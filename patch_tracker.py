import re

with open('tracker.py', 'r', encoding='utf-8') as f:
    code = f.read()

# ADD LOCKS AT THE TOP
if '_IS_ONLINE_RUNNING = False' not in code:
    code = code.replace('RELATION_LIST_CONFIG = {', '_IS_ONLINE_RUNNING = False\n_IS_PROFILE_RUNNING = False\n\nRELATION_LIST_CONFIG = {')

# REWRITE _check_online_and_notify
online_func_pattern = r'async def _check_online_and_notify\(bot: Bot\) -> None:(.*?)async def _check_profile_and_notify'
new_online_func = '''async def _check_online_and_notify(bot: Bot) -> None:
    global _IS_ONLINE_RUNNING
    if _IS_ONLINE_RUNNING:
        logger.warning("Overlap protection: _check_online_and_notify is already running.")
        return
    _IS_ONLINE_RUNNING = True
    t0 = time.time()
    
    try:
        pairs = await db.get_all_active_pairs()
        if not pairs:
            return

        vk_ids, watchers_by_vk = _build_watchers_by_vk(pairs)
        users_data = await vk_api.get_users_status(vk_ids)
        if users_data is None:
            logger.warning("VK API не ответил, пропускаем цикл онлайн-проверки")
            return

        now_ts = int(time.time())
        last_known_statuses = await db.get_multiple_last_status(vk_ids)
        statuses_to_save = []
        outbox_count = 0

        for user in users_data:
            vk_id = user.get("id")
            if not vk_id:
                continue

            new_online = int(user.get("online", 0) or 0)
            new_last_seen = vk_api.extract_last_seen_ts(user) or 0
            first_name = user.get("first_name", "")
            last_name = user.get("last_name", "")

            old_status = last_known_statuses.get(vk_id)
            related_chat_ids = watchers_by_vk.get(vk_id, [])

            for chat_id in related_chat_ids:
                try:
                    await _reconcile_sessions(chat_id, vk_id, new_online, now_ts)
                except Exception as exc:
                    logger.error("Ошибка согласования сессий chat_id=%s, vk_id=%s: %s", chat_id, vk_id, exc)

            statuses_to_save.append({
                "vk_id": vk_id,
                "online": new_online,
                "last_seen": new_last_seen,
                "first_name": first_name,
                "last_name": last_name,
            })
            
            if old_status is None:
                continue

            old_online = int(old_status.get("online", 0) or 0)
            if old_online == new_online:
                continue

            message_text = _build_notification(user, new_online, now_ts)
            for chat_id in related_chat_ids:
                try:
                    notification_mode = await db.get_notification_mode(chat_id)
                    if not _should_send_status_notification(notification_mode, new_online):
                        continue

                    m_hash = hashlib.md5(f"vk_status|{chat_id}|{vk_id}|{new_online}|{now_ts}".encode()).hexdigest()
                    await db.enqueue_outbox_message(
                        source="vk",
                        chat_id=chat_id,
                        text=message_text,
                        message_hash=m_hash,
                        parse_mode="HTML",
                        disable_preview=True,
                    )
                    logger.debug("Уведомление отправлено в очередь: chat_id=%s, vk_id=%s, online=%s", chat_id, vk_id, new_online)
                    outbox_count += 1
                except Exception as exc:
                    logger.error("Не удалось добавить уведомление в очередь chat_id=%s, vk_id=%s: %s", chat_id, vk_id, exc)

        await db.save_multiple_last_statuses(statuses_to_save)
        
        elapsed = time.time() - t0
        logger.info("[VK Tracker] Online check completed for %s users in %.2fs. Outbox messages: %s", len(users_data), elapsed, outbox_count)
    finally:
        _IS_ONLINE_RUNNING = False

async def _check_profile_and_notify'''
code = re.sub(online_func_pattern, new_online_func, code, flags=re.DOTALL)

# REWRITE _check_profile_and_notify
profile_func_pattern = r'async def _check_profile_and_notify\(bot: Bot\) -> None:(.*?)async def run_tracker'
new_profile_func = '''async def _check_profile_and_notify(bot: Bot) -> None:
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

        for vk_id in vk_ids:
            user = users_map.get(vk_id)
            if user is None:
                continue

            profile_snapshot = vk_api.extract_profile_snapshot(user)
            old_profile_raw = cached_profiles.get(vk_id)
            old_profile = _prime_profile_baseline(old_profile_raw, profile_snapshot)
            related_chat_ids = watchers_by_vk.get(vk_id, [])

            relation_change_records: list[dict] = []
            relation_detail_lines: list[str] = []
            relation_events: list[dict] = []
            for list_type in RELATION_LIST_CONFIG:
                records, detail_lines, events = await _sync_relation_list(vk_id, list_type, old_profile, profile_snapshot)
                relation_change_records.extend(records)
                relation_detail_lines.extend(detail_lines)
                relation_events.extend(events)

            new_wall_posts, wall_post_total_count = await _sync_wall_posts(vk_id)

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
code = re.sub(profile_func_pattern, new_profile_func, code, flags=re.DOTALL)

with open('tracker.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Patch tracker ok')
