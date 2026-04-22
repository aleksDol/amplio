# Amplio Bot

Telegram-бот для работы с подборками каналов.

## Стек

- Python 3.12
- aiogram
- PostgreSQL 16
- Docker Compose

## Быстрый старт (Docker)

1. Скопируй шаблон окружения:

```powershell
Copy-Item .env.production.example .env.production
```

2. Заполни `.env.production` (минимум: `BOT_TOKEN`, `POSTGRES_PASSWORD`, `ADMIN_TELEGRAM_IDS`).

3. Запусти:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up --build
```

## Полезные команды

Запуск в фоне:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Логи:

```powershell
docker compose -f docker-compose.prod.yml logs -f bot
```

Остановка:

```powershell
docker compose -f docker-compose.prod.yml down
```

## Подготовка к GitHub

- Файл `.env.production` не должен попадать в репозиторий.
- Для примеров используй `.env.example` или `.env.production.example`.

