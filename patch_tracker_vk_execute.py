import re

with open('tracker.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update _sync_relation_list signature and logic
old_sync_relation = r'async def _sync_relation_list\(\s*vk_id: int,\s*list_type: str,\s*old_profile: dict \| None,\s*profile_snapshot: dict,\s*\) -> tuple\[list\[dict\], list\[str\], list\[dict\]\]:'
new_sync_relation = 'async def _sync_relation_list(vk_id: int, list_type: str, old_profile: dict | None, profile_snapshot: dict, prefetch_snapshot: dict | None = None) -> tuple[list[dict], list[str], list[dict]]:'
code = re.sub(old_sync_relation, new_sync_relation, code)

# Change the logic inside _sync_relation_list to use prefetch
old_call_rel = r'current_snapshot = await vk_api\.get_relation_snapshot\(vk_id, list_type, expected_count\)'
new_call_rel = '''if prefetch_snapshot is not None:
        current_snapshot = prefetch_snapshot
    else:
        current_snapshot = await vk_api.get_relation_snapshot(vk_id, list_type, expected_count)'''
code = code.replace(old_call_rel, new_call_rel)

# 2. Update _sync_wall_posts signature and logic
old_sync_wall = r'async def _sync_wall_posts\(vk_id: int\) -> tuple\[list\[dict\], int \| None\]:'
new_sync_wall = 'async def _sync_wall_posts(vk_id: int, prefetch_snapshot: dict | None = None) -> tuple[list[dict], int | None]:'
code = re.sub(old_sync_wall, new_sync_wall, code)

old_call_wall = r'current_snapshot = await vk_api\.get_recent_wall_posts\(vk_id\)'
new_call_wall = '''if prefetch_snapshot is not None:
        current_snapshot = prefetch_snapshot
    else:
        current_snapshot = await vk_api.get_recent_wall_posts(vk_id)'''
code = code.replace(old_call_wall, new_call_wall)

# 3. Update _check_profile_and_notify with batching
old_check_profile_pattern = r'async def _check_profile_and_notify\(bot: Bot\) -> None:(.*?)async def run_tracker'
new_check_profile = '''async def _check_profile_and_notify(bot: Bot) -> None:
    global _IS_PROFILE_RUNNING
    if _IS_PROFILE_RUNNING:
        logger.warning("Overlap protection: _check_profile_and_notify is already running.")
        return
    _IS_PROFILE_RUNNING = True
    t0 = time.time()
    
    try:
        pairs = await db.get_all_active_pairs()
        if not pairs:
            return

        vk_ids, watchers_by_vk = _build_watchers_by_vk(pairs)
        users_data = await vk_api.get_users_status(vk_ids)
        if users_data is None:
            logger.warning("VK API не ответил, пропускаем цикл проверки профиля")
            return

        users_map: dict[int, dict] = {u["id"]: u for u in users_data if "id" in u}
        now_ts = int(time.time())
        
        cached_profiles = await db.get_multiple_profile_caches(vk_ids)
        profiles_to_save = {}
        outbox_count = 0

        # VK execute batching: chunk users by 5 to stay within 25 methods per request
        CHUNK_SIZE = 5
        for i in range(0, len(vk_ids), CHUNK_SIZE):
            chunk_ids = vk_ids[i:i + CHUNK_SIZE]
            
            # Fetch bulk data for relations and wall
            batch_data = await vk_api.get_batch_profile_data(chunk_ids)
            
            for vk_id in chunk_ids:
                user = users_map.get(vk_id)
                if user is None:
                    continue

                profile_snapshot = vk_api.extract_profile_snapshot(user)
                old_profile_raw = cached_profiles.get(vk_id)
                old_profile = _prime_profile_baseline(old_profile_raw, profile_snapshot)
                related_chat_ids = watchers_by_vk.get(vk_id, [])

                # Get prefetched data for this user
                user_batch = batch_data.get(vk_id, {})

                relation_change_records: list[dict] = []
                relation_detail_lines: list[str] = []
                relation_events: list[dict] = []
                for list_type in RELATION_LIST_CONFIG:
                    # Map raw data to what sync_relation expects (normalization happens inside sync_relation)
                    raw_rel_data = user_batch.get(list_type)
                    prefetch_rel = None
                    if raw_rel_data is not None:
                        prefetch_rel = vk_api._process_relation_response(raw_rel_data, list_type)
                    
                    records, detail_lines, events = await _sync_relation_list(vk_id, list_type, old_profile, profile_snapshot, prefetch_snapshot=prefetch_rel)
                    relation_change_records.extend(records)
                    relation_detail_lines.extend(detail_lines)
                    relation_events.extend(events)

                # Prefetch wall
                raw_wall_data = user_batch.get("wall")
                prefetch_wall = None
                if raw_wall_data is not None:
                    prefetch_wall = vk_api._process_wall_response(raw_wall_data)
                
                new_wall_posts, wall_post_total_count = await _sync_wall_posts(vk_id, prefetch_snapshot=prefetch_wall)

                profiles_to_save[vk_id] = profile_snapshot

                profile_changes = _build_profile_changes(old_profile, profile_snapshot)
                profile_changes = _merge_change_records(profile_changes, relation_change_records)
                if new_wall_posts:
                    profile_changes.extend(_build_wall_post_change_records(new_wall_posts))
                if profile_changes:
                    await db.add_profile_changes(vk_id, profile_changes, now_ts)

                profile_changes_for_message = list(profile_changes)
                if relation_events:
                    profile_changes_for_message = [
                        change for change in profile_changes_for_message
                        if str(change.get("field_name")) not in RELATION_COUNT_FIELDS
                    ]

                detail_lines_for_message = [] if relation_events else relation_detail_lines
                if profile_changes_for_message or detail_lines_for_message:
                    for chat_id in related_chat_ids:
                        try:
                            change_settings = await db.get_change_notification_settings(chat_id)
                            filtered_profile_changes = _filter_profile_changes_by_settings(
                                profile_changes_for_message,
                                change_settings,
                            )
                            filtered_detail_lines = (
                                detail_lines_for_message if bool(change_settings.get("relations", True)) else []
                            )
                            if not filtered_profile_changes and not filtered_detail_lines:
                                continue

                            profile_message_text = _build_profile_change_notification(
                                user,
                                filtered_profile_changes,
                                now_ts,
                                detail_lines=filtered_detail_lines,
                            )
                            m_hash = hashlib.md5(f"vk_profile|{chat_id}|{vk_id}|{now_ts}".encode()).hexdigest()
                            await db.enqueue_outbox_message(
                                source="vk",
                                chat_id=chat_id,
                                text=profile_message_text,
                                message_hash=m_hash,
                                parse_mode="HTML",
                                disable_preview=True,
                            )
                            logger.debug("Уведомление об изменении в очереди: vk_id=%s", vk_id)
                            outbox_count += 1
                        except Exception as exc:
                            logger.error("Не удалось добавить в очередь профиль chat_id=%s: %s", chat_id, exc)

                if relation_events:
                    for event in relation_events:
                        relation_message_text = _build_relation_notification(
                            user,
                            list_type=str(event["list_type"]),
                            added_items=list(event.get("added_items") or []),
                            removed_items=list(event.get("removed_items") or []),
                            changed_at=now_ts,
                            current_count=_normalize_count(event.get("current_count")),
                        )
                        for chat_id in related_chat_ids:
                            try:
                                change_settings = await db.get_change_notification_settings(chat_id)
                                if not bool(change_settings.get("relations", True)):
                                    continue
                                m_hash = hashlib.md5(f"vk_relation|{chat_id}|{vk_id}|{event['list_type']}|{now_ts}".encode()).hexdigest()
                                await db.enqueue_outbox_message(
                                    source="vk",
                                    chat_id=chat_id,
                                    text=relation_message_text,
                                    message_hash=m_hash,
                                    parse_mode="HTML",
                                    disable_preview=True,
                                )
                                outbox_count += 1
                            except Exception as exc:
                                logger.error("Ошибка связей chat_id=%s: %s", chat_id, exc)

                if new_wall_posts:
                    wall_message_text = _build_wall_posts_notification(
                        user,
                        added_posts=new_wall_posts,
                        changed_at=now_ts,
                        total_count=wall_post_total_count,
                    )
                    for chat_id in related_chat_ids:
                        try:
                            change_settings = await db.get_change_notification_settings(chat_id)
                            if not bool(change_settings.get("posts", True)):
                                continue
                            m_hash = hashlib.md5(f"vk_posts|{chat_id}|{vk_id}|{now_ts}".encode()).hexdigest()
                            await db.enqueue_outbox_message(
                                source="vk",
                                chat_id=chat_id,
                                text=wall_message_text,
                                message_hash=m_hash,
                                parse_mode="HTML",
                                disable_preview=True,
                            )
                            outbox_count += 1
                        except Exception as exc:
                            logger.error("Ошибка постов chat_id=%s: %s", chat_id, exc)

        await db.save_multiple_profile_caches(profiles_to_save)
        elapsed = time.time() - t0
        logger.info("[VK Tracker] Profile check completed for %s users in %.2fs. Outbox messages: %s", len(vk_ids), elapsed, outbox_count)
    finally:
        _IS_PROFILE_RUNNING = False

async def run_tracker'''

code = re.sub(old_check_profile_pattern, new_check_profile, code, flags=re.DOTALL)

with open('tracker.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Patch tracker VK execute batching ok')
