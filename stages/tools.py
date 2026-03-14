"""
Определения инструментов (tools) для Claude API.
6 инструментов в 3 навыках: Profile, Content, Build.
"""

TOOL_DEFINITIONS = [
    # ── Skill: Profile ──────────────────────────────────────────────────────
    {
        "name": "select_company",
        "description": (
            "Выбирает компанию для презентации. "
            "Вызывай когда определил какую компанию хочет пользователь."
        ),
        "input_schema": {
            "type": "object",
            "required": ["slug"],
            "properties": {
                "slug": {"type": "string", "description": "Slug компании из списка"},
                "theme_name": {
                    "type": "string",
                    "description": "Название темы (default если одна)",
                    "default": "default",
                },
            },
        },
    },
    {
        "name": "register_company",
        "description": (
            "Регистрирует новую компанию: создаёт YAML-файл бренда и загружает его. "
            "Вызывай после того, как узнал название, цвета и стиль компании."
        ),
        "input_schema": {
            "type": "object",
            "required": ["company_name", "slug", "primary_color", "accent_color"],
            "properties": {
                "company_name": {"type": "string", "description": "Название компании"},
                "slug": {
                    "type": "string",
                    "pattern": "^[a-z0-9_]{1,32}$",
                    "description": "Латинский идентификатор (a-z, 0-9, _)",
                },
                "theme_name": {"type": "string", "default": "default"},
                "tagline": {"type": "string", "default": ""},
                "description": {"type": "string", "default": ""},
                "tone": {
                    "type": "string",
                    "enum": ["formal", "friendly", "technical"],
                    "default": "formal",
                },
                "language": {"type": "string", "default": "ru"},
                "primary_color": {
                    "type": "string",
                    "pattern": "^#[0-9A-Fa-f]{6}$",
                    "description": "Основной цвет в hex (#RRGGBB)",
                },
                "accent_color": {
                    "type": "string",
                    "pattern": "^#[0-9A-Fa-f]{6}$",
                    "description": "Акцентный цвет в hex (#RRGGBB)",
                },
                "logo_url": {
                    "type": "string",
                    "description": "URL логотипа компании (PNG/SVG). Пустая строка если нет.",
                    "default": "",
                },
            },
        },
    },

    # ── Skill: Content ──────────────────────────────────────────────────────
    {
        "name": "save_research",
        "description": (
            "Сохраняет структурированные данные исследования. "
            "Вызывай когда собрал достаточно информации из сообщений/файлов пользователя."
        ),
        "input_schema": {
            "type": "object",
            "required": ["topic", "key_facts", "sections"],
            "properties": {
                "topic": {"type": "string", "description": "Тема презентации"},
                "key_facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ключевые факты",
                },
                "data_for_charts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "kind", "labels", "series"],
                        "properties": {
                            "title": {"type": "string"},
                            "kind": {
                                "type": "string",
                                "enum": ["bar", "line", "pie", "doughnut"],
                            },
                            "labels": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "series": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["name", "values"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "values": {
                                            "type": "array",
                                            "items": {"type": "number"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "default": [],
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "points"],
                        "properties": {
                            "title": {"type": "string"},
                            "points": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "source_summary": {"type": "string", "default": ""},
            },
        },
    },
    {
        "name": "propose_slide_plan",
        "description": (
            "Показывает пользователю план слайдов для подтверждения. "
            "Вызывай когда уточнил аудиторию, тон и количество слайдов."
        ),
        "input_schema": {
            "type": "object",
            "required": ["brief", "slide_plan"],
            "properties": {
                "brief": {
                    "type": "object",
                    "required": ["audience", "tone", "slide_count", "language"],
                    "properties": {
                        "audience": {"type": "string"},
                        "tone": {"type": "string"},
                        "slide_count": {"type": "integer"},
                        "language": {"type": "string"},
                    },
                },
                "slide_plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "type", "title"],
                        "properties": {
                            "id": {"type": "integer"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "title", "content", "chart",
                                    "two_column", "stats", "closing",
                                    "section",
                                ],
                            },
                            "title": {"type": "string"},
                            "chart_ref": {"type": "integer"},
                            "section_number": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "fill_slides",
        "description": (
            "Заполняет все слайды контентом и показывает предпросмотр пользователю. "
            "Вызывай после того, как пользователь подтвердил план слайдов."
        ),
        "input_schema": {
            "type": "object",
            "required": ["slides"],
            "properties": {
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "type", "title"],
                        "properties": {
                            "id": {"type": "integer"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "title", "content", "chart",
                                    "two_column", "stats", "closing",
                                    "section",
                                ],
                            },
                            "title": {"type": "string"},
                            "subtitle": {"type": "string"},
                            "section_number": {"type": "string"},
                            "content": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["type", "text"],
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["bullet", "highlight"],
                                        },
                                        "text": {"type": "string"},
                                    },
                                },
                            },
                            "chart_ref": {"type": "integer"},
                            "left": {
                                "type": "object",
                                "properties": {
                                    "heading": {"type": "string"},
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                            "right": {
                                "type": "object",
                                "properties": {
                                    "heading": {"type": "string"},
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                            "stats": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "value": {"type": "string"},
                                        "trend": {"type": "string"},
                                    },
                                },
                            },
                            "speaker_notes": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "edit_slides",
        "description": (
            "Применяет правки к слайдам и показывает обновлённый предпросмотр. "
            "Вызывай когда пользователь просит изменить содержание слайдов."
        ),
        "input_schema": {
            "type": "object",
            "required": ["slides"],
            "properties": {
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "type", "title"],
                        "properties": {
                            "id": {"type": "integer"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "title", "content", "chart",
                                    "two_column", "stats", "closing",
                                    "section",
                                ],
                            },
                            "title": {"type": "string"},
                            "subtitle": {"type": "string"},
                            "section_number": {"type": "string"},
                            "content": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["type", "text"],
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["bullet", "highlight"],
                                        },
                                        "text": {"type": "string"},
                                    },
                                },
                            },
                            "chart_ref": {"type": "integer"},
                            "left": {
                                "type": "object",
                                "properties": {
                                    "heading": {"type": "string"},
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                            "right": {
                                "type": "object",
                                "properties": {
                                    "heading": {"type": "string"},
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                            "stats": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "value": {"type": "string"},
                                        "trend": {"type": "string"},
                                    },
                                },
                            },
                            "speaker_notes": {"type": "string"},
                        },
                    },
                },
            },
        },
    },

    # ── Skill: Build ────────────────────────────────────────────────────────
    {
        "name": "build_presentation",
        "description": (
            "Собирает PPTX-файл из заполненных слайдов и запускает QA-проверку. "
            "Вызывай когда пользователь подтвердил содержание слайдов."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]
