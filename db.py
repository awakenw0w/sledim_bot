"""
Модуль для работы с базой данных SQLite.
Хранит отслеживаемых пользователей, настройки уведомлений,
последние статусы и онлайн-сессии.
"""

import aiosqlite

from config import DB_PATH

DEFAULT_NOTIFICATION_MODE = "all"
VALID_NOTIFICATION_MODES = {"online", "offline", "all", "off"}
DEFAULT_TG_NOTIFICATION_MODE = "all"
VALID_TG_NOTIFICATION_MODES = {"online", "offline", "all", "off"}
CHANGE_NOTIFICATION_COLUMNS = {
    "name": "notify_name_changes",
    "avatar": "notify_avatar_changes",
    "status": "notify_status_changes",
    "link": "notify_link_changes",
    "privacy": "notify_privacy_changes",
    "fields": "notify_fields_changes",
    "posts": "notify_posts_changes",
    "counts": "notify_counts_changes",
    "relations": "notify_relations_changes",
}
VALID_CHANGE_NOTIFICATION_KEYS = set(CHANGE_NOTIFICATION_COLUMNS)
DEFAULT_CHANGE_NOTIFICATION_SETTINGS = {key: True for key in CHANGE_NOTIFICATION_COLUMNS}
PROFILE_CACHE_FIELDS = (
    "first_name",
    "last_name",
    "profile_status_text",
    "avatar_url",
    "avatar_photo_id",
    "domain",
    "is_closed",
    "friends_count",
    "followers_count",
    "subscriptions_count",
    "city",
    "country",
    "about",
    "bdate",
    "relation",
    "site",
    "interests",
    "books",
    "movies",
    "activities",
    "games",
    "quotes",
)


async def _ensure_column(db: aiosqlite.Connection, table_name: str, column_name: str, ddl: str) -> None:
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        rows = await cursor.fetchall()

    existing_columns = {row[1] for row in rows}
    if column_name not in existing_columns:
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


async def init_db() -> None:
    """Создаёт таблицы в БД и аккуратно добавляет новые поля при обновлении."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                vk_id       INTEGER NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(chat_id, vk_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id                    INTEGER PRIMARY KEY,
                notification_mode          TEXT NOT NULL DEFAULT 'all',
                tg_notification_mode       TEXT NOT NULL DEFAULT 'all',
                tg_notify_activity         INTEGER NOT NULL DEFAULT 1,
                notify_name_changes        INTEGER NOT NULL DEFAULT 1,
                notify_avatar_changes      INTEGER NOT NULL DEFAULT 1,
                notify_status_changes      INTEGER NOT NULL DEFAULT 1,
                notify_link_changes        INTEGER NOT NULL DEFAULT 1,
                notify_privacy_changes     INTEGER NOT NULL DEFAULT 1,
                notify_fields_changes      INTEGER NOT NULL DEFAULT 1,
                notify_posts_changes       INTEGER NOT NULL DEFAULT 1,
                notify_counts_changes      INTEGER NOT NULL DEFAULT 1,
                notify_relations_changes   INTEGER NOT NULL DEFAULT 1,
                created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at                 TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS last_status (
                vk_id               INTEGER PRIMARY KEY,
                online              INTEGER,
                last_seen           INTEGER,
                first_name          TEXT,
                last_name           TEXT,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS online_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                vk_id       INTEGER NOT NULL,
                started_at  INTEGER NOT NULL,
                ended_at    INTEGER,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_cache (
                vk_id               INTEGER PRIMARY KEY,
                first_name          TEXT,
                last_name           TEXT,
                profile_status_text TEXT,
                avatar_url          TEXT,
                avatar_photo_id     TEXT,
                domain              TEXT,
                is_closed           TEXT,
                friends_count       INTEGER,
                followers_count     INTEGER,
                subscriptions_count INTEGER,
                city                TEXT,
                country             TEXT,
                about               TEXT,
                bdate               TEXT,
                relation            TEXT,
                site                TEXT,
                interests           TEXT,
                books               TEXT,
                movies              TEXT,
                activities          TEXT,
                games               TEXT,
                quotes              TEXT,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_change_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vk_id           INTEGER NOT NULL,
                field_name      TEXT NOT NULL,
                old_value       TEXT,
                new_value       TEXT,
                changed_at      INTEGER NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_list_meta (
                vk_id               INTEGER NOT NULL,
                list_type           TEXT NOT NULL,
                total_count         INTEGER,
                is_complete         INTEGER NOT NULL DEFAULT 0,
                last_reason         TEXT,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (vk_id, list_type)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_list_items (
                vk_id               INTEGER NOT NULL,
                list_type           TEXT NOT NULL,
                entity_type         TEXT NOT NULL,
                entity_id           INTEGER NOT NULL,
                screen_name         TEXT,
                first_name          TEXT,
                last_name           TEXT,
                title               TEXT,
                profile_link        TEXT,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (vk_id, list_type, entity_type, entity_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS wall_post_meta (
                vk_id               INTEGER PRIMARY KEY,
                total_count         INTEGER,
                is_available        INTEGER NOT NULL DEFAULT 0,
                last_reason         TEXT,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS wall_post_items (
                vk_id               INTEGER NOT NULL,
                post_id             INTEGER NOT NULL,
                owner_id            INTEGER NOT NULL,
                created_at          INTEGER,
                text                TEXT,
                post_link           TEXT,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (vk_id, post_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tg_tracked_users (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id             INTEGER NOT NULL,
                telegram_user_id    INTEGER NOT NULL,
                username            TEXT,
                first_name          TEXT,
                last_name           TEXT,
                source_value        TEXT,
                is_active           INTEGER NOT NULL DEFAULT 1,
                added_at            TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(chat_id, telegram_user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tg_last_status (
                telegram_user_id    INTEGER PRIMARY KEY,
                status_text         TEXT,
                last_seen_at        INTEGER,
                is_online           INTEGER,
                status_kind         TEXT,
                activity_at         INTEGER,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tg_online_sessions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id             INTEGER NOT NULL,
                telegram_user_id    INTEGER NOT NULL,
                started_at          INTEGER NOT NULL,
                ended_at            INTEGER,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tg_known_users (
                telegram_user_id    INTEGER PRIMARY KEY,
                username            TEXT,
                first_name          TEXT,
                last_name           TEXT,
                access_hash         INTEGER,
                profile_link        TEXT,
                avatar_photo_id     TEXT,
                avatar_dc_id        INTEGER,
                avatar_has_video    INTEGER NOT NULL DEFAULT 0,
                is_bot              INTEGER NOT NULL DEFAULT 0,
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await _ensure_column(db, "chat_settings", "notification_mode", "TEXT NOT NULL DEFAULT 'all'")
        await _ensure_column(db, "chat_settings", "tg_notification_mode", "TEXT NOT NULL DEFAULT 'all'")
        await _ensure_column(db, "chat_settings", "tg_notify_activity", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_name_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_avatar_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_status_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_link_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_privacy_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_fields_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_posts_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_counts_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "notify_relations_changes", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column(db, "chat_settings", "created_at", "TEXT NOT NULL DEFAULT (datetime('now'))")
        await _ensure_column(db, "chat_settings", "updated_at", "TEXT NOT NULL DEFAULT (datetime('now'))")
        await _ensure_column(db, "profile_cache", "first_name", "TEXT")
        await _ensure_column(db, "profile_cache", "last_name", "TEXT")
        await _ensure_column(db, "profile_cache", "profile_status_text", "TEXT")
        await _ensure_column(db, "profile_cache", "avatar_url", "TEXT")
        await _ensure_column(db, "profile_cache", "avatar_photo_id", "TEXT")
        await _ensure_column(db, "profile_cache", "domain", "TEXT")
        await _ensure_column(db, "profile_cache", "is_closed", "TEXT")
        await _ensure_column(db, "profile_cache", "friends_count", "INTEGER")
        await _ensure_column(db, "profile_cache", "followers_count", "INTEGER")
        await _ensure_column(db, "profile_cache", "subscriptions_count", "INTEGER")
        await _ensure_column(db, "profile_cache", "city", "TEXT")
        await _ensure_column(db, "profile_cache", "country", "TEXT")
        await _ensure_column(db, "profile_cache", "about", "TEXT")
        await _ensure_column(db, "profile_cache", "bdate", "TEXT")
        await _ensure_column(db, "profile_cache", "relation", "TEXT")
        await _ensure_column(db, "profile_cache", "site", "TEXT")
        await _ensure_column(db, "profile_cache", "interests", "TEXT")
        await _ensure_column(db, "profile_cache", "books", "TEXT")
        await _ensure_column(db, "profile_cache", "movies", "TEXT")
        await _ensure_column(db, "profile_cache", "activities", "TEXT")
        await _ensure_column(db, "profile_cache", "games", "TEXT")
        await _ensure_column(db, "profile_cache", "quotes", "TEXT")
        await _ensure_column(db, "profile_cache", "updated_at", "TEXT NOT NULL DEFAULT (datetime('now'))")
        await _ensure_column(db, "tg_tracked_users", "source_value", "TEXT")
        await _ensure_column(db, "tg_known_users", "access_hash", "INTEGER")
        await _ensure_column(db, "tg_known_users", "profile_link", "TEXT")
        await _ensure_column(db, "tg_known_users", "avatar_photo_id", "TEXT")
        await _ensure_column(db, "tg_known_users", "avatar_dc_id", "INTEGER")
        await _ensure_column(db, "tg_known_users", "avatar_has_video", "INTEGER NOT NULL DEFAULT 0")
        await _ensure_column(db, "tg_last_status", "is_online", "INTEGER")
        await _ensure_column(db, "tg_last_status", "status_kind", "TEXT")
        await _ensure_column(db, "tg_last_status", "activity_at", "INTEGER")

        await db.commit()


async def _ensure_chat_settings_row(db: aiosqlite.Connection, chat_id: int) -> None:
    await db.execute("""
        INSERT INTO chat_settings (chat_id, notification_mode, created_at, updated_at)
        VALUES (?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(chat_id) DO NOTHING
    """, (chat_id, DEFAULT_NOTIFICATION_MODE))


async def add_tracked_user(chat_id: int, vk_id: int) -> bool:
    """
    Добавляет VK пользователя в список отслеживаемых для данного chat_id.
    Возвращает True, если добавлен впервые или был реактивирован.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)

        async with db.execute(
            "SELECT id, is_active FROM tracked_users WHERE chat_id = ? AND vk_id = ?",
            (chat_id, vk_id)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await db.execute(
                "INSERT INTO tracked_users (chat_id, vk_id, is_active) VALUES (?, ?, 1)",
                (chat_id, vk_id)
            )
            await db.commit()
            return True

        if row[1] == 0:
            await db.execute(
                "UPDATE tracked_users SET is_active = 1 WHERE chat_id = ? AND vk_id = ?",
                (chat_id, vk_id)
            )
            await db.commit()
            return True

        return False


async def add_tg_tracked_user(
    chat_id: int,
    telegram_user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    source_value: str | None = None,
) -> bool:
    """Добавляет Telegram-пользователя в список отслеживаемых для конкретного чата."""
    normalized_username = (username or "").strip().lstrip("@") or None
    normalized_first_name = (first_name or "").strip() or None
    normalized_last_name = (last_name or "").strip() or None
    normalized_source_value = (source_value or "").strip() or None

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)

        async with db.execute(
            "SELECT id, is_active FROM tg_tracked_users WHERE chat_id = ? AND telegram_user_id = ?",
            (chat_id, telegram_user_id),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await db.execute(
                """
                INSERT INTO tg_tracked_users (
                    chat_id,
                    telegram_user_id,
                    username,
                    first_name,
                    last_name,
                    source_value,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    chat_id,
                    telegram_user_id,
                    normalized_username,
                    normalized_first_name,
                    normalized_last_name,
                    normalized_source_value,
                ),
            )
            await db.commit()
            return True

        await db.execute(
            """
            UPDATE tg_tracked_users
            SET
                username = COALESCE(?, username),
                first_name = COALESCE(?, first_name),
                last_name = COALESCE(?, last_name),
                source_value = COALESCE(?, source_value),
                is_active = 1
            WHERE chat_id = ? AND telegram_user_id = ?
            """,
            (
                normalized_username,
                normalized_first_name,
                normalized_last_name,
                normalized_source_value,
                chat_id,
                telegram_user_id,
            ),
        )
        await db.commit()
        return int(row[1]) == 0


async def upsert_tg_known_user(
    telegram_user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    access_hash: int | None = None,
    profile_link: str | None = None,
    avatar_photo_id: str | None = None,
    avatar_dc_id: int | None = None,
    avatar_has_video: bool = False,
    is_bot: bool = False,
) -> None:
    """Сохраняет или обновляет известного Telegram-пользователя, которого бот уже видел."""
    normalized_username = (username or "").strip().lstrip("@") or None
    normalized_first_name = (first_name or "").strip() or None
    normalized_last_name = (last_name or "").strip() or None
    normalized_profile_link = (profile_link or "").strip() or None
    normalized_avatar_photo_id = (avatar_photo_id or "").strip() or None

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO tg_known_users (
                telegram_user_id,
                username,
                first_name,
                last_name,
                access_hash,
                profile_link,
                avatar_photo_id,
                avatar_dc_id,
                avatar_has_video,
                is_bot,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = COALESCE(excluded.username, tg_known_users.username),
                first_name = COALESCE(excluded.first_name, tg_known_users.first_name),
                last_name = COALESCE(excluded.last_name, tg_known_users.last_name),
                access_hash = COALESCE(excluded.access_hash, tg_known_users.access_hash),
                profile_link = COALESCE(excluded.profile_link, tg_known_users.profile_link),
                avatar_photo_id = COALESCE(excluded.avatar_photo_id, tg_known_users.avatar_photo_id),
                avatar_dc_id = COALESCE(excluded.avatar_dc_id, tg_known_users.avatar_dc_id),
                avatar_has_video = excluded.avatar_has_video,
                is_bot = excluded.is_bot,
                updated_at = datetime('now')
            """,
            (
                telegram_user_id,
                normalized_username,
                normalized_first_name,
                normalized_last_name,
                access_hash,
                normalized_profile_link,
                normalized_avatar_photo_id,
                avatar_dc_id,
                1 if avatar_has_video else 0,
                1 if is_bot else 0,
            ),
        )
        await db.commit()


async def get_tg_known_user_by_username(username: str) -> dict | None:
    """Ищет известного Telegram-пользователя по username среди тех, кого бот уже видел."""
    normalized_username = (username or "").strip().lstrip("@")
    if not normalized_username:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT
                telegram_user_id,
                username,
                first_name,
                last_name,
                access_hash,
                profile_link,
                avatar_photo_id,
                avatar_dc_id,
                avatar_has_video,
                is_bot,
                updated_at
            FROM tg_known_users
            WHERE lower(username) = lower(?)
            LIMIT 1
            """,
            (normalized_username,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "telegram_user_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "last_name": row[3],
        "access_hash": row[4],
        "profile_link": row[5],
        "avatar_photo_id": row[6],
        "avatar_dc_id": row[7],
        "avatar_has_video": bool(row[8]),
        "is_bot": bool(row[9]),
        "updated_at": row[10],
    }


async def get_tg_known_user_by_id(telegram_user_id: int) -> dict | None:
    """Возвращает известного Telegram-пользователя по id, если бот уже видел его раньше."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT
                telegram_user_id,
                username,
                first_name,
                last_name,
                access_hash,
                profile_link,
                avatar_photo_id,
                avatar_dc_id,
                avatar_has_video,
                is_bot,
                updated_at
            FROM tg_known_users
            WHERE telegram_user_id = ?
            LIMIT 1
            """,
            (telegram_user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "telegram_user_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "last_name": row[3],
        "access_hash": row[4],
        "profile_link": row[5],
        "avatar_photo_id": row[6],
        "avatar_dc_id": row[7],
        "avatar_has_video": bool(row[8]),
        "is_bot": bool(row[9]),
        "updated_at": row[10],
    }


async def remove_tracked_user(chat_id: int, vk_id: int) -> bool:
    """Удаляет VK пользователя из списка отслеживаемых для данного chat_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tracked_users WHERE chat_id = ? AND vk_id = ?",
            (chat_id, vk_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def remove_tg_tracked_user(chat_id: int, telegram_user_id: int) -> bool:
    """Удаляет Telegram-пользователя из списка отслеживаемых для данного чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tg_tracked_users WHERE chat_id = ? AND telegram_user_id = ?",
            (chat_id, telegram_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_tracked_users(chat_id: int) -> list[int]:
    """Возвращает список активно отслеживаемых VK ID для данного chat_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT vk_id FROM tracked_users WHERE chat_id = ? AND is_active = 1 ORDER BY vk_id",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return [row[0] for row in rows]


async def get_tg_tracked_users(chat_id: int) -> list[int]:
    """Возвращает список активно отслеживаемых Telegram user id для данного chat_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT telegram_user_id
            FROM tg_tracked_users
            WHERE chat_id = ? AND is_active = 1
            ORDER BY COALESCE(first_name, ''), COALESCE(last_name, ''), telegram_user_id
            """,
            (chat_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [row[0] for row in rows]


async def get_all_active_pairs() -> list[tuple[int, int]]:
    """Возвращает все активные пары (chat_id, vk_id)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id, vk_id FROM tracked_users WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()

    return [(row[0], row[1]) for row in rows]


async def get_all_active_tg_pairs() -> list[tuple[int, int]]:
    """Возвращает все активные пары (chat_id, telegram_user_id)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id, telegram_user_id FROM tg_tracked_users WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()

    return [(row[0], row[1]) for row in rows]


async def get_all_user_rows(chat_id: int) -> list[tuple]:
    """Возвращает все записи tracked_users для chat_id, включая неактивные."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, chat_id, vk_id, is_active, added_at FROM tracked_users WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return rows


async def get_tracked_user_detail(chat_id: int, vk_id: int) -> dict | None:
    """Возвращает данные по одному отслеживаемому пользователю в конкретном чате."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT
                t.id,
                t.chat_id,
                t.vk_id,
                t.is_active,
                t.added_at,
                ls.online,
                ls.last_seen,
                COALESCE(pc.first_name, ls.first_name),
                COALESCE(pc.last_name, ls.last_name),
                pc.profile_status_text,
                pc.avatar_url,
                pc.avatar_photo_id,
                pc.domain,
                pc.is_closed,
                pc.friends_count,
                pc.followers_count,
                pc.subscriptions_count,
                pc.city,
                pc.country,
                pc.about,
                pc.bdate,
                pc.relation,
                pc.site,
                pc.interests,
                pc.books,
                pc.movies,
                pc.activities,
                pc.games,
                pc.quotes
            FROM tracked_users AS t
            LEFT JOIN last_status AS ls ON ls.vk_id = t.vk_id
            LEFT JOIN profile_cache AS pc ON pc.vk_id = t.vk_id
            WHERE t.chat_id = ? AND t.vk_id = ?
            LIMIT 1
        """, (chat_id, vk_id)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "chat_id": row[1],
        "vk_id": row[2],
        "is_active": row[3],
        "added_at": row[4],
        "online": row[5],
        "last_seen": row[6],
        "first_name": row[7],
        "last_name": row[8],
        "profile_status_text": row[9],
        "avatar_url": row[10],
        "avatar_photo_id": row[11],
        "domain": row[12],
        "is_closed": row[13],
        "friends_count": row[14],
        "followers_count": row[15],
        "subscriptions_count": row[16],
        "city": row[17],
        "country": row[18],
        "about": row[19],
        "bdate": row[20],
        "relation": row[21],
        "site": row[22],
        "interests": row[23],
        "books": row[24],
        "movies": row[25],
        "activities": row[26],
        "games": row[27],
        "quotes": row[28],
    }


async def get_tracked_users_details(chat_id: int, active_only: bool = True) -> list[dict]:
    """Возвращает список отслеживаемых пользователей чата вместе с кешированными данными."""
    query = """
        SELECT
            t.id,
            t.chat_id,
            t.vk_id,
            t.is_active,
            t.added_at,
            ls.online,
            ls.last_seen,
            COALESCE(pc.first_name, ls.first_name),
            COALESCE(pc.last_name, ls.last_name),
            pc.profile_status_text,
            pc.avatar_url,
            pc.avatar_photo_id,
            pc.domain,
            pc.is_closed,
            pc.friends_count,
            pc.followers_count,
            pc.subscriptions_count,
            pc.city,
            pc.country,
            pc.about,
            pc.bdate,
            pc.relation,
            pc.site,
            pc.interests,
            pc.books,
            pc.movies,
            pc.activities,
            pc.games,
            pc.quotes
        FROM tracked_users AS t
        LEFT JOIN last_status AS ls ON ls.vk_id = t.vk_id
        LEFT JOIN profile_cache AS pc ON pc.vk_id = t.vk_id
        WHERE t.chat_id = ?
    """
    params: list[int] = [chat_id]
    if active_only:
        query += " AND t.is_active = 1"

    query += """
        ORDER BY
            COALESCE(pc.first_name, ls.first_name, ''),
            COALESCE(pc.last_name, ls.last_name, ''),
            t.vk_id
    """

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "chat_id": row[1],
            "vk_id": row[2],
            "is_active": row[3],
            "added_at": row[4],
            "online": row[5],
            "last_seen": row[6],
            "first_name": row[7],
            "last_name": row[8],
            "profile_status_text": row[9],
            "avatar_url": row[10],
            "avatar_photo_id": row[11],
            "domain": row[12],
            "is_closed": row[13],
            "friends_count": row[14],
            "followers_count": row[15],
            "subscriptions_count": row[16],
            "city": row[17],
            "country": row[18],
            "about": row[19],
            "bdate": row[20],
            "relation": row[21],
            "site": row[22],
            "interests": row[23],
            "books": row[24],
            "movies": row[25],
            "activities": row[26],
            "games": row[27],
            "quotes": row[28],
        }
        for row in rows
    ]


async def get_tg_tracked_user_detail(chat_id: int, telegram_user_id: int) -> dict | None:
    """Возвращает данные по одному отслеживаемому Telegram-пользователю в конкретном чате."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT
                t.id,
                t.chat_id,
                t.telegram_user_id,
                COALESCE(t.username, k.username),
                COALESCE(t.first_name, k.first_name),
                COALESCE(t.last_name, k.last_name),
                t.is_active,
                t.added_at,
                t.source_value,
                k.access_hash,
                k.profile_link,
                k.avatar_photo_id,
                k.avatar_dc_id,
                k.avatar_has_video,
                s.status_text,
                s.last_seen_at,
                s.is_online,
                s.status_kind,
                s.activity_at,
                s.updated_at
            FROM tg_tracked_users AS t
            LEFT JOIN tg_known_users AS k ON k.telegram_user_id = t.telegram_user_id
            LEFT JOIN tg_last_status AS s ON s.telegram_user_id = t.telegram_user_id
            WHERE t.chat_id = ? AND t.telegram_user_id = ?
            LIMIT 1
            """,
            (chat_id, telegram_user_id),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "chat_id": row[1],
        "telegram_user_id": row[2],
        "username": row[3],
        "first_name": row[4],
        "last_name": row[5],
        "is_active": row[6],
        "added_at": row[7],
        "source_value": row[8],
        "access_hash": row[9],
        "profile_link": row[10],
        "avatar_photo_id": row[11],
        "avatar_dc_id": row[12],
        "avatar_has_video": bool(row[13]),
        "status_text": row[14],
        "last_seen_at": row[15],
        "is_online": None if row[16] is None else bool(row[16]),
        "status_kind": row[17],
        "activity_at": row[18],
        "status_updated_at": row[19],
    }


async def get_tg_tracked_users_details(chat_id: int, active_only: bool = True) -> list[dict]:
    """Возвращает список отслеживаемых Telegram-пользователей чата с базовыми данными."""
    query = """
        SELECT
            t.id,
            t.chat_id,
            t.telegram_user_id,
            COALESCE(t.username, k.username),
            COALESCE(t.first_name, k.first_name),
            COALESCE(t.last_name, k.last_name),
            t.is_active,
            t.added_at,
            t.source_value,
            k.access_hash,
            k.profile_link,
            k.avatar_photo_id,
            k.avatar_dc_id,
            k.avatar_has_video,
            s.status_text,
            s.last_seen_at,
            s.is_online,
            s.status_kind,
            s.activity_at,
            s.updated_at
        FROM tg_tracked_users AS t
        LEFT JOIN tg_known_users AS k ON k.telegram_user_id = t.telegram_user_id
        LEFT JOIN tg_last_status AS s ON s.telegram_user_id = t.telegram_user_id
        WHERE t.chat_id = ?
    """
    params: list[int] = [chat_id]
    if active_only:
        query += " AND t.is_active = 1"

    query += """
        ORDER BY
            COALESCE(t.first_name, ''),
            COALESCE(t.last_name, ''),
            COALESCE(t.username, ''),
            t.telegram_user_id
    """

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "chat_id": row[1],
            "telegram_user_id": row[2],
            "username": row[3],
            "first_name": row[4],
            "last_name": row[5],
            "is_active": row[6],
            "added_at": row[7],
            "source_value": row[8],
            "access_hash": row[9],
            "profile_link": row[10],
            "avatar_photo_id": row[11],
            "avatar_dc_id": row[12],
            "avatar_has_video": bool(row[13]),
            "status_text": row[14],
            "last_seen_at": row[15],
            "is_online": None if row[16] is None else bool(row[16]),
            "status_kind": row[17],
            "activity_at": row[18],
            "status_updated_at": row[19],
        }
        for row in rows
    ]


async def set_tracking_active(chat_id: int, is_active: bool) -> None:
    """Включает или выключает отслеживание для всех VK ID данного chat_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracked_users SET is_active = ? WHERE chat_id = ?",
            (1 if is_active else 0, chat_id)
        )
        await db.commit()


async def is_tracking_active(chat_id: int) -> bool:
    """Проверяет, есть ли у chat_id хотя бы один активный трекинг."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tracked_users WHERE chat_id = ? AND is_active = 1",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()

    return row[0] > 0


async def get_tg_last_status(telegram_user_id: int) -> dict | None:
    """Возвращает последний сохраненный статус Telegram-пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT status_text, last_seen_at, is_online, status_kind, activity_at, updated_at
            FROM tg_last_status
            WHERE telegram_user_id = ?
            LIMIT 1
            """,
            (telegram_user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "status_text": row[0],
        "last_seen_at": row[1],
        "is_online": None if row[2] is None else bool(row[2]),
        "status_kind": row[3],
        "activity_at": row[4],
        "updated_at": row[5],
    }


async def save_tg_last_status(
    telegram_user_id: int,
    status_text: str | None,
    last_seen_at: int | None = None,
    *,
    is_online: bool | None = None,
    status_kind: str | None = None,
    activity_at: int | None = None,
) -> None:
    """Сохраняет последний известный статус Telegram-пользователя."""
    normalized_status = (status_text or "").strip() or None
    normalized_kind = (status_kind or "").strip() or None
    normalized_is_online = None if is_online is None else (1 if is_online else 0)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO tg_last_status (
                telegram_user_id,
                status_text,
                last_seen_at,
                is_online,
                status_kind,
                activity_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                status_text = excluded.status_text,
                last_seen_at = excluded.last_seen_at,
                is_online = excluded.is_online,
                status_kind = excluded.status_kind,
                activity_at = excluded.activity_at,
                updated_at = datetime('now')
            """,
            (
                telegram_user_id,
                normalized_status,
                last_seen_at,
                normalized_is_online,
                normalized_kind,
                activity_at,
            ),
        )
        await db.commit()


async def get_notification_mode(chat_id: int) -> str:
    """Возвращает режим уведомлений для чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        async with db.execute(
            "SELECT notification_mode FROM chat_settings WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()

    if row is None or row[0] not in VALID_NOTIFICATION_MODES:
        return DEFAULT_NOTIFICATION_MODE
    return row[0]


async def set_notification_mode(chat_id: int, mode: str) -> str:
    """Сохраняет режим уведомлений для чата."""
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in VALID_NOTIFICATION_MODES:
        raise ValueError(f"Unsupported notification mode: {mode}")

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        await db.execute("""
            UPDATE chat_settings
            SET notification_mode = ?, updated_at = datetime('now')
            WHERE chat_id = ?
        """, (normalized_mode, chat_id))
        await db.commit()

    return normalized_mode


async def get_tg_notification_mode(chat_id: int) -> str:
    """Возвращает режим TG-уведомлений для чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        async with db.execute(
            "SELECT tg_notification_mode FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()

    if row is None or row[0] not in VALID_TG_NOTIFICATION_MODES:
        return DEFAULT_TG_NOTIFICATION_MODE
    return row[0]


async def set_tg_notification_mode(chat_id: int, mode: str) -> str:
    """Сохраняет режим TG-уведомлений для чата."""
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in VALID_TG_NOTIFICATION_MODES:
        raise ValueError(f"Unsupported TG notification mode: {mode}")

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        await db.execute(
            """
            UPDATE chat_settings
            SET tg_notification_mode = ?, updated_at = datetime('now')
            WHERE chat_id = ?
            """,
            (normalized_mode, chat_id),
        )
        await db.commit()

    return normalized_mode


async def get_tg_activity_notification_enabled(chat_id: int) -> bool:
    """Возвращает, включены ли уведомления об activity / last seen для TG."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        async with db.execute(
            "SELECT tg_notify_activity FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()

    if row is None:
        return True
    return bool(row[0])


async def set_tg_activity_notification_enabled(chat_id: int, enabled: bool) -> bool:
    """Включает или отключает TG-уведомления об activity / last seen."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        await db.execute(
            """
            UPDATE chat_settings
            SET tg_notify_activity = ?, updated_at = datetime('now')
            WHERE chat_id = ?
            """,
            (1 if enabled else 0, chat_id),
        )
        await db.commit()

    return enabled


async def toggle_tg_activity_notification(chat_id: int) -> bool:
    """Переключает состояние TG-уведомлений об activity / last seen."""
    current_value = await get_tg_activity_notification_enabled(chat_id)
    new_value = not current_value
    await set_tg_activity_notification_enabled(chat_id, new_value)
    return new_value


async def get_change_notification_settings(chat_id: int) -> dict[str, bool]:
    """Возвращает настройки уведомлений по не-онлайн изменениям профиля."""
    select_columns = ", ".join(CHANGE_NOTIFICATION_COLUMNS.values())

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        async with db.execute(
            f"SELECT {select_columns} FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()

    if row is None:
        return dict(DEFAULT_CHANGE_NOTIFICATION_SETTINGS)

    return {
        key: bool(row[index])
        for index, key in enumerate(CHANGE_NOTIFICATION_COLUMNS)
    }


async def set_change_notification_enabled(chat_id: int, key: str, enabled: bool) -> bool:
    """Включает или отключает отдельный тип уведомлений по изменениям профиля."""
    normalized_key = (key or "").strip().lower()
    if normalized_key not in VALID_CHANGE_NOTIFICATION_KEYS:
        raise ValueError(f"Unsupported change notification key: {key}")

    column_name = CHANGE_NOTIFICATION_COLUMNS[normalized_key]
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_chat_settings_row(db, chat_id)
        await db.execute(
            f"""
            UPDATE chat_settings
            SET {column_name} = ?, updated_at = datetime('now')
            WHERE chat_id = ?
            """,
            (1 if enabled else 0, chat_id),
        )
        await db.commit()

    return enabled


async def toggle_change_notification(chat_id: int, key: str) -> bool:
    """Переключает состояние отдельного типа уведомлений и возвращает новое значение."""
    current_settings = await get_change_notification_settings(chat_id)
    normalized_key = (key or "").strip().lower()
    if normalized_key not in current_settings:
        raise ValueError(f"Unsupported change notification key: {key}")

    new_value = not bool(current_settings[normalized_key])
    await set_change_notification_enabled(chat_id, normalized_key, new_value)
    return new_value


async def get_last_status(vk_id: int) -> dict | None:
    """Возвращает последний известный статус VK пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT online, last_seen, first_name, last_name
            FROM last_status
            WHERE vk_id = ?
        """, (vk_id,)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "online": row[0],
        "last_seen": row[1],
        "first_name": row[2],
        "last_name": row[3],
    }


async def save_last_status(
    vk_id: int,
    online: int,
    last_seen: int,
    first_name: str,
    last_name: str,
) -> None:
    """Сохраняет или обновляет последний статус VK пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO last_status (vk_id, online, last_seen, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(vk_id) DO UPDATE SET
                online     = excluded.online,
                last_seen  = excluded.last_seen,
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                updated_at = excluded.updated_at
        """, (vk_id, online, last_seen, first_name, last_name))
        await db.commit()


async def get_profile_cache(vk_id: int) -> dict | None:
    """Возвращает последний сохранённый снимок профиля VK пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"""
            SELECT vk_id, {", ".join(PROFILE_CACHE_FIELDS)}, updated_at
            FROM profile_cache
            WHERE vk_id = ?
            LIMIT 1
        """, (vk_id,)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    result = {"vk_id": row[0]}
    for index, field_name in enumerate(PROFILE_CACHE_FIELDS, start=1):
        result[field_name] = row[index]
    result["updated_at"] = row[len(PROFILE_CACHE_FIELDS) + 1]
    return result


async def save_profile_cache(vk_id: int, profile_data: dict) -> None:
    """
    Сохраняет снимок профиля.

    Для необязательных полей допускается частичный апдейт: если ключ не пришёл в
    profile_data, старое значение в кеше сохраняется без изменений.
    """
    existing = await get_profile_cache(vk_id)
    merged = {field_name: None for field_name in PROFILE_CACHE_FIELDS}
    if existing is not None:
        for field_name in PROFILE_CACHE_FIELDS:
            merged[field_name] = existing.get(field_name)

    for field_name in PROFILE_CACHE_FIELDS:
        if field_name in profile_data:
            merged[field_name] = profile_data.get(field_name)

    values = [vk_id] + [merged[field_name] for field_name in PROFILE_CACHE_FIELDS]
    placeholders = ", ".join("?" for _ in values)
    update_clause = ", ".join(f"{field_name} = excluded.{field_name}" for field_name in PROFILE_CACHE_FIELDS)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            INSERT INTO profile_cache (vk_id, {", ".join(PROFILE_CACHE_FIELDS)}, updated_at)
            VALUES ({placeholders}, datetime('now'))
            ON CONFLICT(vk_id) DO UPDATE SET
                {update_clause},
                updated_at = excluded.updated_at
        """, values)
        await db.commit()


async def add_profile_changes(vk_id: int, changes: list[dict], changed_at: int) -> None:
    """Пишет изменения профиля в историю."""
    if not changes:
        return

    rows = [
        (
            vk_id,
            str(change["field_name"]),
            change.get("old_value"),
            change.get("new_value"),
            changed_at,
        )
        for change in changes
    ]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany("""
            INSERT INTO profile_change_history (vk_id, field_name, old_value, new_value, changed_at)
            VALUES (?, ?, ?, ?, ?)
        """, rows)
        await db.commit()


async def get_recent_profile_changes(chat_id: int, limit: int = 30) -> list[dict]:
    """Возвращает последние изменения профилей пользователей, отслеживаемых в чате."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT
                h.id,
                h.vk_id,
                h.field_name,
                h.old_value,
                h.new_value,
                h.changed_at,
                COALESCE(pc.first_name, ls.first_name),
                COALESCE(pc.last_name, ls.last_name),
                pc.domain
            FROM profile_change_history AS h
            INNER JOIN tracked_users AS t
                ON t.vk_id = h.vk_id
                AND t.chat_id = ?
                AND t.is_active = 1
            LEFT JOIN profile_cache AS pc ON pc.vk_id = h.vk_id
            LEFT JOIN last_status AS ls ON ls.vk_id = h.vk_id
            ORDER BY h.changed_at DESC, h.id DESC
            LIMIT ?
        """, (chat_id, limit)) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "vk_id": row[1],
            "field_name": row[2],
            "old_value": row[3],
            "new_value": row[4],
            "changed_at": row[5],
            "first_name": row[6],
            "last_name": row[7],
            "domain": row[8],
        }
        for row in rows
    ]


async def get_profile_changes_for_report(
    chat_id: int,
    vk_id: int,
    field_names: list[str] | None = None,
    since_ts: int | None = None,
    limit: int = 300,
) -> list[dict]:
    """Возвращает историю изменений профиля с фильтрацией по пользователю, типу и периоду."""
    query = """
        SELECT
            h.id,
            h.vk_id,
            h.field_name,
            h.old_value,
            h.new_value,
            h.changed_at,
            COALESCE(pc.first_name, ls.first_name),
            COALESCE(pc.last_name, ls.last_name),
            pc.domain
        FROM profile_change_history AS h
        INNER JOIN tracked_users AS t
            ON t.vk_id = h.vk_id
            AND t.chat_id = ?
            AND t.is_active = 1
        LEFT JOIN profile_cache AS pc ON pc.vk_id = h.vk_id
        LEFT JOIN last_status AS ls ON ls.vk_id = h.vk_id
        WHERE h.vk_id = ?
    """
    params: list = [chat_id, vk_id]

    if field_names:
        placeholders = ", ".join("?" for _ in field_names)
        query += f" AND h.field_name IN ({placeholders})"
        params.extend(field_names)

    if since_ts is not None:
        query += " AND h.changed_at >= ?"
        params.append(since_ts)

    query += " ORDER BY h.changed_at DESC, h.id DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "vk_id": row[1],
            "field_name": row[2],
            "old_value": row[3],
            "new_value": row[4],
            "changed_at": row[5],
            "first_name": row[6],
            "last_name": row[7],
            "domain": row[8],
        }
        for row in rows
    ]


async def get_profile_list_meta(vk_id: int, list_type: str) -> dict | None:
    """Возвращает метаданные сохранённого снимка списка друзей/подписчиков/подписок."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT vk_id, list_type, total_count, is_complete, last_reason, updated_at
            FROM profile_list_meta
            WHERE vk_id = ? AND list_type = ?
            LIMIT 1
        """, (vk_id, list_type)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "vk_id": row[0],
        "list_type": row[1],
        "total_count": row[2],
        "is_complete": row[3],
        "last_reason": row[4],
        "updated_at": row[5],
    }


async def get_profile_list_items(vk_id: int, list_type: str) -> list[dict]:
    """Возвращает последний полный снимок элементов списка."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT entity_type, entity_id, screen_name, first_name, last_name, title, profile_link
            FROM profile_list_items
            WHERE vk_id = ? AND list_type = ?
            ORDER BY entity_type, entity_id
        """, (vk_id, list_type)) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "entity_type": row[0],
            "entity_id": row[1],
            "screen_name": row[2],
            "first_name": row[3],
            "last_name": row[4],
            "title": row[5],
            "profile_link": row[6],
        }
        for row in rows
    ]


async def save_profile_list_snapshot(
    vk_id: int,
    list_type: str,
    total_count: int | None,
    is_complete: bool,
    reason: str | None = None,
    items: list[dict] | None = None,
) -> None:
    """
    Сохраняет состояние списка.

    Если is_complete=True, старый снимок элементов заменяется целиком.
    Если is_complete=False, элементы не трогаются: это позволяет честно отмечать,
    что точное сравнение сейчас невозможно, не притворяясь, будто список известен.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO profile_list_meta (vk_id, list_type, total_count, is_complete, last_reason, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(vk_id, list_type) DO UPDATE SET
                total_count = excluded.total_count,
                is_complete = excluded.is_complete,
                last_reason = excluded.last_reason,
                updated_at = excluded.updated_at
        """, (vk_id, list_type, total_count, 1 if is_complete else 0, reason))

        if is_complete:
            await db.execute(
                "DELETE FROM profile_list_items WHERE vk_id = ? AND list_type = ?",
                (vk_id, list_type),
            )
            if items:
                await db.executemany("""
                    INSERT INTO profile_list_items (
                        vk_id,
                        list_type,
                        entity_type,
                        entity_id,
                        screen_name,
                        first_name,
                        last_name,
                        title,
                        profile_link,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, [
                    (
                        vk_id,
                        list_type,
                        str(item.get("entity_type") or ""),
                        int(item.get("entity_id") or 0),
                        item.get("screen_name"),
                        item.get("first_name"),
                        item.get("last_name"),
                        item.get("title"),
                        item.get("profile_link"),
                    )
                    for item in items
                ])

        await db.commit()


async def get_wall_post_meta(vk_id: int) -> dict | None:
    """Возвращает метаданные последнего сохранённого снимка стены пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT vk_id, total_count, is_available, last_reason, updated_at
            FROM wall_post_meta
            WHERE vk_id = ?
            LIMIT 1
        """, (vk_id,)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "vk_id": row[0],
        "total_count": row[1],
        "is_available": row[2],
        "last_reason": row[3],
        "updated_at": row[4],
    }


async def get_wall_post_items(vk_id: int) -> list[dict]:
    """Возвращает последний сохранённый список постов со стены пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT post_id, owner_id, created_at, text, post_link
            FROM wall_post_items
            WHERE vk_id = ?
            ORDER BY created_at DESC, post_id DESC
        """, (vk_id,)) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "post_id": row[0],
            "owner_id": row[1],
            "created_at": row[2],
            "text": row[3],
            "post_link": row[4],
        }
        for row in rows
    ]


async def save_wall_post_snapshot(
    vk_id: int,
    total_count: int | None,
    is_available: bool,
    reason: str | None = None,
    items: list[dict] | None = None,
) -> None:
    """
    Сохраняет снимок последних постов со стены пользователя.

    Если стена доступна, список постов заменяется целиком. Если недоступна, старые посты не трогаются,
    чтобы не выдавать отсутствие доступа за удаление записей.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO wall_post_meta (vk_id, total_count, is_available, last_reason, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(vk_id) DO UPDATE SET
                total_count = excluded.total_count,
                is_available = excluded.is_available,
                last_reason = excluded.last_reason,
                updated_at = excluded.updated_at
        """, (vk_id, total_count, 1 if is_available else 0, reason))

        if is_available:
            await db.execute(
                "DELETE FROM wall_post_items WHERE vk_id = ?",
                (vk_id,),
            )
            if items:
                await db.executemany("""
                    INSERT INTO wall_post_items (
                        vk_id,
                        post_id,
                        owner_id,
                        created_at,
                        text,
                        post_link,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, [
                    (
                        vk_id,
                        int(item.get("post_id") or 0),
                        int(item.get("owner_id") or 0),
                        item.get("created_at"),
                        item.get("text"),
                        item.get("post_link"),
                    )
                    for item in items
                ])

        await db.commit()


async def get_tg_open_session(chat_id: int, telegram_user_id: int) -> dict | None:
    """Возвращает текущую незакрытую TG онлайн-сессию пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, started_at
            FROM tg_online_sessions
            WHERE chat_id = ? AND telegram_user_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (chat_id, telegram_user_id),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "started_at": row[1],
    }


async def start_tg_online_session(chat_id: int, telegram_user_id: int, started_at: int) -> int:
    """Создает новую TG онлайн-сессию и возвращает ее ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tg_online_sessions (chat_id, telegram_user_id, started_at, ended_at)
            VALUES (?, ?, ?, NULL)
            """,
            (chat_id, telegram_user_id, started_at),
        )
        await db.commit()
        return cursor.lastrowid


async def end_tg_online_session(chat_id: int, telegram_user_id: int, ended_at: int) -> bool:
    """Закрывает последнюю незакрытую TG онлайн-сессию пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE tg_online_sessions
            SET ended_at = ?
            WHERE id = (
                SELECT id
                FROM tg_online_sessions
                WHERE chat_id = ? AND telegram_user_id = ? AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
            """,
            (ended_at, chat_id, telegram_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def ensure_tg_open_session(chat_id: int, telegram_user_id: int, started_at: int) -> bool:
    """Гарантирует, что у пользователя есть открытая TG онлайн-сессия."""
    existing = await get_tg_open_session(chat_id, telegram_user_id)
    if existing is not None:
        return False

    await start_tg_online_session(chat_id, telegram_user_id, started_at)
    return True


async def close_tg_open_session_if_exists(chat_id: int, telegram_user_id: int, ended_at: int) -> bool:
    """Закрывает TG онлайн-сессию, если она существует."""
    existing = await get_tg_open_session(chat_id, telegram_user_id)
    if existing is None:
        return False

    return await end_tg_online_session(chat_id, telegram_user_id, ended_at)


async def get_tg_online_sessions(chat_id: int, telegram_user_id: int, limit: int = 10) -> list[dict]:
    """Возвращает последние TG онлайн-сессии пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, started_at, ended_at
            FROM tg_online_sessions
            WHERE chat_id = ? AND telegram_user_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (chat_id, telegram_user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "started_at": row[1],
            "ended_at": row[2],
        }
        for row in rows
    ]


async def get_tg_online_sessions_for_period(
    chat_id: int,
    telegram_user_id: int,
    since_ts: int | None = None,
) -> list[dict]:
    """Возвращает TG онлайн-сессии пользователя за выбранный период."""
    query = """
        SELECT id, started_at, ended_at
        FROM tg_online_sessions
        WHERE chat_id = ? AND telegram_user_id = ?
    """
    params: list[int] = [chat_id, telegram_user_id]

    if since_ts is not None:
        query += " AND COALESCE(ended_at, 9223372036854775807) >= ?"
        params.append(since_ts)

    query += " ORDER BY started_at DESC"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "started_at": row[1],
            "ended_at": row[2],
        }
        for row in rows
    ]


async def get_open_session(chat_id: int, vk_id: int) -> dict | None:
    """Возвращает текущую незакрытую онлайн-сессию пользователя, если она есть."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, started_at
            FROM online_sessions
            WHERE chat_id = ? AND vk_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """, (chat_id, vk_id)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "started_at": row[1],
    }


async def start_online_session(chat_id: int, vk_id: int, started_at: int) -> int:
    """Создаёт новую онлайн-сессию и возвращает её ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO online_sessions (chat_id, vk_id, started_at, ended_at)
            VALUES (?, ?, ?, NULL)
        """, (chat_id, vk_id, started_at))
        await db.commit()
        return cursor.lastrowid


async def end_online_session(chat_id: int, vk_id: int, ended_at: int) -> bool:
    """Закрывает последнюю незакрытую онлайн-сессию пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE online_sessions
            SET ended_at = ?
            WHERE id = (
                SELECT id
                FROM online_sessions
                WHERE chat_id = ? AND vk_id = ? AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
        """, (ended_at, chat_id, vk_id))
        await db.commit()
        return cursor.rowcount > 0


async def ensure_open_session(chat_id: int, vk_id: int, started_at: int) -> bool:
    """Гарантирует, что у пользователя есть открытая онлайн-сессия."""
    existing = await get_open_session(chat_id, vk_id)
    if existing is not None:
        return False

    await start_online_session(chat_id, vk_id, started_at)
    return True


async def close_open_session_if_exists(chat_id: int, vk_id: int, ended_at: int) -> bool:
    """Закрывает открытую сессию, если она существует."""
    existing = await get_open_session(chat_id, vk_id)
    if existing is None:
        return False

    return await end_online_session(chat_id, vk_id, ended_at)


async def get_online_sessions(chat_id: int, vk_id: int, limit: int = 10) -> list[dict]:
    """Возвращает список онлайн-сессий пользователя, самые новые сверху."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT id, started_at, ended_at
            FROM online_sessions
            WHERE chat_id = ? AND vk_id = ?
            ORDER BY started_at DESC
            LIMIT ?
        """, (chat_id, vk_id, limit)) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "started_at": row[1],
            "ended_at": row[2],
        }
        for row in rows
    ]


async def get_online_sessions_for_period(
    chat_id: int,
    vk_id: int,
    since_ts: int | None = None,
) -> list[dict]:
    """
    Возвращает онлайн-сессии пользователя за выбранный период.
    Если since_ts не задан, возвращаются все сессии.
    """
    query = """
        SELECT id, started_at, ended_at
        FROM online_sessions
        WHERE chat_id = ? AND vk_id = ?
    """
    params: list[int] = [chat_id, vk_id]

    if since_ts is not None:
        query += " AND COALESCE(ended_at, 9223372036854775807) >= ?"
        params.append(since_ts)

    query += " ORDER BY started_at DESC"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "started_at": row[1],
            "ended_at": row[2],
        }
        for row in rows
    ]
