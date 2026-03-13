"""Этап 2: Preparation — уточняет аудиторию, тон, план слайдов."""
import os, json, re
import anthropic
from stages.onboarding import _parse_file

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_ICONS = {"title":"🏷","content":"📄","chart":"📊",
          "two_column":"📰","quote":"💬","stats":"📈","closing":"🏁"}


def _make_system(brand) -> str:
    defaults = brand.slide_defaults
    return f"""
Ты — продюсер презентаций компании {brand.company_name}.
Тон по умолчанию: {brand.tone}. Язык: {brand.language}.
Слайдов по умолчанию: {defaults.count}.
Обязательные типы слайдов: {', '.join(defaults.always_include)}.

## Режим работы

Задавай по ОДНОМУ вопросу пока не узнаешь: аудиторию, тон, количество слайдов.
Предлагай дефолты: «{defaults.count} слайдов — подойдёт?»

Когда информации достаточно или пользователь подтвердил — верни JSON-план:

```json
{{
  "brief": {{
    "audience": "совет директоров",
    "tone": "{brand.tone}",
    "slide_count": {defaults.count},
    "language": "{brand.language}",
    "confirmed": true
  }},
  "slide_plan": [
    {{"id": 1, "type": "title",   "title": "..."}},
    {{"id": 2, "type": "content", "title": "Повестка"}},
    {{"id": 3, "type": "content", "title": "..."}},
    {{"id": 4, "type": "chart",   "title": "...", "chart_ref": 0}},
    {{"id": 5, "type": "stats",   "title": "Ключевые показатели"}},
    {{"id": 6, "type": "closing", "title": "Следующие шаги"}}
  ]
}}
```

Типы: title · content · chart · two_column · quote · stats · closing
Не задавай больше одного вопроса. JSON — без лишних слов.
"""


class PreparationStage:

    async def start(self, session) -> dict:
        brand = session["brand"]
        research = session["research_data"]
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=800,
            system=_make_system(brand),
            messages=[{"role":"user","content":(
                f"Research готов. Тема: {research.get('topic','')}\n"
                f"Данные: {json.dumps(research, ensure_ascii=False)[:800]}\n\nНачни уточнение."
            )}],
        )
        text = resp.content[0].text.strip()
        data = _extract_json(text)
        if data and "brief" in data:
            return await self._show_plan(session, data)
        return {"type": "message", "text": text}

    async def run(self, session, user_text, file_bytes=None, file_name=None) -> dict:
        brand = session["brand"]
        confirm = {"да","ок","окей","верно","давай","поехали","go","yes","ok","угу","ага"}
        if any(w in user_text.lower() for w in confirm) and session.get("slide_plan"):
            return {"done": True, "brief": {
                "brief": session["brief"],
                "slide_plan": session["slide_plan"],
            }}

        if file_bytes and file_name:
            parsed = _parse_file(file_bytes, file_name)
            file_context = f"\n\n[Файл: {file_name}]\n{parsed}"
            # Update last history entry to include file content
            if session["history"] and session["history"][-1]["role"] == "user":
                session["history"][-1]["content"] += file_context

        research = session["research_data"]
        research_ctx = f"Research: {json.dumps(research, ensure_ascii=False)[:600]}"
        # Build messages ensuring alternating user/assistant roles
        messages = [{"role": "user", "content": research_ctx}]
        for entry in session["history"][-6:]:
            if messages[-1]["role"] == entry["role"]:
                messages[-1]["content"] += "\n\n" + entry["content"]
            else:
                messages.append(dict(entry))
        # Ensure last message is user role
        if messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": "Продолжай."})
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=1200,
            system=_make_system(brand),
            messages=messages,
        )
        text = resp.content[0].text.strip()
        data = _extract_json(text)
        if data and "brief" in data:
            return await self._show_plan(session, data)
        return {"done": False, "message": text}

    async def _show_plan(self, session, data) -> dict:
        brand = session["brand"]
        session["brief"]      = data["brief"]
        session["slide_plan"] = data["slide_plan"]

        lines = [f"📋 *План для {brand.company_name}:*\n"]
        for s in data["slide_plan"]:
            icon = _ICONS.get(s.get("type","content"), "▸")
            lines.append(f"{icon} {s['id']}. {s['title']}")

        b = data["brief"]
        lines += [
            f"\n👥 Аудитория: {b.get('audience','—')}",
            f"🎯 Тон: {b.get('tone','—')}",
            f"📑 Слайдов: {b.get('slide_count', len(data['slide_plan']))}",
            "\nВсё верно? Напишите *да* или попросите изменить.",
        ]
        return {"done": False, "message": "\n".join(lines)}


def _extract_json(text):
    text = re.sub(r"^```(?:json)?\s*","",text.strip())
    text = re.sub(r"\s*```$","",text)
    try: return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}",text,re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except Exception: pass
    return None
