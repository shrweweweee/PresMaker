# Presentation Bot 🎯

Корпоративный Telegram-бот для создания презентаций в фирменном стиле.
Стиль задаётся один раз в `brand/config.yaml` — пользователи не могут его менять.

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/your-org/pres-bot.git
cd pres-bot

# 2. Зависимости
pip install -r requirements.txt

# 3. Переменные окружения
cp .env.example .env
# Заполнить TELEGRAM_TOKEN и ANTHROPIC_API_KEY в .env

# 4. Настроить брендбук
# Отредактировать brand/config.yaml

# 5. Запуск
python bot.py
```

## Структура проекта

```
pres-bot/
├── brand/
│   ├── config.yaml         ← брендбук вашей компании (менять только здесь)
│   ├── techstartup.yaml    ← пример для форка
│   └── loader.py           ← загружает yaml в типизированный объект
├── stages/
│   ├── pipeline.py         ← оркестратор этапов
│   ├── research.py         ← этап 1: сбор и анализ данных
│   ├── preparation.py      ← этап 2: аудитория, тон, план слайдов
│   ├── delivery.py         ← этап 3: генерация PPTX + графики
│   ├── qa.py               ← этап 4: визуальная проверка
│   └── session.py          ← хранение состояния диалога
├── bot.py                  ← точка входа, Telegram handlers
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Procfile                ← для Railway / Render
└── .env.example
```

## Как работает бот

```
Пользователь → Research → Preparation → Delivery → QA → файл .pptx
```

**Research** — извлекает факты и данные для графиков из текста или прикреплённого файла (CSV, XLSX, TXT).

**Preparation** — уточняет аудиторию, тон, количество слайдов. Показывает план и ждёт подтверждения.

**Delivery** — заполняет слайды контентом через Claude, рисует графики в цветах брендбука, собирает PPTX.

**QA** — рендерит слайды в PNG, проверяет визуальное качество через Claude Vision.

## Настройка брендбука

Все параметры стиля находятся в `brand/config.yaml`:

```yaml
company:
  name: "Acme Corp"
  language: "ru"
  tone: "formal"

colors:
  primary:   "1A3C6E"   # шапки слайдов
  accent:    "E8612A"   # выделения, графики
  chart_palette:
    - "1A3C6E"
    - "E8612A"

typography:
  font_heading: "Calibri"
  font_body:    "Calibri"

logo:
  url: "https://..."    # PNG логотипа

agent:
  company_context: |
    Описание компании для Claude — продукт, метрики, аудитории.
```

Полное описание всех параметров — в комментариях `brand/config.yaml`.

## Форк для другой компании

```bash
# Вариант 1 — новый yaml файл
cp brand/config.yaml brand/newcompany.yaml
# отредактировать newcompany.yaml
BRAND_CONFIG=brand/newcompany.yaml python bot.py

# Вариант 2 — отдельная ветка Git
git checkout -b client/newcompany
# отредактировать brand/config.yaml
git commit -m "brand: NewCompany"
```

Несколько ботов на одном сервере:
```bash
docker-compose up -d
# Раскомментируйте второй сервис в docker-compose.yml
```

## Деплой

### Railway (рекомендуется для старта)
1. Подключить репозиторий на [railway.app](https://railway.app)
2. Добавить переменные: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`, `BRAND_CONFIG`
3. Deploy автоматически при каждом пуше в ветку

### Docker (VPS)
```bash
docker-compose up -d
docker-compose logs -f bot-acme
```

### Ручной запуск
```bash
# Установить LibreOffice и Poppler для QA
apt install libreoffice poppler-utils

source .env
python bot.py
```

## Команды бота

| Команда | Действие |
|---------|----------|
| `/start` | Приветствие (текст из config.yaml) |
| `/brand` | Показать активный брендбук |
| `/reload` | Перезагрузить config.yaml без рестарта |
| `/reset` | Сбросить текущую сессию |

## Зависимости

- `python-telegram-bot` — Telegram Bot API
- `anthropic` — Claude API (генерация контента + QA Vision)
- `python-pptx` — создание PPTX файлов
- `matplotlib` — графики в корпоративных цветах
- `pyyaml` — загрузка брендбука
- LibreOffice + Poppler — рендер слайдов для QA (опционально)
