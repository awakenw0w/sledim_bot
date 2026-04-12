"""
Одноразовый скрипт для получения строковой user-session Telethon.

Использование:
1. Заполните в .env переменные TELEGRAM_USERBOT_API_ID и TELEGRAM_USERBOT_API_HASH.
2. Запустите:
   python generate_telegram_userbot_session.py
3. Введите номер телефона, код из Telegram и пароль 2FA, если он включен.
4. Скопируйте напечатанное значение в TELEGRAM_USERBOT_SESSION.
"""

import asyncio
import builtins
import getpass
import sys

from telethon import TelegramClient
from telethon.errors import PasswordHashInvalidError, PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.sessions import StringSession

from config import TELEGRAM_USERBOT_API_HASH, TELEGRAM_USERBOT_API_ID


def _read_input(prompt: str) -> str:
    """
    Безопасно читает строку из stdin.
    В некоторых средах запуска input() может вернуть None вместо строки,
    поэтому добавляем явный fallback на sys.stdin.readline().
    """
    value = builtins.input(prompt)
    if value is None:
        print(prompt, end="", flush=True)
        value = sys.stdin.readline()

    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(
            "Не удалось прочитать ввод из консоли. Запустите скрипт в обычном терминале и введите значение вручную."
        )
    return normalized


async def main() -> None:
    if TELEGRAM_USERBOT_API_ID is None or not TELEGRAM_USERBOT_API_HASH:
        raise ValueError(
            "Заполните TELEGRAM_USERBOT_API_ID и TELEGRAM_USERBOT_API_HASH в .env перед запуском."
        )

    client = TelegramClient(StringSession(), TELEGRAM_USERBOT_API_ID, TELEGRAM_USERBOT_API_HASH)
    await client.connect()

    try:
        if not await client.is_user_authorized():
            phone = _read_input("Введите номер телефона в формате +79991234567: ")
            await client.send_code_request(phone)
            code = _read_input("Введите код из Telegram: ")

            try:
                await client.sign_in(phone=phone, code=code)
            except PhoneCodeInvalidError as exc:
                raise ValueError("Введен неверный код подтверждения Telegram.") from exc
            except SessionPasswordNeededError:
                # Если включен пароль 2FA, Telethon попросит завершить вход через password.
                password = getpass.getpass("Введите пароль двухфакторной аутентификации Telegram: ").strip()
                try:
                    await client.sign_in(password=password)
                except PasswordHashInvalidError as password_exc:
                    raise ValueError("Введен неверный пароль двухфакторной аутентификации Telegram.") from password_exc

        session_string = client.session.save()
        print("\nСохраните это значение в .env:")
        print(f"TELEGRAM_USERBOT_SESSION={session_string}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
