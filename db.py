"""
Модуль для работы с базой данных SQLite.
Хранит отслеживаемых пользователей, настройки уведомлений,
последние статусы, онлайн-сессии и историю изменений профиля.
"""

import json
from app_cache import ttl_cache, invalidate_cache
import logging
import time
from contextlib import asynccontextmanager

import aiosqlite

from config import DB_PATH

logger = logging.getLogger(__name__)

_db_conn: aiosqlite.Connection | None = None

@asynccontextmanager
async def get_db_connection():
    if _db_conn is None:
        raise RuntimeError("Database connection is not initialized. Call init_db() first.")
    yield _db_conn

async def close_db() -> None:
    global _db_conn
    if _db_conn is not None:
        await _db_conn.close()
        _db_conn = None
        logger.info("Database connection closed.")

DEFAULT_NOTIFICATION_MODE = "all"
VALID_NOTIFICATION_MODES = {"online", "offline", "all", "off"}
DEFAULT_TG_NOTIFICATION_MODE = "all"
VALID_TG_NOTIFICATION_MODES = {"online", "offline", "all", "off"}
TG_CHANGE_NOTIFICATION_COLUMNS = {
    "first_name": "tg_notify_first_name_changes",
    "last_name": "tg_notify_last_name_changes",
    "username": "tg_notify_username_changes",
    "avatar": "tg_notify_avatar_changes",
    "gifts": "tg_notify_gifts_changes",
    "bio": "tg_notify_bio_changes",
}
VALID_TG_CHANGE_NOTIFICATION_KEYS = set(TG_CHANGE_NOTIFICATION_COLUMNS)
DEFAULT_TG_CHANGE_NOTIFICATION_SETTINGS = {key: True for key in TG_CHANGE_NOTIFICATION_COLUMNS}
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
    """Создаёт таблицы в БД, инициализирует подключение и выполняет миграции."""
    global _db_conn
    if _db_conn is None:
        _db_conn = await aiosqlite.connect(DB_PATH)
        await _db_conn.execute("PRAGMA journal_mode=WAL;")
        await _db_conn.execute("PRAGMA synchronous=NORMAL;")
        await _db_conn.execute("PRAGMA foreign_keys=ON;")
        logger.info("Database connection initialized with WAL and foreign_keys pragmas.")

    async with get_db_connection() as db:
        async with db.execute("PRAGMA user_version") as cursor:
            row = await cursor.fetchone()
            current_version = row[0] if row else 0

        # Версия 0 -> 1: Начальная схема
        if current_version < 1:
            logger.info("Running migration to schema version 1...")
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
                    tg_notify_first_name_changes INTEGER NOT NULL DEFAULT 1,
                    tg_notify_last_name_changes  INTEGER NOT NULL DEFAULT 1,
                    tg_notify_username_changes   INTEGER NOT NULL DEFAULT 1,
                    tg_notify_avatar_changes     INTEGER NOT NULL DEFAULT 1,
                    tg_notify_gifts_changes      INTEGER NOT NULL DEFAULT 1,
                    tg_notify_bio_changes        INTEGER NOT NULL DEFAULT 1,
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
                    gifts_count         INTEGER,
                    gifts_supported     INTEGER,
                    bio                 TEXT,
                    is_bot              INTEGER NOT NULL DEFAULT 0,
                    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tg_profile_change_history (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id    INTEGER NOT NULL,
                    change_type         TEXT NOT NULL,
                    old_value           TEXT,
                    new_value           TEXT,
                    metadata_json       TEXT,
                    changed_at          INTEGER NOT NULL,
                    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # Безопасное добавление колонок на случай если это была уже рабочая БД, к которой 
            # применяют новую схему v1 (защита _ensure_column)
            await _ensure_column(db, "chat_settings", "notification_mode", "TEXT NOT NULL DEFAULT 'all'")
            await _ensure_column(db, "chat_settings", "tg_notification_mode", "TEXT NOT NULL DEFAULT 'all'")
            await _ensure_column(db, "chat_settings", "tg_notify_activity", "INTEGER NOT NULL DEFAULT 1")
            await _ensure_column(db, "chat_settings", "tg_notify_first_name_changes", "INTEGER NOT NULL DEFAULT 1")
            await _ensure_column(db, "chat_settings", "tg_notify_last_name_changes", "INTEGER NOT NULL DEFAULT 1")
            await _ensure_column(db, "chat_settings", "tg_notify_username_changes", "INTEGER NOT NULL DEFAULT 1")
            await _ensure_column(db, "chat_settings", "tg_notify_avatar_changes", "INTEGER NOT NULL DEFAULT 1")
            await _ensure_column(db, "chat_settings", "tg_notify_gifts_changes", "INTEGER NOT NULL DEFAULT 1")
            await _ensure_column(db, "chat_settings", "tg_notify_bio_changes", "INTEGER NOT NULL DEFAULT 1")
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
            await _ensure_column(db, "tg_known_users", "gifts_count", "INTEGER")
            await _ensure_column(db, "tg_known_users", "gifts_supported", "INTEGER")
            await _ensure_column(db, "tg_known_users", "bio", "TEXT")
            await _ensure_column(db, "tg_last_status", "is_online", "INTEGER")
            await _ensure_column(db, "tg_last_status", "status_kind", "TEXT")
            await _ensure_column(db, "tg_last_status", "activity_at", "INTEGER")

            await db.execute("PRAGMA user_version = 1")

        # Версия 1 -> 2: Outbox Pattern
        if current_version < 2:
            logger.info("Running migration to schema version 2 (Outbox)...")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS outbox_messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    source          TEXT NOT NULL,
                    chat_id         INTEGER NOT NULL,
                    text            TEXT NOT NULL,
                    parse_mode      TEXT,
                    disable_preview INTEGER NOT NULL DEFAULT 1,
                    message_hash    TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    attempt_count   INTEGER NOT NULL DEFAULT 0,
                    next_retry_at   INTEGER NOT NULL DEFAULT 0,
                    last_error      TEXT,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                    sent_at         TEXT
                )
            """)
            await db.execute("PRAGMA user_version = 2")

        # Индексы (идемпотентные)
        logger.info("Verifying database indices...")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_online_sessions_chat_vk ON online_sessions(chat_id, vk_id, started_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tg_online_sessions_chat_tg ON tg_online_sessions(chat_id, telegram_user_id, started_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_profile_history_vk_field ON profile_change_history(vk_id, field_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tg_profile_history_tg_type ON tg_profile_change_history(telegram_user_id, change_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tracked_users_active ON tracked_users(chat_id, is_active)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tg_tracked_users_active ON tg_tracked_users(chat_id, is_active)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_messages(status, next_retry_at)")

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
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
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


async def sync_tg_tracked_user_profile(
    telegram_user_id: int,
    *,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    """Синхронизирует дублируемые поля TG-пользователя во всех строках отслеживания."""
    normalized_username = (username or "").strip().lstrip("@") or None
    normalized_first_name = (first_name or "").strip() or None
    normalized_last_name = (last_name or "").strip() or None

    async with get_db_connection() as db:
        await db.execute(
            """
            UPDATE tg_tracked_users
            SET
                username = ?,
                first_name = ?,
                last_name = ?
            WHERE telegram_user_id = ?
            """,
            (
                normalized_username,
                normalized_first_name,
                normalized_last_name,
                telegram_user_id,
            ),
        )
        await db.commit()


async def sync_multiple_tg_tracked_user_profiles(users_data: list[dict]) -> None:
    """Пакетно синхронизирует профили TG-пользователей."""
    if not users_data:
        return
    
    data_to_update = []
    for u in users_data:
        uid = u["telegram_user_id"]
        uname = (u.get("username") or "").strip().lstrip("@") or None
        fname = (u.get("first_name") or "").strip() or None
        lname = (u.get("last_name") or "").strip() or None
        data_to_update.append((uname, fname, lname, uid))

    async with get_db_connection() as db:
        await db.executemany("""
            UPDATE tg_tracked_users
            SET username = ?, first_name = ?, last_name = ?
            WHERE telegram_user_id = ?
        """, data_to_update)
        await db.commit()


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
    gifts_count: int | None = None,
    gifts_supported: bool | None = None,
    bio: str | None = None,
    is_bot: bool = False,
) -> None:
    """Сохраняет или обновляет известного Telegram-пользователя, которого бот уже видел."""
    normalized_username = (username or "").strip().lstrip("@") or None
    normalized_first_name = (first_name or "").strip() or None
    normalized_last_name = (last_name or "").strip() or None
    normalized_profile_link = (profile_link or "").strip() or None
    normalized_avatar_photo_id = (avatar_photo_id or "").strip() or None

    async with get_db_connection() as db:
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
                gifts_count,
                gifts_supported,
                bio,
                is_bot,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                access_hash = COALESCE(excluded.access_hash, tg_known_users.access_hash),
                profile_link = excluded.profile_link,
                avatar_photo_id = excluded.avatar_photo_id,
                avatar_dc_id = excluded.avatar_dc_id,
                avatar_has_video = excluded.avatar_has_video,
                gifts_count = excluded.gifts_count,
                gifts_supported = excluded.gifts_supported,
                bio = excluded.bio,
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
                gifts_count,
                None if gifts_supported is None else (1 if gifts_supported else 0),
                (bio or "").strip() or None,
                1 if is_bot else 0,
            ),
        )
        await db.commit()


async def save_multiple_tg_known_users(users_data: list[dict]) -> None:
    """Пакетно сохраняет или обновляет известных Telegram-пользователей."""
    if not users_data:
        return
        
    data_to_insert = []
    for u in users_data:
        uid = int(u["telegram_user_id"])
        uname = (u.get("username") or "").strip().lstrip("@") or None
        fname = (u.get("first_name") or "").strip() or None
        lname = (u.get("last_name") or "").strip() or None
        access_hash = u.get("access_hash")
        plink = (u.get("profile_link") or "").strip() or None
        aphid = (u.get("avatar_photo_id") or "").strip() or None
        adcid = u.get("avatar_dc_id")
        ahvid = 1 if u.get("avatar_has_video") else 0
        gcnt = u.get("gifts_count")
        gsupp = None if u.get("gifts_supported") is None else (1 if u.get("gifts_supported") else 0)
        bio = (u.get("bio") or "").strip() or None
        is_bot = 1 if u.get("is_bot") else 0
        
        data_to_insert.append((
            uid, uname, fname, lname, access_hash, plink, aphid, adcid, ahvid, gcnt, gsupp, bio, is_bot
        ))

    async with get_db_connection() as db:
        await db.executemany("""
            INSERT INTO tg_known_users (
                telegram_user_id, username, first_name, last_name, access_hash,
                profile_link, avatar_photo_id, avatar_dc_id, avatar_has_video,
                gifts_count, gifts_supported, bio, is_bot, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                access_hash = COALESCE(excluded.access_hash, tg_known_users.access_hash),
                profile_link = excluded.profile_link,
                avatar_photo_id = excluded.avatar_photo_id,
                avatar_dc_id = excluded.avatar_dc_id,
                avatar_has_video = excluded.avatar_has_video,
                gifts_count = excluded.gifts_count,
                gifts_supported = excluded.gifts_supported,
                bio = excluded.bio,
                is_bot = excluded.is_bot,
                updated_at = datetime('now')
        """, data_to_insert)
        await db.commit()


async def get_tg_known_user_by_username(username: str) -> dict | None:
    """Ищет известного Telegram-пользователя по username среди тех, кого бот уже видел."""
    normalized_username = (username or "").strip().lstrip("@")
    if not normalized_username:
        return None

    async with get_db_connection() as db:
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
                gifts_count,
                gifts_supported,
                bio,
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
        "gifts_count": row[9],
        "gifts_supported": None if row[10] is None else bool(row[10]),
        "bio": row[11],
        "is_bot": bool(row[12]),
        "updated_at": row[13],
    }


async def get_tg_known_user_by_id(telegram_user_id: int) -> dict | None:
    """Возвращает известного Telegram-пользователя по id, если бот уже видел его раньше."""
    async with get_db_connection() as db:
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
                gifts_count,
                gifts_supported,
                bio,
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
        "gifts_count": row[9],
        "gifts_supported": None if row[10] is None else bool(row[10]),
        "bio": row[11],
        "is_bot": bool(row[12]),
        "updated_at": row[13],
    }


async def get_multiple_tg_known_users_by_id(telegram_user_ids: list[int]) -> dict[int, dict]:
    """Возвращает маппинг известных Telegram-пользователей по их id пакетом."""
    if not telegram_user_ids:
        return {}
        
    placeholders = ",".join("?" * len(telegram_user_ids))
    result = {}
    async with get_db_connection() as db:
        async with db.execute(f"""
            SELECT
                telegram_user_id, username, first_name, last_name, access_hash,
                profile_link, avatar_photo_id, avatar_dc_id, avatar_has_video,
                gifts_count, gifts_supported, bio, is_bot, updated_at
            FROM tg_known_users
            WHERE telegram_user_id IN ({placeholders})
        """, telegram_user_ids) as cursor:
            rows = await cursor.fetchall()
            
    for row in rows:
        uid = row[0]
        result[uid] = {
            "telegram_user_id": uid,
            "username": row[1],
            "first_name": row[2],
            "last_name": row[3],
            "access_hash": row[4],
            "profile_link": row[5],
            "avatar_photo_id": row[6],
            "avatar_dc_id": row[7],
            "avatar_has_video": bool(row[8]),
            "gifts_count": row[9],
            "gifts_supported": None if row[10] is None else bool(row[10]),
            "bio": row[11],
            "is_bot": bool(row[12]),
            "updated_at": row[13],
        }
    return result

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
        "gifts_count": row[9],
        "gifts_supported": None if row[10] is None else bool(row[10]),
        "bio": row[11],
        "is_bot": bool(row[12]),
        "updated_at": row[13],
    }


async def remove_tracked_user(chat_id: int, vk_id: int) -> bool:
    """Удаляет VK пользователя из списка отслеживаемых для данного chat_id."""
    async with get_db_connection() as db:
        cursor = await db.execute(
            "DELETE FROM tracked_users WHERE chat_id = ? AND vk_id = ?",
            (chat_id, vk_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def remove_tg_tracked_user(chat_id: int, telegram_user_id: int) -> bool:
    """Удаляет Telegram-пользователя из списка отслеживаемых для данного чата."""
    async with get_db_connection() as db:
        cursor = await db.execute(
            "DELETE FROM tg_tracked_users WHERE chat_id = ? AND telegram_user_id = ?",
            (chat_id, telegram_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_tracked_users(chat_id: int) -> list[int]:
    """Возвращает список активно отслеживаемых VK ID для данного chat_id."""
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT vk_id FROM tracked_users WHERE chat_id = ? AND is_active = 1 ORDER BY vk_id",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return [row[0] for row in rows]


async def get_tg_tracked_users(chat_id: int) -> list[int]:
    """Возвращает список активно отслеживаемых Telegram user id для данного chat_id."""
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT chat_id, vk_id FROM tracked_users WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()

    return [(row[0], row[1]) for row in rows]


async def get_all_active_tg_pairs() -> list[tuple[int, int]]:
    """Возвращает все активные пары (chat_id, telegram_user_id)."""
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT chat_id, telegram_user_id FROM tg_tracked_users WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()

    return [(row[0], row[1]) for row in rows]


async def get_all_user_rows(chat_id: int) -> list[tuple]:
    """Возвращает все записи tracked_users для chat_id, включая неактивные."""
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT id, chat_id, vk_id, is_active, added_at FROM tracked_users WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return rows


async def get_tracked_user_detail(chat_id: int, vk_id: int) -> dict | None:
    """Возвращает данные по одному отслеживаемому пользователю в конкретном чате."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
                k.gifts_count,
                k.gifts_supported,
                k.bio,
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
        "gifts_count": row[14],
        "gifts_supported": None if row[15] is None else bool(row[15]),
        "bio": row[16],
        "status_text": row[17],
        "last_seen_at": row[18],
        "is_online": None if row[19] is None else bool(row[19]),
        "status_kind": row[20],
        "activity_at": row[21],
        "status_updated_at": row[22],
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
            k.gifts_count,
            k.gifts_supported,
            k.bio,
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

    async with get_db_connection() as db:
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
            "gifts_count": row[14],
            "gifts_supported": None if row[15] is None else bool(row[15]),
            "bio": row[16],
            "status_text": row[17],
            "last_seen_at": row[18],
            "is_online": None if row[19] is None else bool(row[19]),
            "status_kind": row[20],
            "activity_at": row[21],
            "status_updated_at": row[22],
        }
        for row in rows
    ]


async def set_tracking_active(chat_id: int, is_active: bool) -> None:
    """Включает или выключает отслеживание для всех VK ID данного chat_id."""
    async with get_db_connection() as db:
        await db.execute(
            "UPDATE tracked_users SET is_active = ? WHERE chat_id = ?",
            (1 if is_active else 0, chat_id)
        )
        await db.commit()


async def is_tracking_active(chat_id: int) -> bool:
    """Проверяет, есть ли у chat_id хотя бы один активный трекинг."""
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tracked_users WHERE chat_id = ? AND is_active = 1",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()

    return row[0] > 0


async def get_tg_last_status(telegram_user_id: int) -> dict | None:
    """Возвращает последний сохраненный статус Telegram-пользователя."""
    async with get_db_connection() as db:
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


async def get_multiple_tg_last_status(telegram_user_ids: list[int]) -> dict[int, dict]:
    """Возвращает маппинг последних статусов для списка Telegram ID пакетом."""
    if not telegram_user_ids:
        return {}
        
    placeholders = ",".join("?" * len(telegram_user_ids))
    result = {}
    async with get_db_connection() as db:
        async with db.execute(f"""
            SELECT telegram_user_id, status_text, last_seen_at, is_online, status_kind, activity_at, updated_at
            FROM tg_last_status
            WHERE telegram_user_id IN ({placeholders})
        """, telegram_user_ids) as cursor:
            rows = await cursor.fetchall()

    for row in rows:
        uid = row[0]
        result[uid] = {
            "status_text": row[1],
            "last_seen_at": row[2],
            "is_online": None if row[3] is None else bool(row[3]),
            "status_kind": row[4],
            "activity_at": row[5],
            "updated_at": row[6],
        }
    return result


async def save_multiple_tg_last_statuses(statuses_data: list[dict]) -> None:
    """Пакетно сохраняет последние статусы Telegram-пользователей."""
    if not statuses_data:
        return
        
    data_to_insert = []
    for s in statuses_data:
        uid = int(s["telegram_user_id"])
        stext = (s.get("status_text") or "").strip() or None
        lsat = s.get("last_seen_at")
        ison = None if s.get("is_online") is None else (1 if s["is_online"] else 0)
        skind = (s.get("status_kind") or "").strip() or None
        acat = s.get("activity_at")
        data_to_insert.append((uid, stext, lsat, ison, skind, acat))

    async with get_db_connection() as db:
        await db.executemany("""
            INSERT INTO tg_last_status (
                telegram_user_id, status_text, last_seen_at, is_online, status_kind, activity_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                status_text = excluded.status_text,
                last_seen_at = excluded.last_seen_at,
                is_online = excluded.is_online,
                status_kind = excluded.status_kind,
                activity_at = excluded.activity_at,
                updated_at = datetime('now')
        """, data_to_insert)
        await db.commit()


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

    async with get_db_connection() as db:
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


@ttl_cache(ttl_seconds=60)
async def get_notification_mode(chat_id: int) -> str:
    """Возвращает режим уведомлений для чата."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
        await _ensure_chat_settings_row(db, chat_id)
        await db.execute("""
            UPDATE chat_settings
            SET notification_mode = ?, updated_at = datetime('now')
            WHERE chat_id = ?
        """, (normalized_mode, chat_id))
        await db.commit()

    invalidate_cache(get_notification_mode, chat_id)
    return normalized_mode


@ttl_cache(ttl_seconds=60)
async def get_tg_notification_mode(chat_id: int) -> str:
    """Возвращает режим TG-уведомлений для чата."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
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

    invalidate_cache(get_tg_notification_mode, chat_id)
    return normalized_mode


@ttl_cache(ttl_seconds=60)
async def get_tg_activity_notification_enabled(chat_id: int) -> bool:
    """Возвращает, включены ли уведомления об activity / last seen для TG."""
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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

    invalidate_cache(get_tg_activity_notification_enabled, chat_id)
    return enabled


async def toggle_tg_activity_notification(chat_id: int) -> bool:
    """Переключает состояние TG-уведомлений об activity / last seen."""
    current_value = await get_tg_activity_notification_enabled(chat_id)
    new_value = not current_value
    await set_tg_activity_notification_enabled(chat_id, new_value)
    invalidate_cache(get_tg_activity_notification_enabled, chat_id)
    return new_value


@ttl_cache(ttl_seconds=60)
async def get_tg_change_notification_settings(chat_id: int) -> dict[str, bool]:
    """Возвращает настройки TG-уведомлений по изменениям профиля."""
    select_columns = ", ".join(TG_CHANGE_NOTIFICATION_COLUMNS.values())

    async with get_db_connection() as db:
        await _ensure_chat_settings_row(db, chat_id)
        async with db.execute(
            f"SELECT {select_columns} FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()

    if row is None:
        return dict(DEFAULT_TG_CHANGE_NOTIFICATION_SETTINGS)

    return {
        key: bool(row[index])
        for index, key in enumerate(TG_CHANGE_NOTIFICATION_COLUMNS)
    }


async def set_tg_change_notification_enabled(chat_id: int, key: str, enabled: bool) -> bool:
    """Включает или отключает отдельный тип TG-уведомлений по изменениям профиля."""
    normalized_key = (key or "").strip().lower()
    if normalized_key not in VALID_TG_CHANGE_NOTIFICATION_KEYS:
        raise ValueError(f"Unsupported TG change notification key: {key}")

    column_name = TG_CHANGE_NOTIFICATION_COLUMNS[normalized_key]
    async with get_db_connection() as db:
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

    invalidate_cache(get_tg_change_notification_settings, chat_id)
    return enabled


async def toggle_tg_change_notification(chat_id: int, key: str) -> bool:
    """Переключает состояние TG-уведомлений по выбранной категории профиля."""
    current_settings = await get_tg_change_notification_settings(chat_id)
    normalized_key = (key or "").strip().lower()
    if normalized_key not in current_settings:
        raise ValueError(f"Unsupported TG change notification key: {key}")

    new_value = not bool(current_settings[normalized_key])
    await set_tg_change_notification_enabled(chat_id, normalized_key, new_value)
    invalidate_cache(get_tg_change_notification_settings, chat_id)
    return new_value


@ttl_cache(ttl_seconds=60)
async def get_change_notification_settings(chat_id: int) -> dict[str, bool]:
    """Возвращает настройки уведомлений по не-онлайн изменениям профиля."""
    select_columns = ", ".join(CHANGE_NOTIFICATION_COLUMNS.values())

    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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

    invalidate_cache(get_change_notification_settings, chat_id)
    return enabled


async def toggle_change_notification(chat_id: int, key: str) -> bool:
    """Переключает состояние отдельного типа уведомлений и возвращает новое значение."""
    current_settings = await get_change_notification_settings(chat_id)
    normalized_key = (key or "").strip().lower()
    if normalized_key not in current_settings:
        raise ValueError(f"Unsupported change notification key: {key}")

    new_value = not bool(current_settings[normalized_key])
    await set_change_notification_enabled(chat_id, normalized_key, new_value)
    invalidate_cache(get_change_notification_settings, chat_id)
    return new_value


async def get_last_status(vk_id: int) -> dict | None:
    """Возвращает последний известный статус VK пользователя."""
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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


async def get_multiple_last_status(vk_ids: list[int]) -> dict[int, dict]:
    """Возвращает маппинг last_status для списка VK ID пакетом."""
    if not vk_ids:
        return {}
    
    placeholders = ",".join("?" * len(vk_ids))
    result = {}
    async with get_db_connection() as db:
        async with db.execute(f"""
            SELECT vk_id, online, last_seen, first_name, last_name
            FROM last_status
            WHERE vk_id IN ({placeholders})
        """, vk_ids) as cursor:
            rows = await cursor.fetchall()

    for row in rows:
        result[row[0]] = {
            "online": row[1],
            "last_seen": row[2],
            "first_name": row[3],
            "last_name": row[4],
        }
    return result


async def save_multiple_last_statuses(statuses: list[dict]) -> None:
    """Сохраняет пачку last_status за 1 SQL запрос."""
    if not statuses:
        return
        
    data_to_insert = [
        (s["vk_id"], s["online"], s["last_seen"], s.get("first_name", ""), s.get("last_name", ""))
        for s in statuses
    ]

    async with get_db_connection() as db:
        await db.executemany("""
            INSERT INTO last_status (vk_id, online, last_seen, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(vk_id) DO UPDATE SET
                online     = excluded.online,
                last_seen  = excluded.last_seen,
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                updated_at = excluded.updated_at
        """, data_to_insert)
        await db.commit()


async def get_profile_cache(vk_id: int) -> dict | None:
    """Возвращает последний сохранённый снимок профиля VK пользователя."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
        await db.execute(f"""
            INSERT INTO profile_cache (vk_id, {", ".join(PROFILE_CACHE_FIELDS)}, updated_at)
            VALUES ({placeholders}, datetime('now'))
            ON CONFLICT(vk_id) DO UPDATE SET
                {update_clause},
                updated_at = excluded.updated_at
        """, values)
        await db.commit()


async def get_multiple_profile_caches(vk_ids: list[int]) -> dict[int, dict]:
    """Возвращает маппинг кэшей для списка VK ID."""
    if not vk_ids:
        return {}
    
    placeholders = ",".join("?" * len(vk_ids))
    result = {}
    async with get_db_connection() as db:
        async with db.execute(f"""
            SELECT vk_id, {", ".join(PROFILE_CACHE_FIELDS)}, updated_at
            FROM profile_cache
            WHERE vk_id IN ({placeholders})
        """, vk_ids) as cursor:
            rows = await cursor.fetchall()
            
    for row in rows:
        vk_id = row[0]
        cache_dict = {"vk_id": vk_id}
        for index, field_name in enumerate(PROFILE_CACHE_FIELDS, start=1):
            cache_dict[field_name] = row[index]
        cache_dict["updated_at"] = row[len(PROFILE_CACHE_FIELDS) + 1]
        result[vk_id] = cache_dict
    return result


async def save_multiple_profile_caches(profiles_data_map: dict[int, dict]) -> None:
    """Пакетное сохранение профиль-кэшей."""
    if not profiles_data_map:
        return
        
    vk_ids = list(profiles_data_map.keys())
    existing_caches = await get_multiple_profile_caches(vk_ids)
    
    data_to_insert = []
    for vk_id, profile_data in profiles_data_map.items():
        existing = existing_caches.get(vk_id)
        merged = {field_name: None for field_name in PROFILE_CACHE_FIELDS}
        if existing is not None:
            for field_name in PROFILE_CACHE_FIELDS:
                merged[field_name] = existing.get(field_name)

        for field_name in PROFILE_CACHE_FIELDS:
            if field_name in profile_data:
                merged[field_name] = profile_data.get(field_name)

        values = [vk_id] + [merged[field_name] for field_name in PROFILE_CACHE_FIELDS]
        data_to_insert.append(values)
        
    update_clause = ", ".join(f"{field_name} = excluded.{field_name}" for field_name in PROFILE_CACHE_FIELDS)
    
    async with get_db_connection() as db:
        await db.executemany(f"""
            INSERT INTO profile_cache (vk_id, {", ".join(PROFILE_CACHE_FIELDS)}, updated_at)
            VALUES ({", ".join("?" for _ in range(len(PROFILE_CACHE_FIELDS) + 1))}, datetime('now'))
            ON CONFLICT(vk_id) DO UPDATE SET
                {update_clause},
                updated_at = excluded.updated_at
        """, data_to_insert)
        await db.commit()


async def add_profile_changes(vk_id: int, changes: list[dict], changed_at: int) -> None:
    """Пишет изменения профиля в историю (с дедупликацией)."""
    if not changes:
        return

    async with get_db_connection() as db:
        for change in changes:
            field_name = str(change["field_name"])
            new_value = change.get("new_value")

            async with db.execute("""
                SELECT new_value FROM profile_change_history
                WHERE vk_id = ? AND field_name = ?
                ORDER BY changed_at DESC LIMIT 1
            """, (vk_id, field_name)) as cursor:
                row = await cursor.fetchone()

            if row and row[0] == new_value:
                continue

            await db.execute("""
                INSERT INTO profile_change_history (vk_id, field_name, old_value, new_value, changed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (vk_id, field_name, change.get("old_value"), new_value, changed_at))

        await db.commit()


async def get_recent_profile_changes(chat_id: int, limit: int = 30) -> list[dict]:
    """Возвращает последние изменения профилей пользователей, отслеживаемых в чате."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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


async def get_last_tg_profile_change(telegram_user_id: int, change_type: str) -> dict | None:
    """Возвращает самую последнюю запись об изменении конкретного типа для TG-пользователя."""
    async with get_db_connection() as db:
        async with db.execute("""
            SELECT old_value, new_value, changed_at
            FROM tg_profile_change_history
            WHERE telegram_user_id = ? AND change_type = ?
            ORDER BY changed_at DESC
            LIMIT 1
        """, (telegram_user_id, change_type)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "old_value": row[0],
        "new_value": row[1],
        "changed_at": row[2],
    }


async def get_multiple_last_tg_profile_changes(telegram_user_ids: list[int], change_types: list[str]) -> dict[tuple[int, str], dict]:
    """Возвращает маппинг последних изменений для списка TG-пользователей и типов изменений."""
    if not telegram_user_ids or not change_types:
        return {}
        
    id_placeholders = ",".join("?" * len(telegram_user_ids))
    type_placeholders = ",".join("?" * len(change_types))
    
    result = {}
    async with get_db_connection() as db:
        async with db.execute(f"""
            SELECT telegram_user_id, change_type, old_value, new_value, changed_at
            FROM (
                SELECT telegram_user_id, change_type, old_value, new_value, changed_at,
                       ROW_NUMBER() OVER (PARTITION BY telegram_user_id, change_type ORDER BY changed_at DESC) as rn
                FROM tg_profile_change_history
                WHERE telegram_user_id IN ({id_placeholders}) AND change_type IN ({type_placeholders})
            ) WHERE rn = 1
        """, telegram_user_ids + change_types) as cursor:
            rows = await cursor.fetchall()

    for row in rows:
        result[(row[0], row[1])] = {
            "old_value": row[2],
            "new_value": row[3],
            "changed_at": row[4],
        }
    return result


async def add_tg_profile_changes(telegram_user_id: int, changes: list[dict], changed_at: int) -> None:
    """Пишет изменения TG-профиля в историю (с дедупликацией)."""
    if not changes:
        return

    async with get_db_connection() as db:
        for change in changes:
            change_type = str(change["change_type"])
            new_value = change.get("new_value")
            metadata = change.get("metadata")
            metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else None

            async with db.execute("""
                SELECT new_value FROM tg_profile_change_history
                WHERE telegram_user_id = ? AND change_type = ?
                ORDER BY changed_at DESC LIMIT 1
            """, (telegram_user_id, change_type)) as cursor:
                row = await cursor.fetchone()

            if row and row[0] == new_value:
                continue

            await db.execute("""
                INSERT INTO tg_profile_change_history (
                    telegram_user_id, change_type, old_value, new_value, metadata_json, changed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (telegram_user_id, change_type, change.get("old_value"), new_value, metadata_json, changed_at))

        await db.commit()


async def get_tg_profile_changes_for_report(
    chat_id: int,
    telegram_user_id: int,
    change_types: list[str] | None = None,
    since_ts: int | None = None,
    limit: int = 300,
) -> list[dict]:
    """Возвращает историю TG-изменений с фильтрацией по пользователю, типу и периоду."""
    query = """
        SELECT
            h.id,
            h.telegram_user_id,
            h.change_type,
            h.old_value,
            h.new_value,
            h.metadata_json,
            h.changed_at
        FROM tg_profile_change_history AS h
        INNER JOIN tg_tracked_users AS t
            ON t.telegram_user_id = h.telegram_user_id
            AND t.chat_id = ?
            AND t.is_active = 1
        WHERE h.telegram_user_id = ?
    """
    params: list = [chat_id, telegram_user_id]

    if change_types:
        placeholders = ", ".join("?" for _ in change_types)
        query += f" AND h.change_type IN ({placeholders})"
        params.extend(change_types)

    if since_ts is not None:
        query += " AND h.changed_at >= ?"
        params.append(since_ts)

    query += " ORDER BY h.changed_at DESC, h.id DESC LIMIT ?"
    params.append(limit)

    async with get_db_connection() as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    result: list[dict] = []
    for row in rows:
        metadata = None
        if row[5]:
            try:
                metadata = json.loads(row[5])
            except json.JSONDecodeError:
                metadata = {"raw": row[5]}
        result.append(
            {
                "id": row[0],
                "telegram_user_id": row[1],
                "change_type": row[2],
                "old_value": row[3],
                "new_value": row[4],
                "metadata": metadata,
                "changed_at": row[6],
            }
        )

    return result


async def get_tg_open_session(chat_id: int, telegram_user_id: int) -> dict | None:
    """Возвращает текущую незакрытую TG онлайн-сессию пользователя."""
    async with get_db_connection() as db:
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


async def get_multiple_tg_open_sessions(chats_users: list[tuple[int, int]]) -> dict[tuple[int, int], dict]:
    """Пакетно возвращает текущие незакрытые TG онлайн-сессии для списка пар (chat_id, telegram_user_id)."""
    if not chats_users:
        return {}
        
    # Формируем цепочку условий (chat_id = ? AND telegram_user_id = ?) OR ...
    conditions = " OR ".join(["(chat_id = ? AND telegram_user_id = ?)" for _ in chats_users])
    params = []
    for chat_id, uid in chats_users:
        params.extend([chat_id, uid])
        
    result = {}
    async with get_db_connection() as db:
        async with db.execute(f"""
            SELECT id, chat_id, telegram_user_id, started_at
            FROM tg_online_sessions
            WHERE ({conditions}) AND ended_at IS NULL
        """, params) as cursor:
            rows = await cursor.fetchall()
            
    for row in rows:
        result[(row[1], row[2])] = {
            "id": row[0],
            "started_at": row[3],
        }
    return result


async def start_tg_online_session(chat_id: int, telegram_user_id: int, started_at: int) -> int:
    """Создает новую TG онлайн-сессию и возвращает ее ID."""
    async with get_db_connection() as db:
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
    """Закрывает все незакрытые TG онлайн-сессии пользователя атомарно."""
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            UPDATE tg_online_sessions
            SET ended_at = ?
            WHERE chat_id = ? AND telegram_user_id = ? AND ended_at IS NULL
            """,
            (ended_at, chat_id, telegram_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def ensure_tg_open_session(chat_id: int, telegram_user_id: int, started_at: int) -> bool:
    """Гарантирует, что у пользователя есть открытая TG онлайн-сессия атомарно."""
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            INSERT INTO tg_online_sessions (chat_id, telegram_user_id, started_at, ended_at)
            SELECT ?, ?, ?, NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM tg_online_sessions
                WHERE chat_id = ? AND telegram_user_id = ? AND ended_at IS NULL
            )
            """,
            (chat_id, telegram_user_id, started_at, chat_id, telegram_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def close_tg_open_session_if_exists(chat_id: int, telegram_user_id: int, ended_at: int) -> bool:
    """Закрывает TG онлайн-сессию, если она существует (атомарно)."""
    return await end_tg_online_session(chat_id, telegram_user_id, ended_at)


async def get_tg_online_sessions(chat_id: int, telegram_user_id: int, limit: int = 10) -> list[dict]:
    """Возвращает последние TG онлайн-сессии пользователя."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
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
    async with get_db_connection() as db:
        cursor = await db.execute("""
            INSERT INTO online_sessions (chat_id, vk_id, started_at, ended_at)
            VALUES (?, ?, ?, NULL)
        """, (chat_id, vk_id, started_at))
        await db.commit()
        return cursor.lastrowid


async def end_online_session(chat_id: int, vk_id: int, ended_at: int) -> bool:
    """Закрывает все незакрытые онлайн-сессии пользователя атомарно."""
    async with get_db_connection() as db:
        cursor = await db.execute("""
            UPDATE online_sessions
            SET ended_at = ?
            WHERE chat_id = ? AND vk_id = ? AND ended_at IS NULL
        """, (ended_at, chat_id, vk_id))
        await db.commit()
        return cursor.rowcount > 0


async def ensure_open_session(chat_id: int, vk_id: int, started_at: int) -> bool:
    """Гарантирует, что у пользователя есть открытая онлайн-сессия атомарно."""
    async with get_db_connection() as db:
        cursor = await db.execute("""
            INSERT INTO online_sessions (chat_id, vk_id, started_at, ended_at)
            SELECT ?, ?, ?, NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM online_sessions
                WHERE chat_id = ? AND vk_id = ? AND ended_at IS NULL
            )
        """, (chat_id, vk_id, started_at, chat_id, vk_id))
        await db.commit()
        return cursor.rowcount > 0


async def close_open_session_if_exists(chat_id: int, vk_id: int, ended_at: int) -> bool:
    """Закрывает открытую сессию, если она существует (атомарно)."""
    return await end_online_session(chat_id, vk_id, ended_at)


async def get_online_sessions(chat_id: int, vk_id: int, limit: int = 10) -> list[dict]:
    """Возвращает список онлайн-сессий пользователя, самые новые сверху."""
    async with get_db_connection() as db:
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

    async with get_db_connection() as db:
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


async def enqueue_outbox_message(
    source: str,
    chat_id: int,
    text: str,
    message_hash: str,
    parse_mode: str | None = "HTML",
    disable_preview: bool = True,
) -> None:
    """Очередизация сообщения, если нет такого же message_hash в состояниях pending/retry."""
    async with get_db_connection() as db:
        async with db.execute(
            """
            SELECT id FROM outbox_messages 
            WHERE message_hash = ? AND status IN ('pending', 'retry') 
            LIMIT 1
            """,
            (message_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            
        if row is not None:
            # Уже есть в очереди, дубликат не добавляем
            return

        await db.execute(
            """
            INSERT INTO outbox_messages (
                source, chat_id, text, parse_mode, disable_preview, message_hash
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source, chat_id, text, parse_mode, 1 if disable_preview else 0, message_hash)
        )
        await db.commit()


async def get_pending_outbox_messages(limit: int = 20) -> list[dict]:
    """Возвращает список сообщений для отправки (статусы pending и retry, если пришло их время)."""
    now_ts = int(time.time())
    async with get_db_connection() as db:
        async with db.execute(
            """
            SELECT id, source, chat_id, text, parse_mode, disable_preview, attempt_count
            FROM outbox_messages
            WHERE status IN ('pending', 'retry') AND next_retry_at <= ?
            ORDER BY next_retry_at ASC, id ASC
            LIMIT ?
            """,
            (now_ts, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            
    return [
        {
            "id": row[0],
            "source": row[1],
            "chat_id": row[2],
            "text": row[3],
            "parse_mode": row[4],
            "disable_preview": bool(row[5]),
            "attempt_count": row[6],
        }
        for row in rows
    ]


async def mark_outbox_message_sent(message_id: int) -> None:
    """Помечает сообщение как отправленное."""
    async with get_db_connection() as db:
        await db.execute(
            """
            UPDATE outbox_messages
            SET status = 'sent', sent_at = datetime('now')
            WHERE id = ?
            """,
            (message_id,)
        )
        await db.commit()


async def mark_outbox_message_failed(message_id: int, last_error: str) -> None:
    """Помечает сообщение как failed навсегда (например, из-за блокировки или лимита)."""
    async with get_db_connection() as db:
        await db.execute(
            """
            UPDATE outbox_messages
            SET status = 'failed', last_error = ?
            WHERE id = ?
            """,
            (str(last_error), message_id)
        )
        await db.commit()


async def schedule_outbox_message_retry(message_id: int, next_retry_at: int, attempt_count: int, last_error: str) -> None:
    """Откладывает отправку на будущее (status='retry')."""
    async with get_db_connection() as db:
        await db.execute(
            """
            UPDATE outbox_messages
            SET status = 'retry', next_retry_at = ?, attempt_count = ?, last_error = ?
            WHERE id = ?
            """,
            (next_retry_at, attempt_count, str(last_error), message_id)
        )
        await db.commit()
