"""
Загрузчик брендбука.
Читает brand/config.yaml один раз при старте, отдаёт типизированный объект.
Все модули импортируют `brand` отсюда — не хранят стиль локально.
"""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field
import yaml
from pptx.dml.color import RGBColor

# Путь к конфигу — можно переопределить через переменную окружения
_CONFIG_PATH = Path(os.environ.get("BRAND_CONFIG", Path(__file__).parent / "config.yaml"))


@dataclass
class Colors:
    primary:       RGBColor
    accent:        RGBColor
    bg_light:      RGBColor
    bg_dark:       RGBColor
    text_dark:     RGBColor
    text_muted:    RGBColor
    success:       RGBColor
    danger:        RGBColor
    chart_palette: list[str]   # hex strings для matplotlib
    # Исходные hex-строки (нужны для matplotlib)
    primary_hex:   str = "#1A3C6E"
    accent_hex:    str = "#E8612A"


@dataclass
class Typography:
    font_heading: str
    font_body:    str
    size_title:   int
    size_heading: int
    size_section: int
    size_body:    int
    size_caption: int


@dataclass
class Logo:
    url:          str
    position:     str
    width_inches: float


@dataclass
class SlideDefaults:
    count:          int
    always_include: list[str]
    footer_text:    str
    slide_numbers:  bool


@dataclass
class AgentConfig:
    welcome_message:  str
    company_context:  str
    forbidden_topics: list[str]


@dataclass
class BrandConfig:
    company_name:    str
    tagline:         str
    language:        str
    tone:            str
    colors:          Colors
    typography:      Typography
    logo:            Logo
    slide_defaults:  SlideDefaults
    agent:           AgentConfig

    def chart_colors(self, n: int) -> list[str]:
        """Возвращает n цветов из палитры (циклически)."""
        palette = self.colors.chart_palette
        return [(("#" + c.lstrip("#")) if not c.startswith("#") else c)
                for c in (palette * 3)[:n]]


def _hex(h: str) -> RGBColor:
    h = h.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load() -> BrandConfig:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    c = raw["colors"]
    t = raw["typography"]
    l = raw.get("logo", {})
    sd = raw.get("slide_defaults", {})
    ag = raw.get("agent", {})
    co = raw.get("company", {})

    colors = Colors(
        primary=_hex(c["primary"]),
        accent=_hex(c["accent"]),
        bg_light=_hex(c["bg_light"]),
        bg_dark=_hex(c["bg_dark"]),
        text_dark=_hex(c["text_dark"]),
        text_muted=_hex(c["text_muted"]),
        success=_hex(c["success"]),
        danger=_hex(c["danger"]),
        chart_palette=c.get("chart_palette", [c["primary"], c["accent"]]),
        primary_hex="#" + c["primary"].lstrip("#"),
        accent_hex="#" + c["accent"].lstrip("#"),
    )

    return BrandConfig(
        company_name=co.get("name", ""),
        tagline=co.get("tagline", ""),
        language=co.get("language", "ru"),
        tone=co.get("tone", "formal"),
        colors=colors,
        typography=Typography(**{k: t[k] for k in Typography.__dataclass_fields__}),
        logo=Logo(
            url=l.get("url", ""),
            position=l.get("position", "bottom-right"),
            width_inches=float(l.get("width_inches", 1.4)),
        ),
        slide_defaults=SlideDefaults(
            count=sd.get("count", 10),
            always_include=sd.get("always_include", ["title", "closing"]),
            footer_text=sd.get("footer_text", ""),
            slide_numbers=sd.get("slide_numbers", True),
        ),
        agent=AgentConfig(
            welcome_message=ag.get("welcome_message", "Привет! Напишите тему презентации."),
            company_context=ag.get("company_context", ""),
            forbidden_topics=ag.get("forbidden_topics", []),
        ),
    )


# ── Синглтон — загружается один раз при импорте ────────────────────────────
brand: BrandConfig = load()


def reload() -> BrandConfig:
    """Перезагружает конфиг без перезапуска бота (удобно при правках)."""
    global brand
    brand = load()
    return brand
