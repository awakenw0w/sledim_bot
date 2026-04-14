"""
Конфигурация бота — читает переменные окружения из .env файла.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем переменные строго из .env рядом с проектом и
# разрешаем им переопределять окружение процесса.
ENV_PATH = Path(__file__).resolve().with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)
logger = logging.getLogger(__name__)

# Токен Telegram-бота (получить у @BotFather)
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Токен доступа VK API (сервисный ключ приложения или токен пользователя)
VK_ACCESS_TOKEN: str = os.getenv("VK_ACCESS_TOKEN", "").strip()

# Версия VK API
VK_API_VERSION: str = os.getenv("VK_API_VERSION", "5.131")

# Путь к файлу базы данных SQLite
DB_PATH: str = os.getenv("DB_PATH", "bot_database.db")

# Параметры клиентского Telegram MTProto-слоя для резолва username -> user_id.
# Нужен именно пользовательский session, а не бот-токен.
TELEGRAM_USERBOT_API_ID_RAW: str = os.getenv("TELEGRAM_USERBOT_API_ID", "").strip()
TELEGRAM_USERBOT_API_ID: int | None = int(TELEGRAM_USERBOT_API_ID_RAW) if TELEGRAM_USERBOT_API_ID_RAW.isdigit() else None
TELEGRAM_USERBOT_API_HASH: str = os.getenv("TELEGRAM_USERBOT_API_HASH", "").strip()
TELEGRAM_USERBOT_SESSION: str = os.getenv("TELEGRAM_USERBOT_SESSION", "").strip()
TELEGRAM_USERBOT_SESSION_FILE: str = os.getenv("TELEGRAM_USERBOT_SESSION_FILE", "telegram_userbot").strip()

# Интервал проверки онлайн-статуса (в секундах)
ONLINE_CHECK_INTERVAL: int = int(os.getenv("ONLINE_CHECK_INTERVAL", "60"))

# Интервал проверки не-онлайн изменений профиля (в секундах)
PROFILE_CHECK_INTERVAL: int = int(os.getenv("PROFILE_CHECK_INTERVAL", "3600"))

# Старое имя переменной оставлено только для обратной совместимости с кодом,
# который мог импортировать CHECK_INTERVAL раньше.
CHECK_INTERVAL: int = ONLINE_CHECK_INTERVAL

# Обязательная подписка на Telegram-канал.
# Для приватного канала нужен числовой chat_id вида -100..., одной invite-ссылки
# недостаточно для проверки подписки через Bot API.
REQUIRED_CHANNEL_LINK: str = os.getenv(
    "REQUIRED_CHANNEL_LINK",
    "",
).strip()
REQUIRED_CHANNEL_ID_RAW: str = os.getenv("REQUIRED_CHANNEL_ID", "").strip()

REQUIRED_CHANNEL_ID: int | None = None
if REQUIRED_CHANNEL_ID_RAW:
    if REQUIRED_CHANNEL_ID_RAW.startswith("-100"):
        REQUIRED_CHANNEL_ID = int(REQUIRED_CHANNEL_ID_RAW)
    else:
        logger.warning(
            "REQUIRED_CHANNEL_ID=%s выглядит некорректно. "
            "Для канала нужен chat_id в формате -100..., иначе проверка подписки не сработает.",
            REQUIRED_CHANNEL_ID_RAW,
        )

# Проверка обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не задана в .env файле")

if not VK_ACCESS_TOKEN:
    raise ValueError("Переменная VK_ACCESS_TOKEN не задана в .env файле")
