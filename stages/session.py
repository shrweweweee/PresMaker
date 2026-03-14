class SessionStore:
    def __init__(self):
        self._s: dict = {}

    def get_or_create(self, uid: int) -> dict:
        if uid not in self._s:
            self._s[uid] = {
                "stage": "active",
                "brand": None,
                "messages": [],              # full Claude API messages
                "system_prompt": "",         # built when brand selected
                "research_data": {},
                "brief": {},
                "slide_plan": [],
                "filled_slides": [],
                "pptx_path": None,
                "pptx_meta": {},
                "qa_attempts": 0,
            }
        return self._s[uid]

    def reset(self, uid: int):
        self._s.pop(uid, None)
