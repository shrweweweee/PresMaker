"""Этап 1: Research — сбор и структурирование данных."""
import os, json, re, io
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _make_system(brand) -> str:
    return f"""
Ты — исследователь-аналитик для компании {brand.company_name}.
{brand.agent.company_context}

Язык ответов: {brand.language}.

## Задача
Извлеки и структурируй информацию для презентации.

Если запрос слишком краткий (< 15 слов, нет данных) — задай ОДИН уточняющий вопрос.
Иначе — сразу верни JSON без лишних слов:

```json
{{
  "topic": "Тема",
  "key_facts": ["факт 1", "факт 2"],
  "data_for_charts": [
    {{
      "title": "Название графика",
      "kind": "bar",
      "labels": ["Q1","Q2","Q3","Q4"],
      "series": [{{"name": "Выручка", "values": [120,145,138,180]}}]
    }}
  ],
  "sections": [
    {{"title": "Раздел", "points": ["тезис 1","тезис 2"]}}
  ],
  "source_summary": "Источники данных"
}}
```

Включай `data_for_charts` когда упоминаются цифры, динамика, сравнение.
kind: bar | line | pie | doughnut
"""


class ResearchStage:
    async def run(self, session, user_text, file_bytes, file_name) -> dict:
        brand = session["brand"]
        messages = list(session["history"])
        if file_bytes and file_name:
            parsed = _parse_file(file_bytes, file_name)
            messages[-1]["content"] = f"{user_text}\n\n[Файл: {file_name}]\n{parsed}"

        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=2000,
            system=_make_system(brand), messages=messages,
        )
        text = resp.content[0].text.strip()
        data = _extract_json(text)
        if data and "topic" in data:
            return {"done": True, "data": data}
        return {"done": False, "message": text}


def _parse_file(file_bytes: bytes, file_name: str) -> str:
    name = file_name.lower()
    try:
        if name.endswith((".txt", ".md")):
            return file_bytes.decode("utf-8", errors="replace")[:3000]
        if name.endswith(".csv"):
            import csv
            rows = list(csv.reader(io.StringIO(file_bytes.decode("utf-8", errors="replace"))))
            return "\n".join("\t".join(r) for r in rows[:50])
        if name.endswith((".xlsx", ".xls")):
            import pandas as pd
            return pd.read_excel(io.BytesIO(file_bytes)).head(30).to_string()
        if name.endswith(".json"):
            return file_bytes.decode("utf-8", errors="replace")[:3000]
    except Exception as e:
        return f"[Ошибка чтения файла: {e}]"
    return f"[Формат {file_name} не поддерживается]"


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except Exception: pass
    return None
