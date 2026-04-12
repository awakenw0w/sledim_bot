import re

with open('telegram_monitor.py', 'r', encoding='utf-8') as f:
    code = f.read()

# REWRITE _do_check_telegram_and_notify with batching
old_do_check_pattern = r'async def _do_check_telegram_and_notify\(bot: Bot\) -> None:(.*?)async def run_telegram_monitor'
new_do_check = '''async def _do_check_telegram_and_notify(bot: Bot) -> None:
    pairs = await db.get_all_active_tg_pairs()
    if not pairs:
        return

    tg_ids, watchers_by_tg = _build_watchers_by_tg(pairs)
    now_ts = int(time.time())
    
    # Batch preload DB data
    known_users_map = await db.get_multiple_tg_known_users_by_id(tg_ids)
    last_statuses_map = await db.get_multiple_tg_last_status(tg_ids)
    
    # Preload all sessions
    all_chat_user_pairs = []
    for uid, chats in watchers_by_tg.items():
        for cid in chats:
            all_chat_user_pairs.append((cid, uid))
    open_sessions_map = await db.get_multiple_tg_open_sessions(all_chat_user_pairs)
    
    # Preload profile changes for deduplication (only for common types)
    # We collect all change types that might be detected
    all_possible_change_types = list(TG_CHANGE_SETTING_KEYS.keys()) + ["activity"]
    last_recorded_changes_map = await db.get_multiple_last_tg_profile_changes(tg_ids, all_possible_change_types)

    outbox_count_tg = 0
    users_processed_tg = 0
    
    known_users_to_save = []
    tracked_profiles_to_sync = []
    statuses_to_save = []

    for telegram_user_id in tg_ids:
        related_chat_ids = watchers_by_tg.get(telegram_user_id, [])
        known_user = known_users_map.get(telegram_user_id)

        if known_user is None and related_chat_ids:
            seed_detail = await db.get_tg_tracked_user_detail(related_chat_ids[0], telegram_user_id)
            if seed_detail is not None:
                known_user = {
                    "telegram_user_id": seed_detail["telegram_user_id"],
                    "username": seed_detail.get("username"),
                    "first_name": seed_detail.get("first_name"),
                    "last_name": seed_detail.get("last_name"),
                    "access_hash": seed_detail.get("access_hash"),
                    "profile_link": seed_detail.get("profile_link"),
                    "avatar_photo_id": seed_detail.get("avatar_photo_id"),
                    "avatar_dc_id": seed_detail.get("avatar_dc_id"),
                    "avatar_has_video": seed_detail.get("avatar_has_video"),
                    "gifts_count": seed_detail.get("gifts_count"),
                    "gifts_supported": seed_detail.get("gifts_supported"),
                    "is_bot": False,
                }

        if known_user is None:
            logger.warning("TG user_id=%s отсутствует в локальном кеше, пропускаем мониторинг", telegram_user_id)
            continue

        try:
            snapshot = await fetch_telegram_user_snapshot(
                telegram_user_id=telegram_user_id,
                access_hash=known_user.get("access_hash"),
                username=known_user.get("username"),
            )
        except TelegramResolverNotFoundError:
            logger.warning("Не удалось обновить TG user_id=%s: пользователь не найден", telegram_user_id)
            continue
        except TelegramResolverPeerTypeError:
            logger.warning("Не удалось обновить TG user_id=%s: объект не является обычным пользователем", telegram_user_id)
            continue
        except TelegramResolverUnavailableError as exc:
            logger.warning("TG resolver временно недоступен для user_id=%s: %s", telegram_user_id, exc)
            continue
        except Exception as exc:
            logger.exception("Ошибка при обновлении TG user_id=%s: %s", telegram_user_id, exc)
            continue

        users_processed_tg += 1
        old_status = last_statuses_map.get(telegram_user_id)
        profile_changes = _build_profile_change_records(known_user, snapshot)
        
        # Системная дедупликация
        deduplicated_changes = []
        if profile_changes:
            for change in profile_changes:
                ctype = change["change_type"]
                last_recorded = last_recorded_changes_map.get((telegram_user_id, ctype))
                if last_recorded and last_recorded.get("new_value") == change.get("new_value"):
                    continue
                deduplicated_changes.append(change)
        
        if deduplicated_changes:
            await db.add_tg_profile_changes(telegram_user_id, deduplicated_changes, now_ts)
        
        # Collect updates
        known_users_to_save.append({
            "telegram_user_id": int(snapshot.telegram_user_id),
            "username": snapshot.username,
            "first_name": snapshot.first_name,
            "last_name": snapshot.last_name,
            "access_hash": snapshot.access_hash,
            "profile_link": snapshot.profile_link,
            "avatar_photo_id": snapshot.avatar_photo_id,
            "avatar_dc_id": snapshot.avatar_dc_id,
            "avatar_has_video": snapshot.avatar_has_video,
            "gifts_count": snapshot.gifts_count,
            "gifts_supported": snapshot.gifts_supported,
            "is_bot": snapshot.is_bot,
        })
        tracked_profiles_to_sync.append({
            "telegram_user_id": int(snapshot.telegram_user_id),
            "username": snapshot.username,
            "first_name": snapshot.first_name,
            "last_name": snapshot.last_name,
        })
        statuses_to_save.append({
            "telegram_user_id": int(snapshot.telegram_user_id),
            "status_text": snapshot.status_text,
            "last_seen_at": snapshot.last_seen_at,
            "is_online": snapshot.is_online,
            "status_kind": snapshot.status_kind,
            "activity_at": snapshot.activity_at,
        })

        for chat_id in related_chat_ids:
            try:
                # Get session from pre-loaded map
                open_session = open_sessions_map.get((chat_id, telegram_user_id))
                await _reconcile_tg_sessions_batched(chat_id, snapshot, now_ts, open_session)
            except Exception as exc:
                logger.error("Не удалось синхронизировать TG сессию chat_id=%s, telegram_user_id=%s: %s", chat_id, telegram_user_id, exc)

        if profile_changes:
            for chat_id in related_chat_ids:
                try:
                    settings = await db.get_tg_change_notification_settings(chat_id)
                    filtered_changes = _filter_profile_changes_by_settings(deduplicated_changes, settings)
                    if not filtered_changes:
                        continue
                    m_hash = hashlib.md5(f"tg_profile|{chat_id}|{telegram_user_id}|{now_ts}".encode()).hexdigest()
                    outbox_count_tg += 1
                    await db.enqueue_outbox_message(
                        source="tg",
                        chat_id=chat_id,
                        text=_build_profile_change_notification(snapshot, filtered_changes),
                        message_hash=m_hash,
                        parse_mode="HTML",
                        disable_preview=True,
                    )
                except Exception as exc:
                    logger.error("Ошибка при отправке уведомления об изменении TG-профиля chat_id=%s: %s", chat_id, exc)

        activity_history_record = _build_activity_history_record(old_status, snapshot)
        if activity_history_record is not None:
            # Дедупликация для активности
            last_activity = last_recorded_changes_map.get((telegram_user_id, "activity"))
            if last_activity is None or last_activity.get("new_value") != activity_history_record.get("new_value"):
                await db.add_tg_profile_changes(telegram_user_id, [activity_history_record], now_ts)
                activity_text = _build_activity_notification(snapshot, old_status, now_ts)
                for chat_id in related_chat_ids:
                    try:
                        if not await db.get_tg_activity_notification_enabled(chat_id):
                            continue
                        m_hash = hashlib.md5(f"tg_activity|{chat_id}|{telegram_user_id}|{snapshot.activity_at}|{now_ts}".encode()).hexdigest()
                        await db.enqueue_outbox_message(
                            source="tg",
                            chat_id=chat_id,
                            text=activity_text,
                            message_hash=m_hash,
                            parse_mode="HTML",
                            disable_preview=True,
                        )
                        outbox_count_tg += 1
                    except Exception as exc:
                        logger.error(
                            "Не удалось добавить TG уведомление об активности в очередь chat_id=%s, telegram_user_id=%s: %s",
                            chat_id,
                            telegram_user_id,
                            exc,
                        )

    # Perform batch writes at the end
    await db.save_multiple_tg_known_users(known_users_to_save)
    await db.sync_multiple_tg_tracked_user_profiles(tracked_profiles_to_sync)
    await db.save_multiple_tg_last_statuses(statuses_to_save)

    logger.info(
        "[TG Monitor] Check completed for %s users in %.2fs. Outbox messages: %s",
        users_processed_tg,
        time.time() - t0,
        outbox_count_tg,
    )

async def _reconcile_tg_sessions_batched(chat_id: int, snapshot, now_ts: int, open_session: dict | None) -> None:
    telegram_user_id = int(snapshot.telegram_user_id)

    if snapshot.is_online is True and open_session is None:
        started_at = int(getattr(snapshot, "activity_at", None) or now_ts)
        await db.start_tg_online_session(chat_id, telegram_user_id, started_at)
        logger.debug("TG online-сессия открыта: chat_id=%s, telegram_user_id=%s, started_at=%s", chat_id, telegram_user_id, started_at)
        return

    if snapshot.is_online is False and open_session is not None:
        ended_at = int(getattr(snapshot, "last_seen_at", None) or getattr(snapshot, "activity_at", None) or now_ts)
        if ended_at < int(open_session["started_at"]):
            ended_at = now_ts
        await db.end_tg_online_session(chat_id, telegram_user_id, ended_at)
        logger.debug("TG online-сессия закрыта: chat_id=%s, telegram_user_id=%s, ended_at=%s", chat_id, telegram_user_id, ended_at)

async def run_telegram_monitor'''

code = re.sub(old_do_check_pattern, new_do_check, code, flags=re.DOTALL)

# Also need to remove the now unused helper functions from within _do_check if any were defined there.
# Looking at the previous turn's output, _get_tg_mode, _get_tg_activity_enabled, _get_tg_change_settings were there.
# My new_do_check uses db.get_* directly (which are cached now).

with open('telegram_monitor.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Patch tg monitor batching ok')
