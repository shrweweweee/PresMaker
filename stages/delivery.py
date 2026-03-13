"""
Этап 3: Delivery — генерирует PPTX.
Все цвета, шрифты, размеры берутся из session["brand"].
"""
import os, json, re, io, tempfile
import anthropic
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_W = Inches(13.33)
_H = Inches(7.5)


def _make_content_system(brand) -> str:
    return f"""
Ты заполняешь слайды контентом для компании {brand.company_name}.
Язык: {brand.language}. Тон: {brand.tone}.
{brand.agent.company_context}

Верни ТОЛЬКО JSON-массив слайдов с заполненным контентом.

Форматы:
- content: {{"id":N,"type":"content","title":"...","content":[{{"type":"bullet","text":"..."}},{{"type":"highlight","text":"ключевой тезис"}}],"speaker_notes":"..."}}
- chart:   {{"id":N,"type":"chart","title":"...","chart_ref":0}}
- two_column: {{"id":N,"type":"two_column","title":"...","left":{{"heading":"До","items":["..."]}}, "right":{{"heading":"После","items":["..."]}}}}
- stats:   {{"id":N,"type":"stats","title":"...","stats":[{{"label":"Выручка","value":"₽2.4 млрд","trend":"+18%"}}]}}
- title:   {{"id":1,"type":"title","title":"...","subtitle":"..."}}
- closing: {{"id":N,"type":"closing","title":"Спасибо!","content":[{{"type":"bullet","text":"контакт"}}]}}

4-6 буллетов на content-слайд. Только JSON, без обёрток.
"""


class DeliveryStage:

    async def run(self, session) -> tuple[str, dict]:
        brand = session["brand"]
        slides = await self._fill_content(session)
        tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
        tmp.close()
        _build_pptx(slides, session["research_data"].get("data_for_charts", []), tmp.name, brand)
        return tmp.name, {
            "title":  session["research_data"].get("topic", "Презентация"),
            "slides": len(slides),
        }

    async def _fill_content(self, session) -> list:
        brand      = session["brand"]
        research   = session["research_data"]
        brief      = session.get("brief", {})
        slide_plan = session.get("slide_plan", [])
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=5000,
            system=_make_content_system(brand),
            messages=[{"role":"user","content":(
                f"Research:\n{json.dumps(research, ensure_ascii=False)}\n\n"
                f"Бриф: {json.dumps(brief, ensure_ascii=False)}\n\n"
                f"План: {json.dumps(slide_plan, ensure_ascii=False)}"
            )}],
        )
        text = resp.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*","",text); text = re.sub(r"\s*```$","",text)
        try:
            result = json.loads(text)
            if isinstance(result, list): return result
        except Exception: pass
        return slide_plan


# ── PPTX builder ─────────────────────────────────────────────────────────────
def _build_pptx(slides: list, charts_data: list, path: str, brand):
    prs = Presentation()
    prs.slide_width  = _W
    prs.slide_height = _H
    blank = prs.slide_layouts[6]

    for s in slides:
        sl = prs.slides.add_slide(blank)
        t  = s.get("type", "content")
        if t == "title":        _slide_title(sl, s, brand)
        elif t == "chart":      _slide_chart(sl, s, brand, charts_data)
        elif t == "two_column": _slide_two_col(sl, s, brand)
        elif t == "stats":      _slide_stats(sl, s, brand)
        elif t == "closing":    _slide_closing(sl, s, brand)
        else:                   _slide_content(sl, s, brand)

        if brand.slide_defaults.slide_numbers and t != "title":
            _add_slide_number(sl, slides.index(s)+1, len(slides), brand)

    prs.save(path)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _rect(sl, x, y, w, h, color: RGBColor):
    sh = sl.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.fill.background()

def _text(sl, text, x, y, w, h, size=18, bold=False, color: RGBColor=None,
          align=PP_ALIGN.LEFT, font=None, brand=None):
    font = font or (brand.typography.font_body if brand else "Calibri")
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    p  = tf.paragraphs[0]; p.alignment = align
    run = p.add_run(); run.text = text
    run.font.size = Pt(size); run.font.bold = bold
    run.font.color.rgb = color or (brand.colors.text_dark if brand else RGBColor(0,0,0))
    run.font.name = font

def _header(sl, title, brand):
    _rect(sl, 0, 0, 13.33, 1.1, brand.colors.primary)
    _text(sl, title, 0.4, 0.1, 12.5, 0.9,
          size=brand.typography.size_heading, bold=True,
          color=brand.colors.bg_light,
          font=brand.typography.font_heading, brand=brand)
    if brand.slide_defaults.footer_text:
        _rect(sl, 0, 7.1, 13.33, 0.4, brand.colors.primary)
        _text(sl, brand.slide_defaults.footer_text, 0.3, 7.1, 10, 0.4,
              size=brand.typography.size_caption, color=brand.colors.bg_light, brand=brand)

def _logo(sl, brand):
    if not brand.logo.url:
        return
    try:
        import urllib.request
        data = urllib.request.urlopen(brand.logo.url, timeout=5).read()
        w = brand.logo.width_inches
        h = w * 0.4
        pos = brand.logo.position
        x = 13.33 - w - 0.2 if "right" in pos else 0.2
        y = 7.5  - h - 0.05 if "bottom" in pos else 0.05
        sl.shapes.add_picture(io.BytesIO(data), Inches(x), Inches(y),
                              width=Inches(w), height=Inches(h))
    except Exception:
        pass

def _add_slide_number(sl, current, total, brand):
    _text(sl, f"{current}/{total}", 12.8, 7.15, 0.5, 0.3,
          size=11, color=brand.colors.text_muted, brand=brand)


# ── Типы слайдов ─────────────────────────────────────────────────────────────
def _slide_title(sl, s, brand):
    _rect(sl, 0, 0, 13.33, 7.5, brand.colors.bg_dark)
    _text(sl, s.get("title",""), 1, 2.0, 11.3, 1.8,
          size=brand.typography.size_title, bold=True,
          color=brand.colors.bg_light, align=PP_ALIGN.CENTER,
          font=brand.typography.font_heading, brand=brand)
    sub = s.get("subtitle","")
    if sub:
        _text(sl, sub, 1, 4.1, 11.3, 0.8,
              size=brand.typography.size_section,
              color=brand.colors.accent, align=PP_ALIGN.CENTER, brand=brand)
    _logo(sl, brand)

def _slide_content(sl, s, brand):
    _header(sl, s.get("title",""), brand)
    y = 1.3
    for item in s.get("content", []):
        t = item.get("type","bullet"); txt = item.get("text","")
        if t == "bullet":
            _text(sl, f"• {txt}", 0.5, y, 12.3, 0.6,
                  size=brand.typography.size_body, color=brand.colors.text_dark, brand=brand)
            y += 0.63
        elif t == "highlight":
            _rect(sl, 0.3, y-0.04, 0.06, 0.62, brand.colors.accent)
            _text(sl, txt, 0.5, y, 12.3, 0.65,
                  size=brand.typography.size_body, bold=True, color=brand.colors.accent, brand=brand)
            y += 0.75
    if s.get("speaker_notes"):
        sl.notes_slide.notes_text_frame.text = s["speaker_notes"]
    _logo(sl, brand)

def _slide_chart(sl, s, brand, charts_data):
    _header(sl, s.get("title",""), brand)
    idx = s.get("chart_ref", 0)
    cd  = charts_data[idx] if idx < len(charts_data) else None
    if cd:
        img = _render_chart(cd, brand)
        from PIL import Image as PILImage
        pi = PILImage.open(io.BytesIO(img))
        pw, ph = pi.size
        ih = 5.8
        iw = (pw/ph) * ih
        ix = (13.33-iw)/2
        sl.shapes.add_picture(io.BytesIO(img), Inches(ix), Inches(1.2),
                              width=Inches(iw), height=Inches(ih))
    _logo(sl, brand)

def _slide_two_col(sl, s, brand):
    _header(sl, s.get("title",""), brand)
    for col, x in [(s.get("left",{}), 0.4), (s.get("right",{}), 6.9)]:
        _text(sl, col.get("heading",""), x, 1.3, 5.8, 0.6,
              size=brand.typography.size_section, bold=True, color=brand.colors.accent, brand=brand)
        y = 2.05
        for item in col.get("items",[]):
            _text(sl, f"• {item}", x, y, 5.8, 0.55,
                  size=brand.typography.size_body, color=brand.colors.text_dark, brand=brand)
            y += 0.58
    _logo(sl, brand)

def _slide_stats(sl, s, brand):
    _header(sl, s.get("title",""), brand)
    stats = s.get("stats",[])
    cw = 13.33 / max(len(stats),1)
    for i, st in enumerate(stats):
        x = i*cw + 0.3
        _text(sl, st.get("value",""), x, 1.8, cw-0.4, 1.4,
              size=52, bold=True, color=brand.colors.primary,
              align=PP_ALIGN.CENTER, font=brand.typography.font_heading, brand=brand)
        if st.get("trend"):
            tc = brand.colors.success if "+" in st["trend"] else brand.colors.danger
            _text(sl, st["trend"], x, 3.3, cw-0.4, 0.5,
                  size=18, bold=True, color=tc, align=PP_ALIGN.CENTER, brand=brand)
        _text(sl, st.get("label",""), x, 3.9, cw-0.4, 0.5,
              size=brand.typography.size_caption, color=brand.colors.text_muted,
              align=PP_ALIGN.CENTER, brand=brand)
    _logo(sl, brand)

def _slide_closing(sl, s, brand):
    _rect(sl, 0, 0, 13.33, 7.5, brand.colors.bg_dark)
    _text(sl, s.get("title","Спасибо!"), 1, 1.8, 11.3, 1.5,
          size=brand.typography.size_title, bold=True,
          color=brand.colors.bg_light, align=PP_ALIGN.CENTER,
          font=brand.typography.font_heading, brand=brand)
    y = 3.8
    for item in s.get("content",[]):
        _text(sl, f"• {item.get('text','')}", 2, y, 9.3, 0.6,
              size=brand.typography.size_body, color=brand.colors.accent,
              align=PP_ALIGN.CENTER, brand=brand)
        y += 0.65
    if brand.slide_defaults.footer_text:
        _text(sl, brand.slide_defaults.footer_text, 0.3, 7.0, 12, 0.4,
              size=11, color=brand.colors.text_muted, align=PP_ALIGN.CENTER, brand=brand)
    _logo(sl, brand)


# ── Графики ──────────────────────────────────────────────────────────────────
def _render_chart(cd: dict, brand) -> bytes:
    kind   = cd.get("kind","bar")
    labels = cd.get("labels",[])
    series = cd.get("series",[])
    colors = brand.chart_colors(len(series) or 1)

    fig, ax = plt.subplots(figsize=(11, 5.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for sp in ["top","right"]: ax.spines[sp].set_visible(False)
    for sp in ["left","bottom"]: ax.spines[sp].set_color("#E2E8F0")
    ax.tick_params(colors="#64748B")
    ax.yaxis.grid(True, color="#E2E8F0", linewidth=0.7)
    ax.set_axisbelow(True)

    if kind == "bar":
        x  = np.arange(len(labels))
        bw = 0.7 / max(len(series),1)
        for i,s in enumerate(series):
            off = (i-(len(series)-1)/2)*bw
            ax.bar(x+off, s["values"], width=bw*0.88, color=colors[i], label=s.get("name",""))
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=12)

    elif kind == "line":
        for i,s in enumerate(series):
            ax.plot(labels, s["values"], color=colors[i],
                    linewidth=2.5, marker="o", markersize=5, label=s.get("name",""))

    elif kind in ("pie","doughnut"):
        vals = series[0]["values"] if series else []
        wp   = {"width":0.5} if kind=="doughnut" else {}
        ax.pie(vals, labels=labels, colors=colors,
               autopct="%1.0f%%", startangle=90, wedgeprops=wp,
               textprops={"fontsize":12,"color":"#1A1A2E"})

    if cd.get("title"):
        ax.set_title(cd["title"], fontsize=14, fontweight="bold",
                     color=brand.colors.primary_hex, pad=12)
    if len(series) > 1:
        ax.legend(fontsize=11, framealpha=0)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
