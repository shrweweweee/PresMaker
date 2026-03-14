"""
Загрузчик брендбука.
Поддерживает несколько компаний — каждый YAML в brand/ = отдельный бренд.
"""
from __future__ import annotations
import os, json
from pathlib import Path
from dataclasses import dataclass
import yaml
from pptx.dml.color import RGBColor

_BRAND_DIR = Path(__file__).parent
_CONFIG_PATH = Path(os.environ.get("BRAND_CONFIG", _BRAND_DIR / "config.yaml"))
_COMPANIES_JSON = _BRAND_DIR / "companies.json"


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
    chart_palette: list[str]
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
    slug:            str = ""
    theme_name:      str = "default"
    description:     str = ""

    def chart_colors(self, n: int) -> list[str]:
        palette = self.colors.chart_palette
        return [(("#" + c.lstrip("#")) if not c.startswith("#") else c)
                for c in (palette * 3)[:n]]


def _hex(h: str) -> RGBColor:
    h = h.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load(path: Path | None = None) -> BrandConfig:
    path = path or _CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    c  = raw["colors"]
    t  = raw["typography"]
    l  = raw.get("logo", {})
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

    stem = Path(path).stem if path else ""
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
        slug=co.get("slug", stem),
        theme_name=co.get("theme_name", "default"),
        description=co.get("description", ""),
    )


def list_brands() -> list[tuple[str, Path]]:
    """Возвращает список (название компании, путь к yaml) для всех брендов."""
    result = []
    for yaml_file in sorted(_BRAND_DIR.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            name = raw.get("company", {}).get("name", yaml_file.stem)
            result.append((name, yaml_file))
        except Exception:
            pass
    return result


def list_brands_grouped() -> dict[str, list[dict]]:
    """Возвращает {slug: [{"name": ..., "theme": ..., "path": Path}, ...]}."""
    groups: dict[str, list[dict]] = {}
    for yaml_file in sorted(_BRAND_DIR.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            co = raw.get("company", {})
            name = co.get("name", yaml_file.stem)
            slug = co.get("slug", yaml_file.stem)
            theme = co.get("theme_name", "default")
            entry = {"name": name, "theme": theme, "path": yaml_file}
            groups.setdefault(slug, []).append(entry)
        except Exception:
            pass
    # default theme first in each group
    for slug in groups:
        groups[slug].sort(key=lambda e: (0 if e["theme"] == "default" else 1, e["theme"]))
    return groups


def find_brand(query: str) -> list[BrandConfig]:
    """Находит все темы компании по названию (регистронезависимо, частичное совпадение)."""
    q = query.lower().strip()
    results = []
    for name, path in list_brands():
        if q in name.lower() or name.lower() in q:
            results.append(load(path))
    return results


def load_companies_json() -> dict:
    """Читает brand/companies.json — AI-facing память о компаниях."""
    if _COMPANIES_JSON.exists():
        with open(_COMPANIES_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_company_to_json(
    slug: str,
    name: str,
    tagline: str = "",
    description: str = "",
    context: str = "",
    audiences: list[str] | None = None,
    theme_name: str = "default",
    brand_file: str = "",
) -> None:
    """Добавляет/обновляет запись о компании в companies.json."""
    data = load_companies_json()
    entry = data.get(slug, {
        "name": name,
        "tagline": tagline,
        "description": description,
        "context": context,
        "audiences": audiences or [],
        "themes": [],
        "brand_files": [],
    })
    entry["name"] = name
    if tagline:
        entry["tagline"] = tagline
    if description:
        entry["description"] = description
    if context:
        entry["context"] = context
    if audiences:
        entry["audiences"] = audiences
    if theme_name not in entry.get("themes", []):
        entry.setdefault("themes", []).append(theme_name)
    if brand_file and brand_file not in entry.get("brand_files", []):
        entry.setdefault("brand_files", []).append(brand_file)
    data[slug] = entry
    with open(_COMPANIES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Синглтон — дефолтный бренд (используется как fallback)
brand: BrandConfig = load()


def reload() -> BrandConfig:
    global brand
    brand = load()
    return brand
