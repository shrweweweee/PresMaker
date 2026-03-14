"""
Оркестратор: всё через AI agent loop, без скриптовых стадий.
"""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from stages.agent import AgentLoop, build_initial_system_prompt


class Pipeline:
    def __init__(self):
        self.agent = AgentLoop()

    async def step(
        self,
        session: dict,
        user_text: str,
        file_bytes: bytes | None = None,
        file_name: str | None = None,
        status_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict:
        if not session.get("system_prompt"):
            session["system_prompt"] = build_initial_system_prompt()
        return await self.agent.run(session, user_text, file_bytes, file_name,
                                    status_callback=status_callback)
