"""Этап 4: QA — визуальная проверка через Claude Vision."""
import os, subprocess, tempfile, glob, re, base64
import anthropic

from stages.layout_registry import LAYOUTS

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_QA_SYSTEM = """
Ты QA-инспектор презентаций. Проверяй по категориям:

LAYOUT: перекрывающиеся элементы, обрезанный текст, элементы за пределами слайда
CONTRAST: текст сливается с фоном, нечитаемые подписи
CONTENT: пустые блоки, placeholder-текст, отсутствующие графики
CONSISTENCY: разный стиль заголовков между слайдами, прыгающие размеры

Ответ: PASS — если всё хорошо.
Иначе: ISSUES:
- Слайд N [КАТЕГОРИЯ]: описание проблемы
"""


def content_qa(slides: list[dict], charts_data: list[dict]) -> list[str]:
    """Pre-render QA: validate slide data without generating PPTX."""
    issues = []
    for i, s in enumerate(slides):
        slide_num = i + 1
        slide_type = s.get("type", "content")
        spec = LAYOUTS.get(slide_type, LAYOUTS["content"])

        # Required fields
        for field in spec.required_fields:
            val = s.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                issues.append(f"Слайд {slide_num}: пустое обязательное поле '{field}'")

        # chart_ref validity
        if slide_type == "chart":
            ref = s.get("chart_ref", 0)
            if ref >= len(charts_data):
                issues.append(
                    f"Слайд {slide_num}: chart_ref={ref} вне диапазона "
                    f"(есть {len(charts_data)} графиков)"
                )

        # Content overflow warning
        items = s.get("content") or s.get("stats") or []
        if isinstance(items, list) and spec.max_items > 0 and len(items) > spec.max_items:
            issues.append(
                f"Слайд {slide_num}: {len(items)} элементов "
                f"(макс {spec.max_items}), лишние обрежутся"
            )

        # Empty columns in two_column
        if slide_type == "two_column":
            for col in ("left", "right"):
                col_data = s.get(col, {})
                if not col_data or not col_data.get("items"):
                    issues.append(f"Слайд {slide_num}: пустая колонка '{col}'")

    return issues


class QAStage:

    async def start(self, session) -> dict:
        pngs = _render_to_png(session["pptx_path"])
        session["qa_pngs"]    = pngs
        session["qa_attempts"] = session.get("qa_attempts", 0) + 1

        if not pngs:
            return {"approved": True, "file": _file_result(session)}

        issues = await _vision_check(pngs)
        session["qa_issues"] = issues

        if not issues:
            return {"approved": True, "file": _file_result(session)}

        return {"message": (
            f"🔎 *QA — найдены замечания:*\n\n{issues}\n\n"
            "Отправляю файл. Напишите *переделай* если нужно пересоздать."
        )}

    async def run(self, session, user_text) -> dict:
        if any(w in user_text.lower() for w in ["переделай","исправь","redo","fix"]):
            return {"redo": True, "message": "🔄 Пересоздаю презентацию…"}
        return {"approved": True, "file": _file_result(session)}


def _render_to_png(pptx_path: str) -> list[str]:
    try:
        tmp = tempfile.mkdtemp()
        subprocess.run(
            ["libreoffice","--headless","--convert-to","pdf", pptx_path,"--outdir",tmp],
            capture_output=True, timeout=60
        )
        pdfs = glob.glob(os.path.join(tmp,"*.pdf"))
        if not pdfs: return []
        subprocess.run(["pdftoppm","-jpeg","-r","100",pdfs[0],
                        os.path.join(tmp,"slide")], capture_output=True, timeout=60)
        return sorted(glob.glob(os.path.join(tmp,"slide*.jpg")))
    except Exception:
        return []


async def _vision_check(pngs: list[str]) -> str:
    content = []
    for i, p in enumerate(pngs[:6]):
        try:
            with open(p,"rb") as f:
                content.append({"type":"image","source":{
                    "type":"base64","media_type":"image/jpeg",
                    "data": base64.b64encode(f.read()).decode()
                }})
            content.append({"type":"text","text":f"Слайд {i+1}"})
        except Exception:
            continue
    if not content: return ""
    content.append({"type":"text","text":"Найди проблемы."})
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=600,
        system=_QA_SYSTEM,
        messages=[{"role":"user","content":content}],
    )
    result = resp.content[0].text.strip()
    return "" if result.startswith("PASS") else result.replace("ISSUES:","").strip()


def _file_result(session) -> dict:
    brand = session["brand"]
    meta  = session.get("pptx_meta", {})
    title = meta.get("title", brand.company_name)
    n     = meta.get("slides","?")
    safe  = re.sub(r"[^\w\s-]","",title)[:40].strip()
    return {
        "path":     session["pptx_path"],
        "filename": f"{safe}.pptx",
        "caption":  f"«{title}» — {n} слайдов · {brand.company_name}",
    }
