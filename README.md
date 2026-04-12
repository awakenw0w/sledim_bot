# VK Online Tracker Bot

Telegram-бот для отслеживания онлайн-статуса пользователей ВКонтакте.  
Бот опрашивает VK API каждые 30 секунд и отправляет уведомления, когда отслеживаемый пользователь входит в сеть или выходит из неё.

---

## Структура проекта

```
vk_tracker_bot/
├── bot.py           # Точка входа: запускает бота и фоновый трекер
├── config.py        # Конфигурация из .env
├── db.py            # Работа с SQLite (aiosqlite)
├── vk_api.py        # Запросы к VK API
├── tracker.py       # Фоновая задача проверки статусов
├── handlers.py      # Обработчики команд Telegram
├── requirements.txt # Python-зависимости
├── .env.example     # Шаблон переменных окружения
└── README.md        # Эта документация
```

---

## Быстрый старт

### 1. Клонирование и установка зависимостей

```bash
git clone <url-репозитория>
cd vk_tracker_bot

# Создаём и активируем виртуальное окружение
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate.bat    # Windows

# Устанавливаем зависимости
pip install -r requirements.txt
```

### 2. Получение токенов

#### Telegram Bot Token
1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot` и следуйте инструкциям
3. Скопируйте выданный токен

#### VK Access Token
Для получения **online-статуса** нужен токен пользователя (не сервисный ключ).

**Способ через vkhost.github.io (быстрый):**
1. Откройте [https://vkhost.github.io/](https://vkhost.github.io/)
2. Выберите **Kate Mobile** → нажмите **Получить**
3. Авторизуйтесь в VK, скопируйте `access_token` из адресной строки

**Способ через своё приложение:**
1. Создайте приложение на [vk.com/apps?act=manage](https://vk.com/apps?act=manage) (тип: Standalone)
2. Используйте Implicit Flow с правами `friends,offline`

### 3. Настройка .env

```bash
cp .env.example .env
```

Откройте `.env` и заполните:

```env
TELEGRAM_BOT_TOKEN=ваш_telegram_токен
VK_ACCESS_TOKEN=ваш_vk_токен
VK_API_VERSION=5.131
DB_PATH=bot_database.db
CHECK_INTERVAL=30
```

### 4. Запуск

```bash
python bot.py
```

При первом запуске бот автоматически создаст файл `bot_database.db` с нужными таблицами.

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и краткое описание |
| `/help` | Список всех команд и подсказки |
| `/add ID` | Добавить VK пользователя в список слежки |
| `/remove ID` | Убрать VK пользователя из списка |
| `/list` | Показать всех отслеживаемых с текущими статусами |
| `/status ID` | Узнать текущий статус конкретного пользователя |
| `/stop` | Приостановить уведомления |
| `/resume` | Возобновить уведомления |

---

## Как узнать VK ID

- Если у пользователя числовой адрес (`vk.com/id12345`) — это и есть ID
- Если адрес красивый (`vk.com/durov`) — откройте любое фото пользователя, в URL будет `owner_id=XXXXX`
- Используйте сервисы типа [vk.barkov.net](https://vk.barkov.net)

---

## Технологии

- **Python 3.11+**
- **aiogram 3.x** — асинхронный фреймворк для Telegram Bot API
- **aiohttp** — HTTP-клиент для запросов к VK API
- **aiosqlite** — асинхронная работа с SQLite
- **python-dotenv** — загрузка переменных из `.env`

---

## Ограничения VK API

- Онлайн-статус возвращается только для пользователей, у которых в настройках приватности разрешён просмотр статуса
- Пользователи с закрытым профилем могут не отображаться как онлайн, даже если они в сети
- VK API имеет лимит: ~3 запроса в секунду. Бот отправляет один батч-запрос раз в 30 секунд, что укладывается в лимиты даже при большом числе отслеживаемых пользователей

---

## Запуск в фоне (Linux, systemd)

Создайте файл `/etc/systemd/system/vk-tracker-bot.service`:

```ini
[Unit]
Description=VK Tracker Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/vk_tracker_bot
ExecStart=/path/to/vk_tracker_bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable vk-tracker-bot
sudo systemctl start vk-tracker-bot
sudo systemctl status vk-tracker-bot
```
