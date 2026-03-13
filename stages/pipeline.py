"""
Оркестратор: маршрутизирует между этапами.
Бренд хранится в session["brand"] и выбирается на этапе company_select.
"""
from brand.loader import find_brand, list_brands
from stages.research import ResearchStage
from stages.preparation import PreparationStage
from stages.delivery import DeliveryStage
from stages.qa import QAStage


class Pipeline:
    def __init__(self):
        self.research    = ResearchStage()
        self.preparation = PreparationStage()
        self.delivery    = DeliveryStage()
        self.qa          = QAStage()

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

        session["history"].append({"role": "user", "content": user_text})

        if stage == "research":
            result = await self.research.run(session, user_text, file_bytes, file_name)
            if result.get("done"):
                session["research_data"] = result["data"]
                session["stage"] = "preparation"
                return await self.preparation.start(session)
            return {"type": "message", "text": result["message"]}

        elif stage == "preparation":
            result = await self.preparation.run(session, user_text)
            if result.get("done"):
                session["brief"]      = result["brief"]["brief"]
                session["slide_plan"] = result["brief"]["slide_plan"]
                session["stage"]      = "delivery"
                return await self._do_delivery(session)
            return {"type": "message", "text": result["message"]}

        elif stage == "delivery":
            return await self._do_delivery(session)

        elif stage == "qa":
            result = await self.qa.run(session, user_text)
            if result.get("approved"):
                return {"type": "file", **result["file"]}
            return {"type": "message", "text": result["message"]}

        return {"type": "message", "text": "Напишите название компании."}

    async def _select_company(self, session: dict, user_text: str) -> dict:
        brand = find_brand(user_text.strip())
        if brand:
            session["brand"] = brand
            session["stage"] = "research"
            return {
                "type": "message",
                "text": (
                    f"✅ Компания *{brand.company_name}* — бренд загружен.\n\n"
                    "Напишите тему презентации или прикрепите файл с данными."
                ),
            }

        available = ", ".join(name for name, _ in list_brands())
        return {
            "type": "message",
            "text": (
                f"❌ Компания «{user_text}» не найдена.\n\n"
                f"Доступные компании: *{available}*\n\n"
                "Напишите название ещё раз."
            ),
        }

    async def _do_delivery(self, session: dict) -> dict:
        path, meta = await self.delivery.run(session)
        session["pptx_path"] = path
        session["pptx_meta"] = meta
        session["stage"]     = "qa"
        qa_result = await self.qa.start(session)
        if qa_result.get("approved"):
            return {"type": "file", **qa_result["file"]}
        return {"type": "message", "text": qa_result["message"]}
