"""Layout Registry — inventory of slide types and their constraints (ClaWic rules 2-3)."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class LayoutSpec:
    name: str
    max_items: int
    has_header: bool
    has_footer: bool
    has_logo: bool
    required_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    body_area: tuple[float, float, float, float] = (1.0, 1.8, 11.33, 5.0)


LAYOUTS: dict[str, LayoutSpec] = {
    "title": LayoutSpec(
        "title", max_items=0, has_header=False, has_footer=False, has_logo=True,
        required_fields=["title"], optional_fields=["subtitle"],
        body_area=(1.0, 2.2, 11.33, 4.2),
    ),
    "content": LayoutSpec(
        "content", max_items=6, has_header=True, has_footer=True, has_logo=True,
        required_fields=["title"], optional_fields=["content", "speaker_notes"],
        body_area=(1.0, 1.8, 11.33, 5.0),
    ),
    "chart": LayoutSpec(
        "chart", max_items=0, has_header=True, has_footer=True, has_logo=True,
        required_fields=["title", "chart_ref"], optional_fields=[],
        body_area=(1.0, 1.8, 11.33, 4.8),
    ),
    "two_column": LayoutSpec(
        "two_column", max_items=5, has_header=True, has_footer=True, has_logo=True,
        required_fields=["title"], optional_fields=["left", "right"],
        body_area=(1.0, 1.8, 11.33, 5.0),
    ),
    "stats": LayoutSpec(
        "stats", max_items=4, has_header=True, has_footer=True, has_logo=True,
        required_fields=["title", "stats"], optional_fields=[],
        body_area=(1.0, 1.8, 11.33, 5.0),
    ),
    "closing": LayoutSpec(
        "closing", max_items=4, has_header=False, has_footer=False, has_logo=True,
        required_fields=["title"], optional_fields=["content"],
        body_area=(1.0, 1.5, 11.33, 5.0),
    ),
    "section": LayoutSpec(
        "section", max_items=0, has_header=False, has_footer=False, has_logo=False,
        required_fields=["title"], optional_fields=["section_number", "subtitle"],
        body_area=(1.0, 1.5, 11.33, 5.0),
    ),
}

_DEFAULT_LAYOUT = "content"


def validate_slide(slide_data: dict) -> list[str]:
    """Check that required fields are present and items don't exceed max."""
    issues = []
    slide_type = slide_data.get("type", _DEFAULT_LAYOUT)
    spec = LAYOUTS.get(slide_type, LAYOUTS[_DEFAULT_LAYOUT])

    for f in spec.required_fields:
        val = slide_data.get(f)
        if val is None or (isinstance(val, str) and not val.strip()):
            issues.append(f"missing required field '{f}'")

    if spec.max_items > 0:
        items = _get_items(slide_data)
        if len(items) > spec.max_items:
            issues.append(f"{len(items)} items exceeds max {spec.max_items}")

    return issues


def match_layout(slide_data: dict) -> str:
    """Return the slide type if valid, otherwise pick best match or fallback to 'content'."""
    t = slide_data.get("type", "")
    if t in LAYOUTS:
        return t
    if slide_data.get("chart_ref") is not None:
        return "chart"
    if slide_data.get("stats"):
        return "stats"
    if slide_data.get("left") or slide_data.get("right"):
        return "two_column"
    return _DEFAULT_LAYOUT


def truncate_content(slide_data: dict) -> dict:
    """Truncate items to max_items for the slide type. Returns a new dict."""
    slide_type = slide_data.get("type", _DEFAULT_LAYOUT)
    spec = LAYOUTS.get(slide_type, LAYOUTS[_DEFAULT_LAYOUT])
    if spec.max_items <= 0:
        return slide_data

    result = dict(slide_data)
    items = _get_items(result)
    if len(items) > spec.max_items:
        log.warning(
            "Slide '%s' (%s): truncating %d items to %d",
            result.get("title", "?"), slide_type, len(items), spec.max_items,
        )
        _set_items(result, items[:spec.max_items])

    # Truncate two_column items separately
    if slide_type == "two_column":
        for col in ("left", "right"):
            col_data = result.get(col)
            if isinstance(col_data, dict) and len(col_data.get("items", [])) > spec.max_items:
                col_data = dict(col_data)
                col_data["items"] = col_data["items"][:spec.max_items]
                result[col] = col_data

    return result


def _get_items(slide_data: dict) -> list:
    """Extract the main item list from a slide."""
    t = slide_data.get("type", _DEFAULT_LAYOUT)
    if t in ("content", "closing"):
        return slide_data.get("content", [])
    if t == "stats":
        return slide_data.get("stats", [])
    return []


def _set_items(slide_data: dict, items: list):
    """Set the main item list on a slide (mutates)."""
    t = slide_data.get("type", _DEFAULT_LAYOUT)
    if t in ("content", "closing"):
        slide_data["content"] = items
    elif t == "stats":
        slide_data["stats"] = items
