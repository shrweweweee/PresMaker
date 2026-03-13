"""
Оркестратор: маршрутизирует между этапами.
Бренд хранится в session["brand"] и выбирается на этапе company_select.
"""
from brand.loader import find_brand, list_brands_grouped
from stages.research import ResearchStage
from stages.preparation import PreparationStage
from stages.content_review import ContentFillStage, ContentReviewStage
from stages.delivery import DeliveryBuildStage
from stages.qa import QAStage
from stages.onboarding import OnboardingStage


class Pipeline:
    def __init__(self):
        self.research       = ResearchStage()
        self.preparation    = PreparationStage()
        self.content_fill   = ContentFillStage()
        self.content_review = ContentReviewStage()
        self.delivery       = DeliveryBuildStage()
        self.qa             = QAStage()
        self.onboarding     = OnboardingStage()

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

        if stage == "onboarding":
            result = await self.onboarding.run(session, user_text, file_bytes, file_name)
            if session.get("stage") == "research":
                return result
            return result

        session["history"].append({"role": "user", "content": user_text})

        if stage == "research":
            result = await self.research.run(session, user_text, file_bytes, file_name)
            if result.get("done"):
                session["research_data"] = result["data"]
                session["stage"] = "preparation"
                return await self.preparation.start(session)
            return {"type": "message", "text": result["message"]}

        elif stage == "preparation":
            result = await self.preparation.run(session, user_text, file_bytes, file_name)
            if result.get("done"):
                session["brief"]      = result["brief"]["brief"]
                session["slide_plan"] = result["brief"]["slide_plan"]
                # auto-advance to content_fill
                return await self.content_fill.run(session)
            return {"type": "message", "text": result["message"]}

        elif stage == "content_review":
            result = await self.content_review.run(session, user_text)
            if result.get("done"):
                return await self._do_delivery(session)
            return result

        elif stage == "delivery_build":
            return await self._do_delivery(session)

        elif stage == "qa":
            result = await self.qa.run(session, user_text)
            if result.get("approved"):
                return {"type": "file", **result["file"]}
            if result.get("redo"):
                # rebuild from same filled_slides
                session["stage"] = "delivery_build"
                return await self._do_delivery(session)
            return {"type": "message", "text": result["message"]}

        return {"type": "message", "text": "Напишите название компании."}

    async def _select_company(self, session: dict, user_text: str) -> dict:
        matches = find_brand(user_text.strip())
        if not matches:
            session["stage"] = "onboarding"
            return {
                "type": "message",
                "text": (
                    f"Компания «{user_text}» не найдена.\n\n"
                    "Расскажите о ней или прикрепите файл — я создам брендбук автоматически."
                ),
            }
        if len(matches) == 1:
            session["brand"] = matches[0]
            session["stage"] = "research"
            return _company_preview_message(matches[0])
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
            session["stage"] = "research"
            return {"type": "message", "text":
                f"✅ Тема *{brand.theme_name}* выбрана.\n\n"
                "Напишите тему презентации или прикрепите файл."}
        if any(w in tl for w in _DENY):
            session["stage"] = "theme_select"
            return _theme_select_message(session.get("theme_candidates", []))
        if any(w in tl for w in _NEW):
            return self._start_new_theme(session, session.get("theme_candidates", []))
        return _theme_confirm_message(session["theme_pending"])

    def _start_new_theme(self, session: dict, candidates: list) -> dict:
        if candidates:
            session["new_theme_base_brand"] = candidates[0]
        session["onboarding_extracted"] = {}
        session["stage"] = "onboarding"
        company_hint = f"для компании *{candidates[0].company_name}*" if candidates else ""
        return {"type": "message", "text":
            f"🎨 Создаём новую тему {company_hint}.\n\n"
            "Опишите стиль: основной цвет, акцентный, название темы, особенности.\n"
            "Или прикрепите файл с гайдлайнами."}

    async def _do_delivery(self, session: dict) -> dict:
        path, meta = await self.delivery.run(session)
        session["pptx_path"] = path
        session["pptx_meta"] = meta
        session["stage"]     = "qa"
        qa_result = await self.qa.start(session)
        if qa_result.get("approved"):
            return {"type": "file", **qa_result["file"]}
        return {"type": "message", "text": qa_result["message"]}


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
    text = (
        f"🎨 *Тема: {brand.theme_name}*\n"
        f"Компания: *{brand.company_name}*\n"
        f"_{brand.tagline}_\n\n"
        f"Основной: `{brand.colors.primary_hex}`  Акцент: `{brand.colors.accent_hex}`\n"
        f"Слайдов: {brand.slide_defaults.count}  Язык: {brand.language}  Тон: {brand.tone}\n\n"
        "Использовать эту тему?\n"
        "• *да* — подтвердить\n"
        "• *нет* — вернуться к списку\n"
        "• *новая* — создать новую тему"
    )
    return {"type": "message", "text": text}


def _company_preview_message(brand) -> dict:
    text = (
        f"✅ Компания найдена: *{brand.company_name}*\n"
        f"_{brand.tagline}_\n\n"
        f"Основной: `{brand.colors.primary_hex}`  Акцент: `{brand.colors.accent_hex}`\n"
        f"Слайдов: {brand.slide_defaults.count}  "
        f"Язык: {brand.language}  Тон: {brand.tone}\n\n"
        "Напишите тему презентации или прикрепите файл."
    )
    return {"type": "message", "text": text}


def _theme_select_message(candidates: list) -> dict:
    lines = ["🎨 *Найдено несколько тем для этой компании:*\n"]
    for i, b in enumerate(candidates, 1):
        lines.append(f"{i}. *{b.theme_name}* — {b.company_name}")
    lines.append("\nНапишите номер или название темы.")
    lines.append("Или напишите *новая* чтобы создать новую тему.")
    return {"type": "message", "text": "\n".join(lines)}
