"""
Этап content_fill: заполняет слайды контентом через Claude.
Этап content_review: показывает предпросмотр и принимает правки.
"""
import os, json, re
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_ICONS = {
    "title": "🏷", "content": "📄", "chart": "📊",
    "two_column": "📰", "quote": "💬", "stats": "📈", "closing": "🏁",
}


def _make_content_system(brand) -> str:
    return f"""
Ты заполняешь слайды контентом для компании {brand.company_name}.
Язык: {brand.language}. Тон: {brand.tone}.
{brand.agent.company_context}

Верни ТОЛЬКО JSON-массив слайдов с заполненным контентом.

Форматы:
- content: {{"id":N,"type":"content","title":"...","content":[{{"type":"bullet","text":"..."}},{{"type":"highlight","text":"ключевой тезис"}}],"speaker_notes":"..."}}
- chart:   {{"id":N,"type":"chart","title":"...","chart_ref":0}}
- two_column: {{"id":N,"type":"two_column","title":"...","left":{{"heading":"До","items":["..."]}}, "right":{{"heading":"После","items":["..."]}}}}
- stats:   {{"id":N,"type":"stats","title":"...","stats":[{{"label":"Выручка","value":"₽2.4 млрд","trend":"+18%"}}]}}
- title:   {{"id":1,"type":"title","title":"...","subtitle":"..."}}
- closing: {{"id":N,"type":"closing","title":"Спасибо!","content":[{{"type":"bullet","text":"контакт"}}]}}

4-6 буллетов на content-слайд. Только JSON, без обёрток.
"""


def _format_preview(slides: list) -> str:
    lines = ["*Предпросмотр слайдов:*\n"]
    for s in slides:
        t = s.get("type", "content")
        icon = _ICONS.get(t, "▸")
        idx = s.get("id", "?")
        title = s.get("title", "")
        lines.append(f"{icon} Слайд {idx} ({t}): \"{title}\"")
        if t == "title" and s.get("subtitle"):
            lines.append(f"  Подзаголовок: {s['subtitle']}")
        elif t in ("content", "closing"):
            for item in s.get("content", [])[:4]:
                lines.append(f"  • {item.get('text', '')}")
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


def _extract_json_list(text: str) -> list | None:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            if isinstance(result, list):
                return result
        except Exception:
            pass
    return None


class ContentFillStage:

    async def run(self, session) -> dict:
        brand      = session["brand"]
        research   = session["research_data"]
        brief      = session.get("brief", {})
        slide_plan = session.get("slide_plan", [])
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=5000,
            system=_make_content_system(brand),
            messages=[{"role": "user", "content": (
                f"Research:\n{json.dumps(research, ensure_ascii=False)}\n\n"
                f"Бриф: {json.dumps(brief, ensure_ascii=False)}\n\n"
                f"План: {json.dumps(slide_plan, ensure_ascii=False)}"
            )}],
        )
        text = resp.content[0].text.strip()
        slides = _extract_json_list(text) or slide_plan
        session["filled_slides"] = slides
        session["stage"] = "content_review"
        return {"type": "message", "text": _format_preview(slides)}


class ContentReviewStage:

    async def run(self, session, user_text: str) -> dict:
        confirm = {"создавай", "да", "ок", "верно", "yes", "ok", "поехали", "готово"}
        if any(w in user_text.lower() for w in confirm):
            session["stage"] = "delivery_build"
            return {"done": True}
        edited = await self._apply_edit(session, user_text)
        session["filled_slides"] = edited
        return {"type": "message", "text": _format_preview(edited)}

    async def _apply_edit(self, session, instruction: str) -> list:
        slides = session["filled_slides"]
        brand  = session["brand"]
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=5000,
            system=(
                f"Ты редактируешь слайды для компании {brand.company_name}. "
                f"Язык: {brand.language}.\n"
                "Применяй правку точно. Верни ПОЛНЫЙ обновлённый JSON-массив (все слайды), без обёрток."
            ),
            messages=[{"role": "user", "content": (
                f"Текущие слайды:\n{json.dumps(slides, ensure_ascii=False)}\n\n"
                f"Правка: {instruction}"
            )}],
        )
        text = resp.content[0].text.strip()
        return _extract_json_list(text) or slides
