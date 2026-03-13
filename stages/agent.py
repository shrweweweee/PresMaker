"""
Agent loop: единый Claude-разговор с tool_use.
Заменяет research, preparation, content_fill, content_review.
"""
from __future__ import annotations
import os, io, json, logging
import anthropic
from pathlib import Path

from brand.loader import load as load_brand, BrandConfig, _BRAND_DIR
from stages.tools import TOOL_DEFINITIONS
from stages.delivery import DeliveryBuildStage
from stages.qa import QAStage

log = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_delivery = DeliveryBuildStage()
_qa = QAStage()

# ── Icons ───────────────────────────────────────────────────────────────────
_SLIDE_ICONS = {
    "title": "\U0001f3f7", "content": "\U0001f4c4", "chart": "\U0001f4ca",
    "two_column": "\U0001f4f0", "stats": "\U0001f4c8", "closing": "\U0001f3c1",
}

# ── YAML template (from onboarding.py) ──────────────────────────────────────
_YAML_TEMPLATE = """\
company:
  name: "{name}"
  slug: "{slug}"
  theme_name: "{theme_name}"
  tagline: "{tagline}"
  language: "{language}"
  tone: "{tone}"
  description: "{description}"

colors:
  primary:       "{primary_color}"
  accent:        "{accent_color}"
  bg_light:      "#FFFFFF"
  bg_dark:       "#1A1A2E"
  text_dark:     "#1A1A2E"
  text_muted:    "#64748B"
  success:       "#22C55E"
  danger:        "#EF4444"
  chart_palette: ["{primary_color}", "{accent_color}", "#64748B", "#22C55E"]

typography:
  font_heading: "Calibri"
  font_body:    "Calibri"
  size_title:   40
  size_heading: 28
  size_section: 22
  size_body:    18
  size_caption: 12

logo:
  url:          ""
  position:     "bottom-right"
  width_inches: 1.4

slide_defaults:
  count:          10
  always_include: ["title", "closing"]
  footer_text:    "{name}"
  slide_numbers:  true

agent:
  welcome_message: "Привет! Напишите тему презентации для {name}."
  company_context: "{description}"
  forbidden_topics: []
"""


# ── System prompt builder ───────────────────────────────────────────────────

def build_system_prompt(brand: BrandConfig, onboarding: bool = False) -> str:
    """Build system prompt for the agent loop."""
    defaults = brand.slide_defaults
    always = ", ".join(defaults.always_include) if defaults.always_include else "title, closing"

    prompt = f"""\
Ты — ассистент по созданию презентаций для {brand.company_name}.
{brand.agent.company_context}
Язык: {brand.language}. Тон: {brand.tone}.

## Процесс работы

1. **Исследование**: Собери информацию из сообщений/файлов пользователя. Когда данных достаточно — вызови save_research.
2. **Планирование**: Уточни аудиторию и тон (по одному вопросу). Количество слайдов НЕ спрашивай — используй дефолт: {defaults.count}. Когда готово — вызови propose_slide_plan. Жди подтверждения.
3. **Наполнение**: После подтверждения плана — вызови fill_slides со всем контентом. Жди подтверждения или правок.
4. **Правки**: Если пользователь просит изменения — вызови edit_slides с обновлённым массивом.
5. **Сборка**: Когда пользователь подтвердил контент — вызови build_presentation.

## Типы слайдов
- title: {{id, type, title, subtitle}}
- content: {{id, type, title, content: [{{type: bullet|highlight, text}}], speaker_notes}}
- chart: {{id, type, title, chart_ref}} (chart_ref — индекс в data_for_charts)
- two_column: {{id, type, title, left: {{heading, items}}, right: {{heading, items}}}}
- stats: {{id, type, title, stats: [{{label, value, trend}}]}}
- closing: {{id, type, title, content: [{{type: bullet, text}}]}}

Обязательные типы: {always}. 4-6 буллетов на content-слайд.
Включай data_for_charts когда есть цифры/динамика/сравнения. kind: bar|line|pie|doughnut.

## Правила
- Задавай по ОДНОМУ вопросу за раз.
- Всегда используй tools для сохранения данных.
- Если пользователь прикрепил файл — используй его содержимое.
"""
    if onboarding:
        prompt = (
            "Пользователь хочет создать презентацию для неизвестной компании.\n"
            "Спроси о компании и стиле, затем вызови register_company.\n"
            "После регистрации продолжай обычный процесс.\n\n"
        ) + prompt
    return prompt


# ── File parser (consolidated from onboarding.py) ──────────────────────────

def parse_file(file_bytes: bytes, file_name: str) -> str:
    name = file_name.lower()
    try:
        if name.endswith((".txt", ".md")):
            return file_bytes.decode("utf-8", errors="replace")[:4000]
        if name.endswith(".csv"):
            import csv
            rows = list(csv.reader(io.StringIO(file_bytes.decode("utf-8", errors="replace"))))
            return "\n".join("\t".join(r) for r in rows[:50])
        if name.endswith((".xlsx", ".xls")):
            import pandas as pd
            return pd.read_excel(io.BytesIO(file_bytes)).head(30).to_string()
        if name.endswith(".json"):
            return file_bytes.decode("utf-8", errors="replace")[:4000]
        if name.endswith(".pdf"):
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                return "\n".join(p.extract_text() or "" for p in reader.pages[:10])[:4000]
            except ImportError:
                return "[PDF не поддерживается: установите pypdf]"
        if name.endswith(".docx"):
            try:
                from docx import Document
                doc = Document(io.BytesIO(file_bytes))
                return "\n".join(p.text for p in doc.paragraphs)[:4000]
            except ImportError:
                return "[DOCX не поддерживается: установите python-docx]"
    except Exception as e:
        return f"[Ошибка чтения файла: {e}]"
    return f"[Формат {file_name} не поддерживается]"


# ── Preview formatters ──────────────────────────────────────────────────────

def _format_plan_preview(brief: dict, slide_plan: list, brand: BrandConfig) -> str:
    lines = [f"\U0001f4cb *План для {brand.company_name}:*\n"]
    for s in slide_plan:
        icon = _SLIDE_ICONS.get(s.get("type", "content"), "\u25b8")
        lines.append(f"{icon} {s['id']}. {s['title']}")
    dash = "\u2014"
    audience = brief.get("audience", dash)
    tone = brief.get("tone", dash)
    count = brief.get("slide_count", len(slide_plan))
    lines += [
        f"\n\U0001f465 Аудитория: {audience}",
        f"\U0001f3af Тон: {tone}",
        f"\U0001f4d1 Слайдов: {count}",
        "\nВсё верно? Напишите *да* или попросите изменить.",
    ]
    return "\n".join(lines)


def _format_slides_preview(slides: list) -> str:
    lines = ["*Предпросмотр слайдов:*\n"]
    for s in slides:
        t = s.get("type", "content")
        icon = _SLIDE_ICONS.get(t, "\u25b8")
        idx = s.get("id", "?")
        title = s.get("title", "")
        lines.append(f'{icon} Слайд {idx} ({t}): "{title}"')
        if t == "title" and s.get("subtitle"):
            lines.append(f"  Подзаголовок: {s['subtitle']}")
        elif t in ("content", "closing"):
            for item in s.get("content", [])[:4]:
                lines.append(f"  \u2022 {item.get('text', '')}")
        elif t == "chart":
            lines.append(f"  [График #{s.get('chart_ref', 0)}]")
        elif t == "two_column":
            lh = s.get("left", {}).get("heading", "")
            rh = s.get("right", {}).get("heading", "")
            if lh or rh:
                lines.append(f"  {lh} | {rh}")
        elif t == "stats":
            for st in s.get("stats", [])[:3]:
                lines.append(f"  {st.get('label','')}: {st.get('value','')} {st.get('trend','')}")
        lines.append("")
    lines.append("Всё верно? Напишите *создавай* или укажите правки (например: «слайд 3: добавь про безопасность»)")
    return "\n".join(lines)


# ── Message trimmer ─────────────────────────────────────────────────────────

def _trim_messages(messages: list, max_pairs: int = 12):
    """Keep first user message + last N message pairs.

    Never cut between an assistant tool_use and its following user tool_result —
    the API requires every tool_result to have a matching tool_use in the
    immediately preceding assistant message.
    """
    if len(messages) <= max_pairs * 2 + 1:
        return

    # Find safe cut points — indices where we can split without breaking
    # a tool_use / tool_result pair.  A cut is unsafe right after an
    # assistant message whose content contains tool_use blocks (because
    # the next message will hold tool_results that reference them).
    target_start = len(messages) - max_pairs * 2
    cut = target_start
    # Walk forward from target_start to find the nearest safe point
    while cut < len(messages) - 1:
        prev = messages[cut - 1] if cut > 0 else None
        if prev and prev.get("role") == "assistant" and _has_tool_use(prev):
            cut += 1  # skip — can't cut here, would orphan tool_results
            continue
        # Also unsafe if cut itself is a tool_result message
        cur = messages[cut]
        if cur.get("role") == "user" and _has_tool_result(cur):
            cut += 1
            continue
        break

    if cut >= len(messages) - 1:
        # Can't trim safely — just truncate large payloads
        cut = 1  # keep only the very first message

    keep_first = messages[:1]
    keep_last = messages[cut:]
    messages.clear()
    messages.extend(keep_first + keep_last)

    # Truncate large tool_result payloads
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, str) and len(content) > 500:
                        block["content"] = content[:500] + "… [обрезано]"


def _has_tool_use(msg: dict) -> bool:
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_use"
        for b in content
    )


def _has_tool_result(msg: dict) -> bool:
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_result"
        for b in content
    )


# ── Extract text from response ──────────────────────────────────────────────

def _extract_text(resp) -> str:
    parts = []
    for block in resp.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


# ── Tool handlers ───────────────────────────────────────────────────────────

async def _handle_register_company(session: dict, inp: dict) -> dict:
    slug = inp["slug"]
    theme_name = inp.get("theme_name", "default")

    if theme_name != "default":
        file_slug = f"{slug}_{theme_name}"
    else:
        file_slug = slug

    yaml_path = _BRAND_DIR / f"{file_slug}.yaml"
    yaml_content = _YAML_TEMPLATE.format(
        name=inp["company_name"],
        slug=slug,
        theme_name=theme_name,
        tagline=inp.get("tagline", ""),
        language=inp.get("language", "ru"),
        tone=inp.get("tone", "formal"),
        description=inp.get("description", ""),
        primary_color=inp["primary_color"],
        accent_color=inp["accent_color"],
    )
    yaml_path.write_text(yaml_content, encoding="utf-8")
    brand = load_brand(yaml_path)
    session["brand"] = brand
    session["system_prompt"] = build_system_prompt(brand)
    return {"content": f"Компания «{brand.company_name}» зарегистрирована. Бренд загружен. Продолжай обычный процесс."}


async def _handle_save_research(session: dict, inp: dict) -> dict:
    session["research_data"] = inp
    return {"content": "Данные исследования сохранены."}


async def _handle_propose_slide_plan(session: dict, inp: dict) -> dict:
    session["brief"] = inp["brief"]
    session["slide_plan"] = inp["slide_plan"]
    brand = session["brand"]
    preview = _format_plan_preview(inp["brief"], inp["slide_plan"], brand)
    return {
        "content": "План показан пользователю. Жди ответа.",
        "user_message": {"type": "message", "text": preview},
    }


async def _handle_fill_slides(session: dict, inp: dict) -> dict:
    session["filled_slides"] = inp["slides"]
    preview = _format_slides_preview(inp["slides"])
    return {
        "content": "Предпросмотр показан пользователю. Жди ответа.",
        "user_message": {"type": "message", "text": preview},
    }


async def _handle_edit_slides(session: dict, inp: dict) -> dict:
    session["filled_slides"] = inp["slides"]
    preview = _format_slides_preview(inp["slides"])
    return {
        "content": "Обновлённый предпросмотр показан пользователю. Жди ответа.",
        "user_message": {"type": "message", "text": preview},
    }


async def _handle_build_presentation(session: dict, inp: dict) -> dict:
    path, meta = await _delivery.run(session)
    session["pptx_path"] = path
    session["pptx_meta"] = meta

    qa_result = await _qa.start(session)
    if qa_result.get("approved"):
        return {
            "content": "Презентация собрана и прошла QA.",
            "user_message": {"type": "file", **qa_result["file"]},
        }

    # QA found issues — report back to Claude
    issues = qa_result.get("message", "")
    return {
        "content": f"Презентация собрана, но QA нашла замечания:\n{issues}\n\nФайл всё равно отправлен пользователю.",
        "user_message": {"type": "file", **_qa_file_result(session)},
    }


def _qa_file_result(session: dict) -> dict:
    """Fallback file result when QA has issues but we still send the file."""
    import re
    brand = session["brand"]
    meta = session.get("pptx_meta", {})
    title = meta.get("title", brand.company_name)
    n = meta.get("slides", "?")
    safe = re.sub(r"[^\w\s-]", "", title)[:40].strip()
    return {
        "path": session["pptx_path"],
        "filename": f"{safe}.pptx",
        "caption": f"«{title}» — {n} слайдов · {brand.company_name}",
    }


# ── Tool dispatch ───────────────────────────────────────────────────────────

_HANDLERS = {
    "register_company": _handle_register_company,
    "save_research": _handle_save_research,
    "propose_slide_plan": _handle_propose_slide_plan,
    "fill_slides": _handle_fill_slides,
    "edit_slides": _handle_edit_slides,
    "build_presentation": _handle_build_presentation,
}


# ── Agent Loop ──────────────────────────────────────────────────────────────

PAUSE_TOOLS = {"propose_slide_plan", "fill_slides", "edit_slides"}


class AgentLoop:

    async def run(
        self,
        session: dict,
        user_text: str,
        file_bytes: bytes | None = None,
        file_name: str | None = None,
    ) -> dict:
        # Build user content
        content = user_text or ""
        if file_bytes and file_name:
            parsed = parse_file(file_bytes, file_name)
            content = f"{content}\n\n[Файл: {file_name}]\n{parsed}"

        session["messages"].append({"role": "user", "content": content})
        _trim_messages(session["messages"])

        for _ in range(10):  # safety limit
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=5000,
                system=session["system_prompt"],
                messages=session["messages"],
                tools=TOOL_DEFINITIONS,
            )

            # Append assistant response
            # Convert content blocks to serialisable dicts
            assistant_content = []
            for block in resp.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            session["messages"].append({"role": "assistant", "content": assistant_content})

            # Text-only response → return to user
            if resp.stop_reason == "end_turn":
                return {"type": "message", "text": _extract_text(resp)}

            # Execute tool calls
            tool_results = []
            pause_message = None
            file_result = None

            for block in resp.content:
                if block.type != "tool_use":
                    continue
                handler = _HANDLERS.get(block.name)
                if not handler:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Unknown tool: {block.name}",
                        "is_error": True,
                    })
                    continue

                try:
                    result = await handler(session, block.input)
                except Exception as e:
                    log.exception(f"Tool {block.name} failed")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Ошибка: {e}",
                        "is_error": True,
                    })
                    continue

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result["content"],
                })

                if result.get("user_message"):
                    um = result["user_message"]
                    if um.get("type") == "file":
                        file_result = um
                    else:
                        pause_message = um

            session["messages"].append({"role": "user", "content": tool_results})

            # File result takes priority (build_presentation)
            if file_result:
                return file_result
            # Pause tools → return message to user, wait for next input
            if pause_message:
                return pause_message
            # Continue loop — Claude sees tool results and decides next step

        return {"type": "message", "text": "\u26a0\ufe0f Превышен лимит итераций."}
