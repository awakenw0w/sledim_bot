"""
MTProto-резолвер Telegram-пользователей через пользовательскую сессию Telethon.
Используется только для получения устойчивого user_id и базовых данных по username / ссылке.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl import types

from config import (
    TELEGRAM_USERBOT_API_HASH,
    TELEGRAM_USERBOT_API_ID,
    TELEGRAM_USERBOT_SESSION,
    TELEGRAM_USERBOT_SESSION_FILE,
)

logger = logging.getLogger(__name__)


class TelegramResolverError(Exception):
    """Базовая ошибка Telegram-резолвера."""


class TelegramResolverInvalidInputError(TelegramResolverError):
    """Введены некорректные данные для поиска пользователя."""


class TelegramResolverNotFoundError(TelegramResolverError):
    """Telegram-пользователь не найден."""


class TelegramResolverPeerTypeError(TelegramResolverError):
    """Найденный peer не является обычным пользователем."""


class TelegramResolverUnavailableError(TelegramResolverError):
    """MTProto-резолвер недоступен или не настроен."""


@dataclass(slots=True)
class NormalizedTelegramLookup:
    kind: Literal["user_id", "username"]
    value: str | int


@dataclass(slots=True)
class ResolvedTelegramUser:
    telegram_user_id: int
    access_hash: int | None
    username: str | None
    first_name: str | None
    last_name: str | None
    is_bot: bool
    avatar_photo_id: str | None
    avatar_dc_id: int | None
    avatar_has_video: bool
    status_text: str | None
    last_seen_at: int | None
    profile_link: str
    lookup_value: str


def normalize_telegram_lookup(raw_value: str) -> NormalizedTelegramLookup:
    """Нормализует ввод пользователя и возвращает username или числовой user_id."""
    normalized = (raw_value or "").strip()
    if not normalized:
        raise TelegramResolverInvalidInputError

    for prefix in ("https://", "http://"):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    if normalized.lower().startswith("t.me/"):
        normalized = normalized[5:]

    normalized = normalized.strip().strip("/")
    if normalized.startswith("@"):
        normalized = normalized[1:]
    normalized = normalized.strip()

    if not normalized:
        raise TelegramResolverInvalidInputError

    if "/" in normalized or " " in normalized:
        raise TelegramResolverInvalidInputError

    if normalized.isdigit():
        return NormalizedTelegramLookup(kind="user_id", value=int(normalized))

    return NormalizedTelegramLookup(kind="username", value=normalized)


def _build_status_payload(status: object | None) -> tuple[str | None, int | None]:
    if status is None:
        return None, None

    if isinstance(status, types.UserStatusOnline):
        return "онлайн", None

    if isinstance(status, types.UserStatusOffline):
        was_online = getattr(status, "was_online", None)
        if isinstance(was_online, datetime):
            return "был(а) в сети", int(was_online.timestamp())
        return "был(а) в сети", None

    if isinstance(status, types.UserStatusRecently):
        return "был(а) недавно", None

    if isinstance(status, types.UserStatusLastWeek):
        return "был(а) на этой неделе", None

    if isinstance(status, types.UserStatusLastMonth):
        return "был(а) в этом месяце", None

    return "статус скрыт", None


def _build_avatar_payload(photo: object | None) -> tuple[str | None, int | None, bool]:
    if not isinstance(photo, types.UserProfilePhoto):
        return None, None, False

    photo_id = str(photo.photo_id) if getattr(photo, "photo_id", None) is not None else None
    dc_id = int(photo.dc_id) if getattr(photo, "dc_id", None) is not None else None
    has_video = bool(getattr(photo, "has_video", False))
    return photo_id, dc_id, has_video


def _to_resolved_user(user: types.User, lookup_value: str) -> ResolvedTelegramUser:
    status_text, last_seen_at = _build_status_payload(getattr(user, "status", None))
    avatar_photo_id, avatar_dc_id, avatar_has_video = _build_avatar_payload(getattr(user, "photo", None))
    username = (getattr(user, "username", None) or "").strip() or None
    profile_link = f"https://t.me/{username}" if username else f"tg://user?id={int(user.id)}"

    return ResolvedTelegramUser(
        telegram_user_id=int(user.id),
        access_hash=int(user.access_hash) if getattr(user, "access_hash", None) is not None else None,
        username=username,
        first_name=(getattr(user, "first_name", None) or "").strip() or None,
        last_name=(getattr(user, "last_name", None) or "").strip() or None,
        is_bot=bool(getattr(user, "bot", False)),
        avatar_photo_id=avatar_photo_id,
        avatar_dc_id=avatar_dc_id,
        avatar_has_video=avatar_has_video,
        status_text=status_text,
        last_seen_at=last_seen_at,
        profile_link=profile_link,
        lookup_value=lookup_value,
    )


class TelegramResolver:
    """Ленивая обертка над Telethon-клиентом для резолва Telegram-пользователей."""

    def __init__(self) -> None:
        self._client: TelegramClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> TelegramClient:
        if self._client is not None:
            return self._client

        async with self._lock:
            if self._client is not None:
                return self._client

            if TELEGRAM_USERBOT_API_ID is None or not TELEGRAM_USERBOT_API_HASH:
                raise TelegramResolverUnavailableError

            session = StringSession(TELEGRAM_USERBOT_SESSION) if TELEGRAM_USERBOT_SESSION else TELEGRAM_USERBOT_SESSION_FILE
            client = TelegramClient(
                session,
                TELEGRAM_USERBOT_API_ID,
                TELEGRAM_USERBOT_API_HASH,
                device_model="sledim_bot",
                system_version="Windows",
                app_version="1.0",
            )

            try:
                await client.connect()
                if not await client.is_user_authorized():
                    await client.disconnect()
                    raise TelegramResolverUnavailableError
            except TelegramResolverUnavailableError:
                raise
            except Exception as exc:
                logger.exception("Не удалось подключить MTProto-резолвер Telegram: %s", exc)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                raise TelegramResolverUnavailableError from exc

            self._client = client
            return client

    async def close(self) -> None:
        async with self._lock:
            if self._client is None:
                return
            await self._client.disconnect()
            self._client = None

    async def resolve_user(self, raw_value: str) -> ResolvedTelegramUser:
        lookup = normalize_telegram_lookup(raw_value)
        client = await self._get_client()

        try:
            if lookup.kind == "username":
                entity = await client.get_entity(str(lookup.value))
            else:
                entity = await client.get_entity(types.PeerUser(int(lookup.value)))
        except (errors.UsernameInvalidError, errors.UsernameNotOccupiedError, ValueError):
            raise TelegramResolverNotFoundError from None
        except errors.RPCError as exc:
            logger.warning("MTProto-резолвер вернул RPC-ошибку: %s", exc)
            raise TelegramResolverUnavailableError from exc
        except Exception as exc:
            logger.exception("Неожиданная ошибка Telegram-резолвера: %s", exc)
            raise TelegramResolverUnavailableError from exc

        if not isinstance(entity, types.User):
            raise TelegramResolverPeerTypeError

        if bool(getattr(entity, "bot", False)):
            raise TelegramResolverPeerTypeError

        return _to_resolved_user(entity, str(lookup.value))


telegram_resolver = TelegramResolver()


async def resolve_telegram_user(raw_value: str) -> ResolvedTelegramUser:
    return await telegram_resolver.resolve_user(raw_value)


async def close_telegram_resolver() -> None:
    await telegram_resolver.close()
