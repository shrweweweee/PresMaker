# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PresMaker is a Telegram bot that generates branded PowerPoint presentations using Claude AI. Users describe their topic via Telegram, and the bot produces a `.pptx` file styled according to a company brandbook (`brand/config.yaml`).

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run (requires env vars)
TELEGRAM_TOKEN=... ANTHROPIC_API_KEY=... python bot.py

# Use alternate brandbook
BRAND_CONFIG=brand/techstartup.yaml python bot.py
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

The bot follows a linear 4-stage pipeline per user session:

```
User message → Research → Preparation → Delivery → QA → .pptx file
```

**`bot.py`** — Entry point. Registers Telegram handlers, routes messages to `Pipeline.step()`, handles file uploads and callback buttons.

**`stages/session.py`** — In-memory `SessionStore` keyed by Telegram user ID. Each session tracks: `stage`, `history`, `research_data`, `brief`, `slide_plan`, `pptx_path`, `qa_attempts`.

**`stages/pipeline.py`** — Orchestrator. Reads `session["stage"]` and dispatches to the appropriate stage. Automatically advances stages on completion.

**`stages/research.py`** — Stage 1. Calls Claude to extract structured JSON (`topic`, `key_facts`, `data_for_charts`, `sections`) from user input or uploaded files (CSV, XLSX, TXT, JSON). Asks a clarifying question if input is too short.

**`stages/preparation.py`** — Stage 2. Calls Claude to ask about audience/tone/slide count (one question at a time), then produces a `slide_plan` (ordered list of slide specs with type and title). Waits for user confirmation ("да", "ок", etc.).

**`stages/delivery.py`** — Stage 3. Calls Claude to fill slide content, then builds the PPTX via `python-pptx`. Supported slide types: `title`, `content`, `chart`, `two_column`, `stats`, `closing`. Charts are rendered to PNG via matplotlib using brand colors.

**`stages/qa.py`** — Stage 4. Optionally renders slides to PNG via LibreOffice + pdftoppm, then sends images to Claude Vision for quality inspection. Passes through automatically if rendering tools are unavailable.

**`brand/loader.py`** — Loads `brand/config.yaml` (or `$BRAND_CONFIG`) into a typed `BrandConfig` singleton at import time. All stages import `brand` from here — never pass brand state through arguments. Hot-reload via `/reload` bot command calls `reload()`.

**`brand/config.yaml`** — Single source of truth for all visual/style parameters: colors (HEX), typography, logo URL, slide defaults, and agent behavior (welcome message, company context for Claude prompts).

## Key Conventions

- **Brand singleton**: All modules do `from brand.loader import brand` and read brand properties directly. The singleton is mutable via `reload()`.
- **Claude model**: All API calls use `claude-sonnet-4-20250514` with synchronous `client.messages.create()` (not async), despite the stage methods being `async def`.
- **JSON extraction**: Both `research.py` and `preparation.py` include a local `_extract_json()` helper that strips markdown fences and falls back to regex for JSON extraction from Claude responses.
- **PPTX dimensions**: All slides are 13.33×7.5 inches (widescreen 16:9), built on blank layout (index 6).
- **Chart refs**: `slide_plan` entries of type `chart` reference `research_data["data_for_charts"]` by index via `chart_ref`.
- **QA fallback**: If LibreOffice/pdftoppm are unavailable, `_render_to_png()` returns `[]` and QA auto-approves.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_TOKEN` | Yes | Telegram Bot API token |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `BRAND_CONFIG` | No | Path to alternate brandbook YAML (default: `brand/config.yaml`) |
