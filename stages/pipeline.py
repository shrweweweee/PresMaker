"""
Оркестратор: маршрутизирует между этапами.
Бренд хранится в session["brand"] и выбирается на этапе company_select.
"""
from __future__ import annotations
from brand.loader import find_brand, list_brands_grouped
from stages.agent import AgentLoop, build_system_prompt


class Pipeline:
    def __init__(self):
        self.agent = AgentLoop()

    async def step(
        self,
        session: dict,
        user_text: str,
        file_bytes: bytes | None = None,
        file_name: str | None = None,
    ) -> dict:
        stage = session.get("stage", "company_select")

        if stage == "company_select":
            return await self._select_company(session, user_text)

        if stage == "theme_select":
            return await self._handle_theme_select(session, user_text)

        if stage == "theme_confirm":
            return await self._handle_theme_confirm(session, user_text)

        if stage == "active":
            return await self.agent.run(session, user_text, file_bytes, file_name)

        return {"type": "message", "text": "Напишите название компании."}

    async def _select_company(self, session: dict, user_text: str) -> dict:
        matches = find_brand(user_text.strip())
        if not matches:
            # Unknown company → onboarding via agent
            session["stage"] = "active"
            session["system_prompt"] = build_system_prompt(
                _default_brand(), onboarding=True
            )
            return {
                "type": "message",
                "text": (
                    f"Компания «{user_text}» не найдена.\n\n"
                    "Расскажите о ней — я создам брендбук автоматически."
                ),
            }
        if len(matches) == 1:
            brand = matches[0]
            session["brand"] = brand
            session["stage"] = "active"
            session["system_prompt"] = build_system_prompt(brand)
            return _company_preview_message(brand)
        session["theme_candidates"] = matches
        session["stage"] = "theme_select"
        return _theme_select_message(matches)

    async def _handle_theme_select(self, session: dict, user_text: str) -> dict:
        candidates = session.get("theme_candidates", [])
        tl = user_text.strip().lower()

        _NEW_KEYWORDS = {"новая", "новую", "создать", "другой", "новый", "добавить", "custom", "new"}
        if any(w in tl for w in _NEW_KEYWORDS):
            return self._start_new_theme(session, candidates)

        chosen = _match_theme(user_text.strip(), candidates)
        if not chosen:
            return _theme_select_message(candidates)

        session["theme_pending"] = chosen
        session["stage"] = "theme_confirm"
        return _theme_confirm_message(chosen)

    async def _handle_theme_confirm(self, session: dict, user_text: str) -> dict:
        tl = user_text.lower()
        _CONFIRM = {"да", "ок", "верно", "yes", "ok", "давай", "использовать", "поехали"}
        _DENY = {"нет", "другую", "назад", "back", "no", "другая", "другой", "вернуться"}
        _NEW = {"новая", "новую", "создать", "другой стиль", "добавить", "новый"}

        if any(w in tl for w in _CONFIRM):
            brand = session["theme_pending"]
            session["brand"] = brand
            session["stage"] = "active"
            session["system_prompt"] = build_system_prompt(brand)
            return {"type": "message", "text":
                f"\u2705 Тема *{brand.theme_name}* выбрана.\n\n"
                "Напишите тему презентации или прикрепите файл."}
        if any(w in tl for w in _DENY):
            session["stage"] = "theme_select"
            return _theme_select_message(session.get("theme_candidates", []))
        if any(w in tl for w in _NEW):
            return self._start_new_theme(session, session.get("theme_candidates", []))
        return _theme_confirm_message(session["theme_pending"])

    def _start_new_theme(self, session: dict, candidates: list) -> dict:
        base = candidates[0] if candidates else _default_brand()
        session["brand"] = base
        session["stage"] = "active"
        session["system_prompt"] = build_system_prompt(base, onboarding=True)
        company_hint = f"для компании *{base.company_name}*" if candidates else ""
        return {"type": "message", "text":
            f"\U0001f3a8 Создаём новую тему {company_hint}.\n\n"
            "Опишите стиль: основной цвет, акцентный, название темы, особенности.\n"
            "Или прикрепите файл с гайдлайнами."}


def _default_brand():
    """Fallback brand for onboarding when no company matched."""
    from brand.loader import brand
    return brand


def _match_theme(text: str, candidates: list):
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
    tl = text.lower()
    for c in candidates:
        if tl in c.theme_name.lower() or c.theme_name.lower() in tl:
            return c
    return None


def _theme_confirm_message(brand) -> dict:
    lines = [
        f"\U0001f3a8 *Тема: {brand.theme_name}*",
        f"Компания: *{brand.company_name}*",
    ]
    if brand.tagline:
        lines.append(f"_{brand.tagline}_")
    lines.append(
        f"\nОсновной: `{brand.colors.primary_hex}`  Акцент: `{brand.colors.accent_hex}`"
    )
    lines.append(
        "\nИспользовать эту тему?\n"
        "\u2022 *да* \u2014 подтвердить\n"
        "\u2022 *нет* \u2014 вернуться к списку\n"
        "\u2022 *новая* \u2014 создать новую тему"
    )
    return {"type": "message", "text": "\n".join(lines)}


def _company_preview_message(brand) -> dict:
    lines = [f"\u2705 Компания найдена: *{brand.company_name}*"]
    if brand.tagline:
        lines.append(f"_{brand.tagline}_")
    lines.append(
        f"\nОсновной: `{brand.colors.primary_hex}`  Акцент: `{brand.colors.accent_hex}`"
    )
    lines.append("\nНапишите тему презентации или прикрепите файл.")
    return {"type": "message", "text": "\n".join(lines)}


def _theme_select_message(candidates: list) -> dict:
    lines = ["\U0001f3a8 *Найдено несколько тем для этой компании:*\n"]
    for i, b in enumerate(candidates, 1):
        lines.append(f"{i}. *{b.theme_name}* \u2014 {b.company_name}")
    lines.append("\nНапишите номер или название темы.")
    lines.append("Или напишите *новая* чтобы создать новую тему.")
    return {"type": "message", "text": "\n".join(lines)}
