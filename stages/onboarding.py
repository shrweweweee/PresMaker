"""
Этап onboarding: регистрация новой компании.
Вызывается когда company_select не находит совпадения.
"""
import os, json, re, io
import anthropic
from pathlib import Path
from brand.loader import load as load_brand, _BRAND_DIR

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_CONFIRM_WORDS = {"да", "ок", "верно", "yes", "ok", "давай", "создавай"}

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


def _parse_file(file_bytes: bytes, file_name: str) -> str:
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


def _slugify(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_-]+", "_", name)
    return name[:32] or "company"


class OnboardingStage:

    async def run(self, session, user_text: str, file_bytes: bytes | None, file_name: str | None) -> dict:
        extracted = session.get("onboarding_extracted", {})
        if extracted and any(w in user_text.lower() for w in _CONFIRM_WORDS):
            return await self._save_and_proceed(session)
        return await self._extract(session, user_text, file_bytes, file_name)

    async def _extract(self, session, user_text: str, file_bytes: bytes | None, file_name: str | None) -> dict:
        content = user_text
        if file_bytes and file_name:
            parsed = _parse_file(file_bytes, file_name)
            content = f"{user_text}\n\n[Файл: {file_name}]\n{parsed}"

        base = session.get("new_theme_base_brand")
        if base:
            system = (
                f"Ты создаёшь новую тему оформления для компании {base.company_name}. "
                "Извлеки из описания пользователя визуальные параметры. "
                "Верни ТОЛЬКО JSON без обёрток:\n"
                '{"company_name":"...","slug":"...","theme_name":"...","tagline":"...",\n'
                '"description":"...","tone":"formal","language":"ru",\n'
                '"primary_color":"#...","accent_color":"#..."}\n'
                f'company_name должен быть "{base.company_name}", slug должен быть "{base.slug}". '
                "theme_name — короткое название новой темы (одно слово). "
                "primary_color и accent_color — hex-коды из описания."
            )
        else:
            system = (
                "Извлеки информацию о компании из текста пользователя. "
                "Верни ТОЛЬКО JSON без обёрток:\n"
                '{"company_name":"...","slug":"...","tagline":"...","industry":"...",'
                '"description":"...","tone":"formal","language":"ru",'
                '"primary_color":"#1A3C6E","accent_color":"#E8612A"}\n'
                "slug — латинские буквы/цифры/подчёркивание, до 32 символов. "
                "primary_color и accent_color — hex-коды. "
                "Угадывай недостающее из контекста. JSON без пояснений."
            )

        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = resp.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        # lock company identity for new-theme mode
        if base:
            data["company_name"] = base.company_name
            data["slug"] = base.slug

        # ensure slug
        if not data.get("slug"):
            data["slug"] = _slugify(data.get("company_name", "company"))

        session["onboarding_extracted"] = data

        if base:
            card = (
                f"🎨 *Новая тема для {data.get('company_name', '—')}:*\n\n"
                f"Название темы: *{data.get('theme_name', '—')}*\n"
                f"Основной цвет: `{data.get('primary_color', '—')}`  "
                f"Акцент: `{data.get('accent_color', '—')}`\n"
                f"Тон: {data.get('tone', '—')}  Язык: {data.get('language', '—')}\n\n"
                "Всё верно? Напишите *да* или уточните детали."
            )
        else:
            card = (
                f"🏢 *Найденная информация о компании:*\n\n"
                f"Название: *{data.get('company_name', '—')}*\n"
                f"Слоган: _{data.get('tagline', '—')}_\n"
                f"Отрасль: {data.get('industry', '—')}\n"
                f"Тон: {data.get('tone', '—')}  Язык: {data.get('language', '—')}\n"
                f"Основной цвет: `{data.get('primary_color', '—')}`  "
                f"Акцент: `{data.get('accent_color', '—')}`\n\n"
                "Всё верно? Напишите *да* или уточните детали."
            )
        return {"type": "message", "text": card}

    async def _save_and_proceed(self, session) -> dict:
        data = session["onboarding_extracted"]
        base = session.get("new_theme_base_brand")

        if base:
            theme_suffix = _slugify(data.get("theme_name", "custom"))
            file_slug = f"{base.slug}_{theme_suffix}"
        else:
            file_slug = data.get("slug") or _slugify(data.get("company_name", "company"))

        yaml_path = _BRAND_DIR / f"{file_slug}.yaml"
        yaml_content = _YAML_TEMPLATE.format(
            name=data.get("company_name", file_slug),
            slug=data.get("slug", file_slug),
            theme_name=data.get("theme_name", "default"),
            tagline=data.get("tagline", ""),
            language=data.get("language", "ru"),
            tone=data.get("tone", "formal"),
            description=data.get("description", ""),
            primary_color=data.get("primary_color", "#1A3C6E"),
            accent_color=data.get("accent_color", "#E8612A"),
        )
        yaml_path.write_text(yaml_content, encoding="utf-8")
        brand = load_brand(yaml_path)
        session["brand"] = brand
        session["stage"] = "research"
        session["new_theme_base_brand"] = None

        if base:
            msg = (
                f"✅ Тема *{brand.theme_name}* для *{brand.company_name}* сохранена!\n\n"
                "Напишите тему презентации или прикрепите файл с данными."
            )
        else:
            msg = (
                f"✅ Компания *{brand.company_name}* зарегистрирована!\n\n"
                "Напишите тему презентации или прикрепите файл с данными."
            )
        return {"type": "message", "text": msg}
