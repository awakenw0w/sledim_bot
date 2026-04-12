"""
Модуль для работы с VK API.
Получает информацию об онлайн-статусе пользователей.
Исправлен для Windows / aiohttp / SSL с явным использованием certifi.
"""

import ssl
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlparse

import aiohttp
import certifi

from config import VK_ACCESS_TOKEN, VK_API_VERSION

logger = logging.getLogger(__name__)

VK_API_BASE = "https://api.vk.com/method"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)
MSK = timezone(timedelta(hours=3))

VK_ALLOWED_DOMAINS = {"vk.com", "www.vk.com", "vk.ru", "www.vk.ru"}
RELATION_LIST_FRIENDS = "friends"
RELATION_LIST_FOLLOWERS = "followers"
RELATION_LIST_SUBSCRIPTIONS = "subscriptions"
RELATION_LIST_TYPES = {RELATION_LIST_FRIENDS, RELATION_LIST_FOLLOWERS, RELATION_LIST_SUBSCRIPTIONS}
RELATION_LIST_LIMITS = {
    RELATION_LIST_FRIENDS: 5000,
    RELATION_LIST_FOLLOWERS: 3000,
    RELATION_LIST_SUBSCRIPTIONS: 3000,
}
RELATION_LIST_BATCH_SIZES = {
    RELATION_LIST_FRIENDS: 5000,
    RELATION_LIST_FOLLOWERS: 1000,
    RELATION_LIST_SUBSCRIPTIONS: 200,
}
VK_ONLINE_FIELDS = [
    "online",
    "last_seen",
    "first_name",
    "last_name",
    "screen_name",
    "domain",
]
VK_ONLINE_FIELDS_STR = ",".join(VK_ONLINE_FIELDS)
VK_USER_FIELDS = [
    "online",
    "last_seen",
    "first_name",
    "last_name",
    "status",
    "photo_id",
    "photo_200_orig",
    "counters",
    "followers_count",
    "screen_name",
    "domain",
    "is_closed",
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
]
VK_USER_FIELDS_STR = ",".join(VK_USER_FIELDS)

PROFILE_FIELD_LABELS = {
    "first_name": "Имя",
    "last_name": "Фамилия",
    "profile_status_text": "Текстовый статус",
    "avatar_url": "Аватарка",
    "domain": "Короткая ссылка",
    "is_closed": "Статус профиля",
    "friends_count": "Количество друзей",
    "followers_count": "Количество подписчиков",
    "subscriptions_count": "Количество подписок",
    "city": "Город",
    "country": "Страна",
    "about": "О себе",
    "bdate": "Дата рождения",
    "relation": "Семейное положение",
    "site": "Сайт",
    "interests": "Интересы",
    "books": "Книги",
    "movies": "Фильмы",
    "activities": "Деятельность",
    "games": "Игры",
    "quotes": "Цитаты",
}
WALL_POST_TRACK_LIMIT = 100

RELATION_LABELS = {
    1: "не женат / не замужем",
    2: "есть друг / есть подруга",
    3: "помолвлен / помолвлена",
    4: "женат / замужем",
    5: "всё сложно",
    6: "в активном поиске",
    7: "влюблён / влюблена",
    8: "в гражданском браке",
}


async def get_users_status(vk_ids: list[int]) -> list[dict[str, Any]] | None:
    """
    Получает статусы сразу нескольких VK пользователей через users.get.
    Возвращает список словарей при успехе, [] при пустом списке ID и None при ошибке.
    """
    if not vk_ids:
        return []

    return await _get_users_by_fields(vk_ids, VK_USER_FIELDS_STR)


async def get_users_online_presence(vk_ids: list[int]) -> list[dict[str, Any]] | None:
    """Получает только поля, нужные для быстрого опроса онлайна."""
    return await _get_users_by_fields(vk_ids, VK_ONLINE_FIELDS_STR)


async def get_single_user_status(vk_id: int) -> dict[str, Any] | None:
    """Получает статус одного VK пользователя."""
    result = await get_users_status([vk_id])
    if result is None or len(result) == 0:
        return None
    return result[0]


async def _get_users_by_fields(vk_ids: list[int], fields: str) -> list[dict[str, Any]] | None:
    if not vk_ids:
        return []

    response_data = await _call_vk_api_response(
        "users.get",
        {
            "user_ids": ",".join(str(i) for i in vk_ids),
            "fields": fields,
        },
    )
    if not isinstance(response_data, list):
        logger.error("Поле 'response' имеет неожиданный тип: %r", response_data)
        return None
    return response_data


def extract_vk_screen_name(value: str) -> str | None:
    """Извлекает короткое имя пользователя из ссылки, username, @username или числового ID."""
    raw_value = (value or "").strip()
    if not raw_value:
        return None

    # Поддерживаем короткий ввод без ссылки: ID, username и @username.
    if "://" not in raw_value and "/" not in raw_value:
        normalized_value = raw_value.removeprefix("@").strip()
        return normalized_value or None

    normalized = raw_value
    if "://" not in normalized:
        normalized = f"https://{normalized}"

    try:
        parsed = urlparse(normalized)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    if (parsed.netloc or "").casefold() not in VK_ALLOWED_DOMAINS:
        return None

    path_parts = [part.strip() for part in parsed.path.split("/") if part.strip()]
    if len(path_parts) != 1:
        return None

    screen_name = path_parts[0]
    if not screen_name:
        return None

    return screen_name


async def resolve_user_by_vk_link(link: str) -> dict[str, Any] | None:
    """Находит пользователя VK по ссылке, username, @username или числовому ID."""
    screen_name = extract_vk_screen_name(link)
    if screen_name is None:
        return None

    response_data = await _call_vk_api_response(
        "users.get",
        {
            "user_ids": screen_name,
            "fields": VK_USER_FIELDS_STR,
        },
    )
    if not isinstance(response_data, list) or not response_data:
        logger.error("VK API не вернул пользователя для ссылки %s. Ответ: %r", link, response_data)
        return None
    return response_data[0]


def extract_last_seen_ts(user_data: dict[str, Any]) -> int | None:
    """Безопасно извлекает timestamp последнего визита из ответа VK API."""
    if not isinstance(user_data, dict):
        return None

    last_seen = user_data.get("last_seen")
    if not isinstance(last_seen, dict):
        return None

    ts = last_seen.get("time")
    if isinstance(ts, int):
        return ts
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    return text


def _extract_location_title(value: Any) -> str | None:
    if isinstance(value, dict):
        title = value.get("title")
        return _normalize_text(title)
    return _normalize_text(value)


def _normalize_relation(value: Any) -> str | None:
    if value is None:
        return None

    try:
        relation_code = int(value)
    except (TypeError, ValueError):
        return _normalize_text(value)

    if relation_code <= 0:
        return None

    return RELATION_LABELS.get(relation_code, str(relation_code))


def _normalize_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_counter(counters: Any, key: str) -> int | None:
    if isinstance(counters, dict):
        return _normalize_int(counters.get(key))
    return None


def build_profile_link(vk_id: int | None, domain: str | None = None) -> str:
    normalized_domain = _normalize_text(domain)
    if normalized_domain:
        return f"https://vk.com/{normalized_domain}"
    if vk_id is not None:
        return f"https://vk.com/id{vk_id}"
    return "https://vk.com"


def build_group_link(group_id: int | None, screen_name: str | None = None, entity_type: str | None = None) -> str:
    normalized_screen_name = _normalize_text(screen_name)
    if normalized_screen_name:
        return f"https://vk.com/{normalized_screen_name}"
    if group_id is None:
        return "https://vk.com"

    normalized_type = (entity_type or "").strip().lower()
    if normalized_type == "page":
        return f"https://vk.com/public{group_id}"
    return f"https://vk.com/club{group_id}"


def extract_profile_snapshot(user_data: dict[str, Any]) -> dict[str, Any]:
    """
    Собирает безопасный снимок полей профиля.

    Важно: часть полей VK API может отсутствовать в ответе из-за настроек приватности
    или особенностей конкретного аккаунта. Поэтому для необязательных полей мы
    сохраняем только те ключи, которые реально пришли от API.
    """
    if not isinstance(user_data, dict):
        return {}

    vk_id_raw = user_data.get("id")
    vk_id = vk_id_raw if isinstance(vk_id_raw, int) else None

    snapshot: dict[str, Any] = {
        "first_name": _normalize_text(user_data.get("first_name")) or "",
        "last_name": _normalize_text(user_data.get("last_name")) or "",
    }

    domain_value = _normalize_text(user_data.get("domain")) or _normalize_text(user_data.get("screen_name"))
    if "domain" in user_data or "screen_name" in user_data:
        snapshot["domain"] = domain_value

    if "is_closed" in user_data:
        snapshot["is_closed"] = "1" if bool(user_data.get("is_closed")) else "0"

    if "status" in user_data:
        snapshot["profile_status_text"] = _normalize_text(user_data.get("status"))

    if "photo_200_orig" in user_data:
        snapshot["avatar_url"] = _normalize_text(user_data.get("photo_200_orig"))

    if "photo_id" in user_data:
        snapshot["avatar_photo_id"] = _normalize_text(user_data.get("photo_id"))

    counters = user_data.get("counters")
    if "counters" in user_data:
        snapshot["friends_count"] = _extract_counter(counters, "friends")
        snapshot["subscriptions_count"] = _extract_counter(counters, "subscriptions")

        followers_count = _normalize_int(user_data.get("followers_count"))
        if followers_count is None:
            followers_count = _extract_counter(counters, "followers")
        snapshot["followers_count"] = followers_count
    elif "followers_count" in user_data:
        snapshot["followers_count"] = _normalize_int(user_data.get("followers_count"))

    optional_extractors: dict[str, Any] = {
        "city": _extract_location_title,
        "country": _extract_location_title,
        "about": _normalize_text,
        "bdate": _normalize_text,
        "relation": _normalize_relation,
        "site": _normalize_text,
        "interests": _normalize_text,
        "books": _normalize_text,
        "movies": _normalize_text,
        "activities": _normalize_text,
        "games": _normalize_text,
        "quotes": _normalize_text,
    }

    for field_name, extractor in optional_extractors.items():
        if field_name in user_data:
            snapshot[field_name] = extractor(user_data.get(field_name))

    snapshot["profile_link"] = build_profile_link(vk_id, domain_value)
    return snapshot


def format_profile_visibility(value: Any) -> str:
    if value is None or value == "":
        return "неизвестно"
    return "закрытый" if str(value) == "1" else "открытый"


def format_profile_field_value(field_name: str, value: Any) -> str:
    if field_name == "is_closed":
        return format_profile_visibility(value)
    if field_name == "profile_status_text":
        normalized = _normalize_text(value)
        return normalized if normalized is not None else "пусто"
    if field_name == "avatar_url":
        normalized = _normalize_text(value)
        return normalized if normalized is not None else "нет аватарки"
    if field_name in {"friends_count", "followers_count", "subscriptions_count"}:
        normalized_count = _normalize_int(value)
        if normalized_count is None:
            return "неизвестно"
        return str(normalized_count)
    normalized = _normalize_text(value)
    if normalized is None:
        return "не указано"
    return normalized


async def _call_vk_api(method_name: str, params: dict[str, Any]) -> dict[str, Any] | None:
    if not VK_ACCESS_TOKEN:
        logger.error("VK_ACCESS_TOKEN пустой или не загружен из config/.env")
        return None

    request_params = {
        **params,
        "access_token": VK_ACCESS_TOKEN,
        "v": VK_API_VERSION,
    }
    url = f"{VK_API_BASE}/{method_name}"

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(url, params=request_params, ssl=SSL_CONTEXT) as response:
                raw_text = await response.text()

                if response.status != 200:
                    logger.error(
                        "VK API вернул HTTP %s для %s. Ответ: %s",
                        response.status,
                        method_name,
                        raw_text[:1000],
                    )
                    return None

                try:
                    data = await response.json(content_type=None)
                except Exception as json_error:
                    logger.error(
                        "Не удалось разобрать JSON от VK API для %s: %s. Тело ответа: %s",
                        method_name,
                        json_error,
                        raw_text[:1000],
                    )
                    return None

        if not isinstance(data, dict):
            logger.error("VK API вернул неожиданный формат данных для %s: %r", method_name, data)
            return None

        if "error" in data:
            error = data["error"]
            logger.error(
                "VK API вернул ошибку %s для %s: %s",
                error.get("error_code"),
                method_name,
                error.get("error_msg"),
            )
            return None

        return data

    except aiohttp.ClientConnectorCertificateError as e:
        logger.error("Ошибка SSL-сертификата при подключении к VK API: %s", e)
        return None
    except aiohttp.ClientSSLError as e:
        logger.error("SSL-ошибка при запросе к VK API: %s", e)
        return None
    except aiohttp.ClientConnectorError as e:
        logger.error("Ошибка подключения к VK API: %s", e)
        return None
    except aiohttp.ClientError as e:
        logger.error("Ошибка HTTP-запроса к VK API: %s", e)
        return None
    except TimeoutError:
        logger.error("Таймаут запроса к VK API")
        return None
    except Exception as e:
        logger.exception("Неожиданная ошибка при запросе к VK API (%s): %s", method_name, e)
        return None


async def _call_vk_api_response(method_name: str, params: dict[str, Any]) -> Any:
    data = await _call_vk_api(method_name, params)
    if data is None:
        return None

    if "response" not in data:
        logger.error("VK API не вернул поле 'response' для %s. Ответ: %r", method_name, data)
        return None
    return data.get("response")


def _normalize_relation_entity(item: dict[str, Any], list_type: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    entity_id = _normalize_int(item.get("id"))
    if entity_id is None:
        return None

    raw_type = _normalize_text(item.get("type"))
    is_user = list_type in {RELATION_LIST_FRIENDS, RELATION_LIST_FOLLOWERS} or "first_name" in item

    if is_user or raw_type == "profile":
        screen_name = _normalize_text(item.get("domain")) or _normalize_text(item.get("screen_name"))
        first_name = _normalize_text(item.get("first_name")) or ""
        last_name = _normalize_text(item.get("last_name")) or ""
        name = f"{first_name} {last_name}".strip() or f"ID {entity_id}"
        return {
            "entity_type": "user",
            "entity_id": entity_id,
            "screen_name": screen_name,
            "first_name": first_name,
            "last_name": last_name,
            "title": None,
            "name": name,
            "profile_link": build_profile_link(entity_id, screen_name),
        }

    screen_name = _normalize_text(item.get("screen_name"))
    title = _normalize_text(item.get("name")) or f"ID {entity_id}"
    entity_type = raw_type or "group"
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "screen_name": screen_name,
        "first_name": None,
        "last_name": None,
        "title": title,
        "name": title,
        "profile_link": build_group_link(entity_id, screen_name, entity_type),
    }


def _too_large_relation_result(list_type: str, total_count: int) -> dict[str, Any]:
    return {
        "count": total_count,
        "items": [],
        "complete": False,
        "reason": (
            f"Список «{list_type}» слишком большой для точного сравнения через API "
            f"({total_count})."
        ),
    }


async def _get_paginated_relation_snapshot(
    *,
    method_name: str,
    list_type: str,
    vk_id: int,
    params: dict[str, Any],
    result_key: str = "items",
    expected_count: int | None = None,
) -> dict[str, Any]:
    max_items = RELATION_LIST_LIMITS[list_type]
    batch_size = RELATION_LIST_BATCH_SIZES[list_type]
    total_count = _normalize_int(expected_count) or 0

    if total_count > max_items:
        return _too_large_relation_result(list_type, total_count)

    collected_items: list[dict[str, Any]] = []
    offset = 0

    while True:
        response_data = await _call_vk_api_response(
            method_name,
            {
                **params,
                "user_id": vk_id,
                "count": batch_size,
                "offset": offset,
            },
        )
        if not isinstance(response_data, dict):
            return {
                "count": total_count or 0,
                "items": [],
                "complete": False,
                "reason": "VK API не отдал список или список скрыт настройками приватности.",
            }

        if total_count == 0:
            total_count = _normalize_int(response_data.get("count")) or 0
            if total_count > max_items:
                return _too_large_relation_result(list_type, total_count)

        raw_items = response_data.get(result_key, [])
        if not isinstance(raw_items, list):
            raw_items = []

        normalized_batch = []
        for raw_item in raw_items:
            normalized_item = _normalize_relation_entity(raw_item, list_type)
            if normalized_item is not None:
                normalized_batch.append(normalized_item)

        collected_items.extend(normalized_batch)
        offset += len(raw_items)

        if total_count == 0 or offset >= total_count or not raw_items:
            break

    unique_items: dict[tuple[str, int], dict[str, Any]] = {}
    for item in collected_items:
        unique_items[(str(item["entity_type"]), int(item["entity_id"]))] = item

    return {
        "count": total_count,
        "items": list(unique_items.values()),
        "complete": True,
        "reason": None,
    }


async def get_relation_snapshot(vk_id: int, list_type: str, expected_count: int | None = None) -> dict[str, Any]:
    """
    Возвращает снимок списка друзей / подписчиков / подписок.

    Если список слишком большой или недоступен через API, complete=False и будет
    заполнено reason. Это позволяет боту честно уведомлять пользователя о том,
    что точный аккаунт определить нельзя.
    """
    if list_type not in RELATION_LIST_TYPES:
        raise ValueError(f"Unsupported relation list type: {list_type}")

    if list_type == RELATION_LIST_FRIENDS:
        return await _get_paginated_relation_snapshot(
            method_name="friends.get",
            list_type=list_type,
            vk_id=vk_id,
            params={"fields": "domain,screen_name,first_name,last_name"},
            expected_count=expected_count,
        )

    if list_type == RELATION_LIST_FOLLOWERS:
        return await _get_paginated_relation_snapshot(
            method_name="users.getFollowers",
            list_type=list_type,
            vk_id=vk_id,
            params={"fields": "domain,screen_name,first_name,last_name"},
            expected_count=expected_count,
        )

    return await _get_paginated_relation_snapshot(
        method_name="users.getSubscriptions",
        list_type=list_type,
        vk_id=vk_id,
        params={"extended": 1, "fields": "domain,screen_name,first_name,last_name"},
        expected_count=expected_count,
    )


async def get_recent_wall_posts(vk_id: int, limit: int = 20) -> dict[str, Any]:
    """
    Возвращает последние записи со стены пользователя.

    Важно: сравнение строится по ограниченному числу последних постов.
    Это даёт надёжное отслеживание свежих публикаций, но не гарантирует
    обнаружение удаления очень старого поста, если он уже вышел за пределы окна.
    """
    normalized_limit = max(1, min(int(limit), WALL_POST_TRACK_LIMIT))
    response_data = await _call_vk_api_response(
        "wall.get",
        {
            "owner_id": vk_id,
            "count": normalized_limit,
            "filter": "owner",
        },
    )
    if not isinstance(response_data, dict):
        return {
            "count": 0,
            "items": [],
            "available": False,
            "reason": "VK API не отдал стену пользователя.",
        }

    raw_items = response_data.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        post_id = _normalize_int(item.get("id"))
        owner_id = _normalize_int(item.get("owner_id"))
        created_at = _normalize_int(item.get("date"))
        if post_id is None or owner_id is None:
            continue

        text_value = _normalize_text(item.get("text"))
        post_link = f"https://vk.com/wall{owner_id}_{post_id}"
        items.append(
            {
                "post_id": post_id,
                "owner_id": owner_id,
                "created_at": created_at,
                "text": text_value,
                "post_link": post_link,
            }
        )

    return {
        "count": _normalize_int(response_data.get("count")) or len(items),
        "items": items,
        "available": True,
        "reason": None,
    }


def format_timestamp(ts: int | None) -> str:
    """Форматирует Unix timestamp в строку МСК."""
    if ts is None:
        return "неизвестно"
    dt = datetime.fromtimestamp(ts, tz=MSK)
    return dt.strftime("%d.%m.%Y %H:%M:%S (МСК)")


def format_last_seen(last_seen_ts: int | None) -> str:
    """Форматирует время последнего визита в читаемую строку."""
    return format_timestamp(last_seen_ts)
