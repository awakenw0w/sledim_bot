"""
MTProto-резолвер Telegram-пользователей через пользовательскую сессию Telethon.
Используется для получения устойчивого user_id, базовых данных профиля
и актуального статуса пользователя через userbot-сессию.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl import functions, types

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
    status_kind: str | None
    is_online: bool | None
    activity_at: int | None
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


def _build_status_payload(
    status: object | None,
    checked_at: int,
) -> tuple[str | None, int | None, str | None, bool | None, int | None]:
    if status is None:
        return "статус недоступен", None, "unknown", None, None

    if isinstance(status, types.UserStatusOnline):
        return "онлайн", None, "online", True, checked_at

    if isinstance(status, types.UserStatusOffline):
        was_online = getattr(status, "was_online", None)
        if isinstance(was_online, datetime):
            timestamp = int(was_online.timestamp())
            return "был(а) в сети", timestamp, "offline", False, timestamp
        return "был(а) в сети", None, "offline", False, None

    if isinstance(status, types.UserStatusRecently):
        return "был(а) недавно", None, "recently", False, None

    if isinstance(status, types.UserStatusLastWeek):
        return "был(а) на этой неделе", None, "last_week", False, None

    if isinstance(status, types.UserStatusLastMonth):
        return "был(а) в этом месяце", None, "last_month", False, None

    return "статус скрыт", None, "hidden", False, None


def _build_avatar_payload(photo: object | None) -> tuple[str | None, int | None, bool]:
    if not isinstance(photo, types.UserProfilePhoto):
        return None, None, False

    photo_id = str(photo.photo_id) if getattr(photo, "photo_id", None) is not None else None
    dc_id = int(photo.dc_id) if getattr(photo, "dc_id", None) is not None else None
    has_video = bool(getattr(photo, "has_video", False))
    return photo_id, dc_id, has_video


def _to_resolved_user(user: types.User, lookup_value: str, checked_at: int) -> ResolvedTelegramUser:
    status_text, last_seen_at, status_kind, is_online, activity_at = _build_status_payload(
        getattr(user, "status", None),
        checked_at=checked_at,
    )
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
        status_kind=status_kind,
        is_online=is_online,
        activity_at=activity_at,
        profile_link=profile_link,
        lookup_value=lookup_value,
    )


class TelegramResolver:
    """Ленивая обертка над Telethon-клиентом для резолва и обновления Telegram-пользователей."""

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

    @staticmethod
    def _ensure_regular_user(entity: object) -> types.User:
        if not isinstance(entity, types.User):
            raise TelegramResolverPeerTypeError

        if bool(getattr(entity, "bot", False)):
            raise TelegramResolverPeerTypeError

        return entity

    @staticmethod
    def _normalize_username(username: str | None) -> str | None:
        normalized = (username or "").strip().lstrip("@")
        return normalized or None

    async def _resolve_user_by_lookup(self, lookup: NormalizedTelegramLookup) -> types.User:
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

        return self._ensure_regular_user(entity)

    async def _get_users_by_input(self, telegram_user_id: int, access_hash: int) -> types.User | None:
        client = await self._get_client()
        result = await client(
            functions.users.GetUsersRequest(
                id=[types.InputUser(user_id=int(telegram_user_id), access_hash=int(access_hash))]
            )
        )
        if not result:
            return None

        entity = result[0]
        if isinstance(entity, types.UserEmpty):
            return None

        return self._ensure_regular_user(entity)

    async def get_user_snapshot(
        self,
        telegram_user_id: int,
        access_hash: int | None = None,
        username: str | None = None,
    ) -> ResolvedTelegramUser:
        checked_at = int(datetime.now(tz=timezone.utc).timestamp())
        normalized_username = self._normalize_username(username)
        rpc_error: Exception | None = None

        if access_hash is not None:
            try:
                entity = await self._get_users_by_input(telegram_user_id, access_hash)
                if entity is not None:
                    return _to_resolved_user(entity, str(normalized_username or telegram_user_id), checked_at)
            except TelegramResolverPeerTypeError:
                raise
            except errors.RPCError as exc:
                rpc_error = exc
                logger.warning(
                    "Не удалось обновить Telegram-пользователя по access_hash user_id=%s: %s",
                    telegram_user_id,
                    exc,
                )
            except Exception as exc:
                rpc_error = exc
                logger.warning(
                    "Не удалось обновить Telegram-пользователя по access_hash user_id=%s: %s",
                    telegram_user_id,
                    exc,
                )

        if normalized_username:
            try:
                entity = await self._resolve_user_by_lookup(
                    NormalizedTelegramLookup(kind="username", value=normalized_username)
                )
                return _to_resolved_user(entity, normalized_username, checked_at)
            except TelegramResolverNotFoundError:
                pass
            except TelegramResolverPeerTypeError:
                raise
            except TelegramResolverUnavailableError as exc:
                rpc_error = exc

        try:
            entity = await self._resolve_user_by_lookup(
                NormalizedTelegramLookup(kind="user_id", value=int(telegram_user_id))
            )
            return _to_resolved_user(entity, str(telegram_user_id), checked_at)
        except TelegramResolverNotFoundError:
            if rpc_error is not None:
                raise TelegramResolverUnavailableError from rpc_error
            raise
        except TelegramResolverPeerTypeError:
            raise
        except TelegramResolverUnavailableError as exc:
            if rpc_error is not None:
                raise TelegramResolverUnavailableError from rpc_error
            raise exc

    async def close(self) -> None:
        async with self._lock:
            if self._client is None:
                return
            await self._client.disconnect()
            self._client = None

    async def resolve_user(self, raw_value: str) -> ResolvedTelegramUser:
        lookup = normalize_telegram_lookup(raw_value)
        entity = await self._resolve_user_by_lookup(lookup)
        checked_at = int(datetime.now(tz=timezone.utc).timestamp())
        return _to_resolved_user(entity, str(lookup.value), checked_at)


telegram_resolver = TelegramResolver()


async def resolve_telegram_user(raw_value: str) -> ResolvedTelegramUser:
    return await telegram_resolver.resolve_user(raw_value)


async def fetch_telegram_user_snapshot(
    telegram_user_id: int,
    access_hash: int | None = None,
    username: str | None = None,
) -> ResolvedTelegramUser:
    return await telegram_resolver.get_user_snapshot(
        telegram_user_id=telegram_user_id,
        access_hash=access_hash,
        username=username,
    )


async def close_telegram_resolver() -> None:
    await telegram_resolver.close()
