# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PresMaker is a Telegram bot that generates branded PowerPoint presentations using Claude AI. At the start of each session the bot asks which company the presentation is for, loads the matching brand config, and produces a `.pptx` file styled accordingly.

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run (requires env vars)
TELEGRAM_TOKEN=... ANTHROPIC_API_KEY=... python bot.py

# Or with a .env file
cp .env.example .env   # fill in values
python bot.py
```

For QA rendering (slide-to-PNG), LibreOffice and Poppler must be installed:
```bash
apt install libreoffice poppler-utils
```

Docker:
```bash
docker-compose up -d
docker-compose logs -f bot-acme
```

## Architecture

The bot follows a linear 5-stage pipeline per user session:

```
/start → company_select → Research → Preparation → Delivery → QA → .pptx file
```

**`bot.py`** — Entry point. Registers Telegram handlers, routes messages to `Pipeline.step()`. On `/start` resets session and lists available companies.

**`stages/session.py`** — In-memory `SessionStore` keyed by Telegram user ID. Initial stage is `company_select`. Session keys: `stage`, `brand`, `history`, `research_data`, `brief`, `slide_plan`, `pptx_path`, `qa_attempts`.

**`stages/pipeline.py`** — Orchestrator. Reads `session["stage"]` and dispatches to the appropriate stage. The `company_select` stage calls `find_brand(user_text)` and stores the matched `BrandConfig` in `session["brand"]`.

**`stages/research.py`** — Stage 1. Calls Claude to extract structured JSON (`topic`, `key_facts`, `data_for_charts`, `sections`) from user input or uploaded files (CSV, XLSX, TXT, JSON).

**`stages/preparation.py`** — Stage 2. Calls Claude to ask about audience/tone/slide count one question at a time, then produces a `slide_plan`. Waits for user confirmation ("да", "ок", etc.).

**`stages/delivery.py`** — Stage 3. Calls Claude to fill slide content, then builds the PPTX via `python-pptx`. Supported slide types: `title`, `content`, `chart`, `two_column`, `stats`, `closing`. Charts rendered to PNG via matplotlib.

**`stages/qa.py`** — Stage 4. Optionally renders slides to PNG via LibreOffice + pdftoppm, sends images to Claude Vision for inspection. Auto-passes if rendering tools unavailable.

**`brand/loader.py`** — Core brand module. Key functions:
- `load(path?)` — loads a YAML into a typed `BrandConfig`
- `list_brands()` — scans `brand/*.yaml`, returns `[(company_name, path)]`
- `find_brand(query)` — case-insensitive partial match against company names
- `brand` — global singleton (default fallback, loaded from `$BRAND_CONFIG` or `brand/config.yaml`)

**`brand/*.yaml`** — Each YAML file = one company's brand. Adding a new YAML automatically makes that company available for selection.

## Key Conventions

- **Brand per session**: All stages read `session["brand"]` (a `BrandConfig` instance). Never use the global `brand` singleton inside stage logic — it's only a fallback.
- **Adding a new company**: Create `brand/newcompany.yaml` based on `brand/config.yaml`. It becomes immediately available — no code changes needed.
- **Claude model**: All API calls use `claude-sonnet-4-20250514` with synchronous `client.messages.create()` (not async), despite stage methods being `async def`.
- **JSON extraction**: `research.py` and `preparation.py` each have a local `_extract_json()` that strips markdown fences and falls back to regex.
- **PPTX dimensions**: All slides are 13.33×7.5 inches (widescreen 16:9), blank layout (index 6).
- **Chart refs**: `slide_plan` entries of type `chart` reference `research_data["data_for_charts"]` by index via `chart_ref`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_TOKEN` | Yes | Telegram Bot API token |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `BRAND_CONFIG` | No | Path to default brand YAML (overrides `brand/config.yaml`) |
