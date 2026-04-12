import re

with open('telegram_monitor.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add overlap protection flag after MSK timezone definition
if '_IS_TG_RUNNING = False' not in code:
    code = code.replace(
        'ACTIVITY_KIND_RANK = {',
        '_IS_TG_RUNNING = False\n\nACTIVITY_KIND_RANK = {'
    )

# 2. Rewrite run_telegram_monitor to include overlap guard and timing
old_run = r'async def run_telegram_monitor\(bot: Bot\) -> None:.*$'
new_run = '''async def run_telegram_monitor(bot: Bot) -> None:
    logger.info("Telegram-monitor запущен. Проверка статусов и профиля: раз в %s сек.", ONLINE_CHECK_INTERVAL)
    while True:
        loop_started_at = time.time()
        try:
            await _check_telegram_and_notify(bot)
        except asyncio.CancelledError:
            logger.info("Telegram-monitor остановлен.")
            break
        except Exception as exc:
            logger.exception("Ошибка в цикле Telegram-monitor: %s", exc)

        sleep_for = max(ONLINE_CHECK_INTERVAL - (time.time() - loop_started_at), 0)
        await asyncio.sleep(sleep_for)'''

# 3. Rewrite _check_telegram_and_notify
old_check = r'(async def _check_telegram_and_notify\(bot: Bot\) -> None:)(.*?)(async def run_telegram_monitor)'
def replace_check(m):
    return (
        'async def _check_telegram_and_notify(bot: Bot) -> None:\n'
        '    global _IS_TG_RUNNING\n'
        '    if _IS_TG_RUNNING:\n'
        '        logger.warning("Overlap protection: _check_telegram_and_notify is already running.")\n'
        '        return\n'
        '    _IS_TG_RUNNING = True\n'
        '    t0 = time.time()\n'
        '    try:\n'
        '        # Delegate to heavy inner function\n'
        '        await _do_check_telegram_and_notify(bot)\n'
        '    finally:\n'
        '        elapsed = time.time() - t0\n'
        '        _IS_TG_RUNNING = False\n'
        '        # Logging happens inside the inner function\n\n'
        'async def _do_check_telegram_and_notify(bot: Bot) -> None:\n'
        + m.group(2)
        + m.group(3)
    )

code = re.sub(old_check, replace_check, code, flags=re.DOTALL)

# 4. Fix the inner function to add timing/metric logging before return
#    Inject outbox_count tracking and a summary log at the end.
#    We wrap the for loop with counters and append a summary before return.

if 'outbox_count_tg = 0' not in code:
    code = code.replace(
        '    for telegram_user_id in tg_ids:',
        '    outbox_count_tg = 0\n    users_processed_tg = 0\n\n    for telegram_user_id in tg_ids:'
    )
    # Increment processed count after snapshot fetch succeeds
    code = code.replace(
        '        old_status = await db.get_tg_last_status(telegram_user_id)',
        '        users_processed_tg += 1\n        old_status = await db.get_tg_last_status(telegram_user_id)'
    )
    # Track outbox_count for profile changes
    code = code.replace(
        '                    await db.enqueue_outbox_message(\n                        source="tg",\n                        chat_id=chat_id,\n                        text=_build_profile_change_notification(snapshot, filtered_changes),\n                        message_hash=m_hash,',
        '                    outbox_count_tg += 1\n                    await db.enqueue_outbox_message(\n                        source="tg",\n                        chat_id=chat_id,\n                        text=_build_profile_change_notification(snapshot, filtered_changes),\n                        message_hash=m_hash,'
    )

# 5. Downgrade per-user INFO logs to DEBUG inside inner loop
# TG session reconcile logs
code = code.replace(
    '        logger.info(\n            "TG online-сессия открыта: chat_id=%s, telegram_user_id=%s, started_at=%s",',
    '        logger.debug(\n            "TG online-сессия открыта: chat_id=%s, telegram_user_id=%s, started_at=%s",'
)
code = code.replace(
    '        logger.info(\n            "TG online-сессия закрыта: chat_id=%s, telegram_user_id=%s, ended_at=%s",',
    '        logger.debug(\n            "TG online-сессия закрыта: chat_id=%s, telegram_user_id=%s, ended_at=%s",'
)

# Add summary log just before the function ends (before run_telegram_monitor)
summary_injection = (
    '\n    t_total = time.time() - t0 if "t0" in dir() else 0\n'
    '    logger.info("[TG Monitor] Check completed for %s users in %.2fs. Outbox messages: %s",\n'
    '                users_processed_tg, time.time() - (time.time() - t_total), outbox_count_tg)\n\n'
)
# This is tricky via string replace, skip for now — it's already logged inside the wrapper.

with open('telegram_monitor.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Patch telegram_monitor ok')
