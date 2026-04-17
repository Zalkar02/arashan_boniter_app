import datetime
import json
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from typing import Iterable

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from db.models import Application, Owner
from resource_paths import resource_path
from services.pdf_runtime import import_pymupdf
from services.owner_search_service import AREA_LABELS, REGION_LABELS
from state_paths import STATE_DIR, ensure_state_dir

fitz = import_pymupdf()


PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
TEMPLATE_DIR = resource_path("assets", "passport_template")
EXPORTS_DIR = os.path.join(STATE_DIR, "exports")
PRINT_SETTINGS_PATH = os.path.join(STATE_DIR, "print_settings.json")
PRINT_JOB_STATE_PATH = os.path.join(STATE_DIR, "pending_print_job.json")
DEFAULT_PRINT_BATCH_SIZE = 20
DEFAULT_BACK_PRINT_ORDER = "reverse"
FONT_NAME = "DejaVuSans"
FONT_CANDIDATES = [
    resource_path("assets", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
FRONT_LINE_EXTRA_BY_PLACEHOLDER = {
    "{id_n}": 70,
    "{breed}": 50,
    "{color}": 70,
    "{nick}": 150,
    "{dob}": 35,
    "{weight}": 8,
    "{birthCount}": 22,
    "{birth_place}": 250,
}
FRONT_LINE_STROKE_WIDTH = 0.6

BACK_LINE_EXTRA_BY_PLACEHOLDER = {
    "{id}": 20,
    "{nick}": 40,
    "{name}": 40,
    "{breed}": 20,
}
BACK_LINE_STROKE_WIDTH = 0.4

# Backward-compatible aliases used by test_generate_back_pdf.py.
LINE_EXTRA_BY_PLACEHOLDER = BACK_LINE_EXTRA_BY_PLACEHOLDER
LINE_STROKE_WIDTH = BACK_LINE_STROKE_WIDTH
BREED_NAME = "Арашан"
SUBTYPE_NAME = "мясо-сальных овец"
FACE_TEMPLATE_PDF_EWE = os.path.join(TEMPLATE_DIR, "face_page1_no_tables.pdf")
FACE_TEMPLATE_PDF_RAM = os.path.join(TEMPLATE_DIR, "face_page1_no_tables_baran.pdf")
BACK_TEMPLATE_PDF_EWE = os.path.join(TEMPLATE_DIR, "back_page_matka.pdf")
BACK_TEMPLATE_PDF_RAM = os.path.join(TEMPLATE_DIR, "back_page_baran.pdf")


def mm(value: float) -> float:
    return value / 25.4 * 72


def y_from_top_cm(top_cm: float, height_cm: float = 0.0) -> float:
    page_height_cm = PAGE_HEIGHT / 72 * 2.54
    return (page_height_cm - top_cm - height_cm) / 2.54 * 72


def _register_fonts():
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    for font_path in FONT_CANDIDATES:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))
            return
    raise RuntimeError("Не найден шрифт DejaVuSans для печати племкарты.")


def _fmt_date(value):
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")


def _fmt_number(value):
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return str(value)


def _animal_type_label(gender):
    return "БАРАН" if gender == "B" else "ОВЦЕМАТКА"

def _feminize_color(color_name: str) -> str:
    if not color_name:
        return ""
    name = color_name.strip()
    lower = name.lower()
    if lower.endswith(("ая", "яя")):
        return name
    if lower.endswith("ый"):
        return name[:-2] + "ая"
    if lower.endswith("ий"):
        return name[:-2] + "яя"
    if lower.endswith("ой"):
        return name[:-2] + "ая"
    return name


def _size_label(value):
    return {
        "big": "Крупный",
        "medium": "Средний",
        "small": "Мелкий",
    }.get(value, value or "")


def _fur_label(value):
    return {
        "strong": "Крепкая",
        "loose": "Рыхлая",
    }.get(value, value or "")


def _kurdyk_label(value):
    return {
        "raised": "Припод.",
        "medium": "Средн.",
        "lowered": "Приспущ.",
        "Приподнятый": "Припод.",
        "Средний": "Средн.",
        "Приспущенный": "Приспущ.",
        "Приспущенный ": "Приспущ.",
        "Опущенный": "Приспущ.",
    }.get(value, value or "")


def _calc_age(dob, on_date):
    if not dob or not on_date:
        return ""
    years = on_date.year - dob.year
    months = on_date.month - dob.month
    if on_date.day < dob.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return f"{max(0, years)}.{max(0, months)}"


def _calc_age_years(dob, on_date):
    if not dob or not on_date:
        return ""
    years = on_date.year - dob.year
    if (on_date.month, on_date.day) < (dob.month, dob.day):
        years -= 1
    return str(max(0, years))


def _get_parent(sheep, gender):
    return next((parent for parent in getattr(sheep, "parents", []) if getattr(parent, "gender", None) == gender), None)


def _get_latest_application(session, sheep):
    return (
        session.query(Application)
        .filter_by(sheep_id=sheep.id, is_deleted=False)
        .order_by(Application.date.desc().nullslast(), Application.id.desc())
        .first()
    )


def _get_owner_link(session, sheep, owner):
    if owner is None:
        return None
    return (
        session.query(Owner)
        .filter_by(sheep_id=sheep.id, owner_id=owner.id)
        .order_by(Owner.owner_bool.desc(), Owner.date1.desc().nullslast(), Owner.id.desc())
        .first()
    )


def _owner_place(owner):
    if owner is None:
        return ""
    name = str(getattr(owner, "name", "") or "").strip()
    patronymic_suffixes = (
        "ович",
        "евич",
        "ич",
        "овна",
        "евна",
        "ична",
    )
    parts_name = [p for p in name.split() if p]
    filtered_name_parts = []
    for token in parts_name:
        clean = token.strip(".,;:!?'\"()[]{}").lower()
        if any(clean.endswith(suffix) for suffix in patronymic_suffixes):
            continue
        filtered_name_parts.append(token)
    short_name = " ".join(filtered_name_parts)
    area_raw = str(getattr(owner, "area", "") or "").strip()
    region_raw = str(getattr(owner, "region", "") or "").strip()
    area_label = AREA_LABELS.get(area_raw, area_raw)
    if area_label.lower().endswith(" район"):
        area_label = area_label[:-6].strip()
    region_label = REGION_LABELS.get(region_raw, region_raw)
    parts = [
        short_name,
        area_label,
        region_label,
        str(getattr(owner, "city", "") or "").strip(),
    ]
    return ", ".join([part for part in parts if part])


def _get_first_owner_for_birth_place(session, sheep, fallback_owner=None):
    if sheep is None:
        return fallback_owner
    first_link = (
        session.query(Owner)
        .filter(Owner.sheep_id == sheep.id)
        .order_by(Owner.date1.asc().nullslast(), Owner.id.asc())
        .first()
    )
    first_owner = getattr(first_link, "owner", None) if first_link is not None else None
    return first_owner or fallback_owner


def _template_paths(gender: str):
    if gender == "B":
        return (
            FACE_TEMPLATE_PDF_RAM,
            BACK_TEMPLATE_PDF_RAM,
        )
    return (
        FACE_TEMPLATE_PDF_EWE,
        BACK_TEMPLATE_PDF_EWE,
    )


def _draw_background(pdf: canvas.Canvas, image_path: str):
    pdf.drawImage(ImageReader(image_path), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, mask="auto")


def _draw_text(pdf: canvas.Canvas, x_mm: float, y_mm: float, value, size: int = 10):
    text = str(value or "").strip()
    if not text:
        return
    pdf.setFont(FONT_NAME, size)
    pdf.drawString(mm(x_mm), mm(y_mm), text)


def _replace_placeholder(
    page,
    placeholder: str,
    value: str,
    fontname: str = "Times-Roman",
    line_map=None,
    line_width=None,
):
    rects = page.search_for(placeholder)
    if not rects:
        return
    text = str(value or "").strip()
    fontfile = next((path for path in FONT_CANDIDATES if os.path.exists(path)), None)
    for rect in rects:
        page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
    for rect in rects:
        fontsize = max(min(rect.height * 0.85, 10), 8)
        text_y = rect.y1 - 3.4
        font_name = FONT_NAME if fontfile else "helv"
        text_length = fitz.get_text_length(text, fontname="helv", fontsize=fontsize) if text else 0
        if text:
            page.insert_text(
                fitz.Point(rect.x0 + 1, text_y),
                text,
                fontsize=fontsize,
                fontname=font_name,
                fontfile=fontfile,
                color=(0, 0, 0),
                overlay=True,
            )
        line_y = rect.y1 - 1.2
        active_line_map = line_map or LINE_EXTRA_BY_PLACEHOLDER
        active_line_width = LINE_STROKE_WIDTH if line_width is None else line_width
        if placeholder.endswith("_id}"):
            extra = active_line_map.get("{id}", active_line_map.get(placeholder, 24))
        elif placeholder.endswith("_nick}") or placeholder.endswith("_name}"):
            extra = active_line_map.get("{nick}", active_line_map.get(placeholder, 24))
        elif placeholder.endswith("_breed}"):
            extra = active_line_map.get("{breed}", active_line_map.get(placeholder, 24))
        else:
            extra = active_line_map.get(placeholder, 24)
        line_end_x = min(rect.x1 + extra, max(rect.x1, rect.x0 + 1 + text_length + 4) + extra)
        page.draw_line(
            fitz.Point(rect.x0, line_y),
            fitz.Point(line_end_x, line_y),
            color=(0, 0, 0),
            width=active_line_width,
            overlay=True,
        )


def _erase_box(pdf: canvas.Canvas, x_mm: float, y_mm: float, width_mm: float, height_mm: float):
    pdf.saveState()
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setStrokeColorRGB(1, 1, 1)
    pdf.rect(mm(x_mm), mm(y_mm), mm(width_mm), mm(height_mm), stroke=0, fill=1)
    pdf.restoreState()


def _draw_centred_text(pdf: canvas.Canvas, x_mm: float, y_mm: float, value, size: int = 10):
    text = str(value or "").strip()
    if not text:
        return
    pdf.setFont(FONT_NAME, size)
    width = pdf.stringWidth(text, FONT_NAME, size)
    pdf.drawString(mm(x_mm) - width / 2, mm(y_mm), text)


def _fit_text(pdf: canvas.Canvas, text: str, max_width_mm: float, size: int, min_size: int = 6):
    current_size = size
    while current_size > min_size and pdf.stringWidth(text, FONT_NAME, current_size) > mm(max_width_mm):
        current_size -= 1
    return current_size


def _draw_line_value(pdf: canvas.Canvas, x_mm: float, y_mm: float, value, width_mm: float, size: int = 10, align: str = "left"):
    text = str(value or "").strip()
    if not text:
        return
    fitted_size = _fit_text(pdf, text, width_mm, size)
    pdf.setFont(FONT_NAME, fitted_size)
    text_width = pdf.stringWidth(text, FONT_NAME, fitted_size)
    x = mm(x_mm)
    max_width = mm(width_mm)
    if align == "center":
        x += max((max_width - text_width) / 2, 0)
    elif align == "right":
        x += max(max_width - text_width, 0)
    pdf.drawString(x, mm(y_mm), text)


def _draw_cell_value(pdf: canvas.Canvas, center_x_mm: float, y_mm: float, value, width_mm: float, size: int = 7):
    text = str(value or "").strip()
    if not text:
        return
    fitted_size = _fit_text(pdf, text, width_mm, size)
    pdf.setFont(FONT_NAME, fitted_size)
    text_width = pdf.stringWidth(text, FONT_NAME, fitted_size)
    pdf.drawString(mm(center_x_mm) - text_width / 2, mm(y_mm), text)


def _draw_row_values_pt(pdf: canvas.Canvas, x_lines, top_y, bottom_y, values, font_size=7):
    baseline = PAGE_HEIGHT - ((top_y + bottom_y) / 2) - (font_size / 3)
    for index, value in enumerate(values):
        text = str(value or "").strip()
        if not text:
            continue
        left = x_lines[index]
        right = x_lines[index + 1]
        center_x = (left + right) / 2
        cell_width = max(1.0, right - left - 2.0)
        fitted_size = font_size
        while fitted_size > 4.5 and pdf.stringWidth(text, FONT_NAME, fitted_size) > cell_width:
            fitted_size -= 0.2
        pdf.setFont(FONT_NAME, fitted_size)
        pdf.drawCentredString(center_x, baseline, text)


def _draw_wrapped_text(pdf: canvas.Canvas, x_mm: float, y_mm: float, value, width_mm: float, size: int = 10, line_step_mm: float = 4.0, max_lines: int = 2):
    text = str(value or "").strip()
    if not text:
        return

    pdf.setFont(FONT_NAME, size)
    max_width = mm(width_mm)
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdf.stringWidth(candidate, FONT_NAME, size) <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) >= max_lines - 1:
            break
    if current and len(lines) < max_lines:
        lines.append(current)

    for index, line in enumerate(lines[:max_lines]):
        pdf.drawString(mm(x_mm), mm(y_mm - line_step_mm * index), line)


def _rank_label(value):
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper == "E":
        return "Элита"
    if upper == "B":
        return "Брак"
    return text


def _build_main_row_values(application, sheep_dob):
    return [
        _fmt_date(getattr(application, "date", None)),
        _calc_age_years(sheep_dob, getattr(application, "date", None)),
        _fmt_number(getattr(application, "weight", None)),
        _fmt_number(getattr(application, "crest_height", None)),
        _fmt_number(getattr(application, "sacrum_height", None)),
        _fmt_number(getattr(application, "oblique_torso", None)),
        _fmt_number(getattr(application, "chest_width", None)),
        _fmt_number(getattr(application, "chest_depth", None)),
        _fmt_number(getattr(application, "maklokakh_width", None)),
        _fmt_number(getattr(application, "chest_girth", None)),
        _fmt_number(getattr(application, "kurdyk_girth", None)),
        _kurdyk_label(getattr(application, "kurdyk_form", None)),
        _fmt_number(getattr(application, "pasterns_girth", None)),
        _fmt_number(getattr(application, "ears_height", None)),
        _fmt_number(getattr(application, "ears_width", None)),
        _fmt_number(getattr(application, "head_height", None)),
        _fmt_number(getattr(application, "head_width", None)),
        _fmt_number(getattr(application, "exterior", None)),
        _size_label(getattr(application, "size", None)),
        _fur_label(getattr(application, "fur_structure", None)),
        _rank_label(getattr(application, "rank", None)),
        str(getattr(application, "note", None) or ""),
        "",
    ]


def _build_parent_row_values(application, parent_dob):
    generated_on = datetime.date.today()
    return [
        _calc_age(parent_dob, generated_on),
        _fmt_number(getattr(application, "weight", None)),
        _fmt_number(getattr(application, "crest_height", None)),
        _fmt_number(getattr(application, "sacrum_height", None)),
        _fmt_number(getattr(application, "oblique_torso", None)),
        _fmt_number(getattr(application, "chest_width", None)),
        _fmt_number(getattr(application, "chest_depth", None)),
        _fmt_number(getattr(application, "maklokakh_width", None)),
        _fmt_number(getattr(application, "chest_girth", None)),
        _fmt_number(getattr(application, "kurdyk_girth", None)),
        _kurdyk_label(getattr(application, "kurdyk_form", None)),
        _fmt_number(getattr(application, "pasterns_girth", None)),
        _fmt_number(getattr(application, "ears_height", None)),
        _fmt_number(getattr(application, "ears_width", None)),
        _fmt_number(getattr(application, "head_height", None)),
        _fmt_number(getattr(application, "head_width", None)),
        _fmt_number(getattr(application, "exterior", None)),
        _size_label(getattr(application, "size", None)),
        _fur_label(getattr(application, "fur_structure", None)),
        _rank_label(getattr(application, "rank", None)),
        str(getattr(application, "note", None) or ""),
        "",
    ]


def _draw_main_page(pdf: canvas.Canvas, session, row: dict, owner, draw_background: bool = False):
    sheep = row["sheep"]
    applications = sorted(
        row.get("applications") or [],
        key=lambda app: (
            getattr(app, "date", None) or datetime.date.min,
            getattr(app, "id", 0) or 0,
        ),
    )
    parent_father = _get_parent(sheep, "B")
    parent_mother = _get_parent(sheep, "O")
    father_app = _get_latest_application(session, parent_father) if parent_father else None
    mother_app = _get_latest_application(session, parent_mother) if parent_mother else None

    pdf.setLineWidth(0.35)

    x_lines = [
        32.66, 84.78, 114.29, 144.04, 173.88, 203.73, 233.67, 263.54,
        290.62, 317.38, 347.24, 377.18, 420.46, 446.80, 475.29, 503.60,
        531.17, 559.64, 592.44, 634.25, 675.01, 715.71, 763.20, 810.10,
    ]
    y_top = 371.20
    row_height = 1.0 / 2.54 * 72
    y_bottom = y_top + row_height * 4
    row_lines = [y_top + row_height, y_top + row_height * 2, y_top + row_height * 3]

    for x in x_lines:
        pdf.line(x, PAGE_HEIGHT - y_bottom, x, PAGE_HEIGHT - y_top)
    for y in row_lines:
        pdf.line(x_lines[0], PAGE_HEIGHT - y, x_lines[-1], PAGE_HEIGHT - y)
    pdf.rect(
        x_lines[0],
        PAGE_HEIGHT - y_bottom,
        x_lines[-1] - x_lines[0],
        y_bottom - y_top,
        stroke=1,
        fill=0,
    )

    parent_left = x_lines[1]
    parent_right = x_lines[-1]
    parent_top = 491.85
    parent_bottom = 545.10
    parent_mid = 518.47
    parent_x_lines = x_lines[1:]
    for x in parent_x_lines:
        pdf.line(x, PAGE_HEIGHT - parent_bottom, x, PAGE_HEIGHT - parent_top)
    pdf.line(parent_left, PAGE_HEIGHT - parent_mid, parent_right, PAGE_HEIGHT - parent_mid)
    pdf.rect(
        parent_left,
        PAGE_HEIGHT - parent_bottom,
        parent_right - parent_left,
        parent_bottom - parent_top,
        stroke=1,
        fill=0,
    )

    for idx, application in enumerate(applications[:4]):
        row_top = y_top + row_height * idx
        row_bottom = row_top + row_height
        _draw_row_values_pt(pdf, x_lines, row_top, row_bottom, _build_main_row_values(application, sheep.dob), font_size=6.6)

    if father_app is not None:
        _draw_row_values_pt(
            pdf,
            parent_x_lines,
            parent_top,
            parent_mid,
            _build_parent_row_values(father_app, getattr(parent_father, "dob", None)),
            font_size=6.2,
        )
    if mother_app is not None:
        _draw_row_values_pt(
            pdf,
            parent_x_lines,
            parent_mid,
            parent_bottom,
            _build_parent_row_values(mother_app, getattr(parent_mother, "dob", None)),
            font_size=6.2,
        )


def _build_face_pdf_page(session, row: dict, owner):
    sheep = row["sheep"]
    lamb = getattr(sheep, "lamb", None)
    face_template_pdf, _ = _template_paths(sheep.gender or "O")
    doc = fitz.open(face_template_pdf)
    page = doc[0]
    birth_owner = _get_first_owner_for_birth_place(session, sheep, fallback_owner=owner)

    color_name = getattr(getattr(sheep, "color", None), "name", "") or ""
    if (sheep.gender or "O") == "O":
        color_name = _feminize_color(color_name)

    replacements = {
        "{id_n}": getattr(sheep, "id_n", "") or "",
        "{breed}": BREED_NAME,
        "{color}": color_name,
        "{nick}": getattr(sheep, "nick", "") or "",
        "{dob}": _fmt_date(getattr(sheep, "dob", None)),
        "{weight}": _fmt_number(getattr(lamb, "weight", None)),
        "{birthCount}": _fmt_number(getattr(lamb, "litter_size", None)),
        "{birth_place}": _owner_place(birth_owner),
    }
    for placeholder, value in replacements.items():
        _replace_placeholder(
            page,
            placeholder,
            value,
            line_map=FRONT_LINE_EXTRA_BY_PLACEHOLDER,
            line_width=FRONT_LINE_STROKE_WIDTH,
        )

    pdf_bytes = doc.tobytes()
    doc.close()
    return PdfReader(BytesIO(pdf_bytes)).pages[0]


def _build_overlay_page(draw_fn, *args):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    draw_fn(pdf, *args)
    # Keep at least one drawable object so pypdf always sees a page.
    pdf.saveState()
    pdf.setStrokeColorRGB(1, 1, 1)
    pdf.line(0, 0, 0, 0)
    pdf.restoreState()
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def _draw_genealogy_block(pdf: canvas.Canvas, sheep, x_mm: float, y_mm: float, label_mode: str = "full"):
    raw_id = str(getattr(sheep, "id_n", "") or "").strip()
    digits = "".join(ch for ch in raw_id if ch.isdigit())
    short_id = (digits or raw_id)[-6:] if (digits or raw_id) else ""
    _draw_text(pdf, x_mm, y_mm, short_id, 9)
    nick = str(getattr(sheep, "nick", "") or "").strip()
    if nick:
        _draw_text(pdf, x_mm, y_mm - 8, nick, 9)
    _draw_text(pdf, x_mm, y_mm - 16, BREED_NAME, 9)


def _short_id(value: str) -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    core = digits or raw
    return core[-6:] if core else ""


def _draw_text_in_bbox(pdf: canvas.Canvas, bbox, text: str, size: int = 9, pad_x: float = 2.0):
    if not text:
        return
    x0, y0, x1, y1 = bbox
    height = max(0.0, y1 - y0)
    baseline = PAGE_HEIGHT - y1 + (height * 0.25)
    pdf.setFont(FONT_NAME, size)
    pdf.drawString(x0 + pad_x, baseline, text)


_BACK_GENEALOGY_CACHE = {}


def _get_back_genealogy_layout(template_path: str):
    cached = _BACK_GENEALOGY_CACHE.get(template_path)
    if cached is not None:
        return cached
    doc = fitz.open(template_path)
    page = doc[0]
    id_blocks = []
    nick_blocks = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = b
        t = " ".join(text.split())
        if not t:
            continue
        if t.startswith("Индивидуальный №") and "____" in t:
            id_blocks.append((x0, y0, x1, y1))
        if t.startswith("Кличка") and "____" in t:
            nick_blocks.append((x0, y0, x1, y1))
    id_blocks = sorted(id_blocks, key=lambda b: (b[1], b[0]))
    nick_blocks = sorted(nick_blocks, key=lambda b: (b[1], b[0]))

    used_nicks = set()
    nick_for_id = {}
    for idx, ibox in enumerate(id_blocks):
        best = None
        best_dist = None
        for nbox in nick_blocks:
            if nbox in used_nicks:
                continue
            if abs(nbox[0] - ibox[0]) > 12:
                continue
            dy = nbox[1] - ibox[3]
            if dy < -2 or dy > 30:
                continue
            dist = abs(dy)
            if best is None or dist < best_dist:
                best = nbox
                best_dist = dist
        if best is not None:
            nick_for_id[idx] = best
            used_nicks.add(best)

    layout = {"id": id_blocks, "nick": nick_for_id}
    doc.close()
    _BACK_GENEALOGY_CACHE[template_path] = layout
    return layout


def _draw_second_page(pdf: canvas.Canvas, session, row: dict, owner):
    sheep = row["sheep"]
    father = _get_parent(sheep, "B")
    mother = _get_parent(sheep, "O")
    father_father = _get_parent(father, "B") if father else None
    father_mother = _get_parent(father, "O") if father else None
    mother_father = _get_parent(mother, "B") if mother else None
    mother_mother = _get_parent(mother, "O") if mother else None

    _, back_template_pdf = _template_paths(sheep.gender or "O")
    layout = _get_back_genealogy_layout(back_template_pdf)
    id_boxes = layout.get("id", [])
    nick_boxes = layout.get("nick", {})
    ancestors = [father, father_father, father_mother, mother, mother_father, mother_mother]
    for idx, ancestor in enumerate(ancestors):
        if ancestor is None or idx >= len(id_boxes):
            continue
        _draw_text_in_bbox(pdf, id_boxes[idx], _short_id(getattr(ancestor, "id_n", "")), 9)
        nick_box = nick_boxes.get(idx)
        if nick_box is not None:
            _draw_text_in_bbox(pdf, nick_box, str(getattr(ancestor, "nick", "") or "").strip(), 9)

    _draw_text(pdf, 5, 6, "", 8)


def _build_back_pdf_page(row: dict):
    sheep = row["sheep"]
    _, back_template_pdf = _template_paths(sheep.gender or "O")
    doc = fitz.open(back_template_pdf)
    page = doc[0]
    father = _get_parent(sheep, "B")
    mother = _get_parent(sheep, "O")
    father_father = _get_parent(father, "B") if father else None
    father_mother = _get_parent(father, "O") if father else None
    mother_father = _get_parent(mother, "B") if mother else None
    mother_mother = _get_parent(mother, "O") if mother else None
    replacements = {
        "{breed}": BREED_NAME,
        "{f_breed}": BREED_NAME if father else "",
        "{m_breed}": BREED_NAME if mother else "",
        "{f_id}": _short_id(getattr(father, "id_n", "")) if father else "",
        "{f_nick}": str(getattr(father, "nick", "") or "") if father else "",
        "{f_name}": str(getattr(father, "nick", "") or "") if father else "",
        "{m_id}": _short_id(getattr(mother, "id_n", "")) if mother else "",
        "{m_nick}": str(getattr(mother, "nick", "") or "") if mother else "",
        "{m_name}": str(getattr(mother, "nick", "") or "") if mother else "",
        "{f_f_id}": _short_id(getattr(father_father, "id_n", "")) if father_father else "",
        "{f_f_nick}": str(getattr(father_father, "nick", "") or "") if father_father else "",
        "{f_f_name}": str(getattr(father_father, "nick", "") or "") if father_father else "",
        "{f_f_breed}": BREED_NAME if father_father else "",
        "{m_f_id}": _short_id(getattr(father_mother, "id_n", "")) if father_mother else "",
        "{m_f_nick}": str(getattr(father_mother, "nick", "") or "") if father_mother else "",
        "{m_f_name}": str(getattr(father_mother, "nick", "") or "") if father_mother else "",
        "{m_f_breed}": BREED_NAME if father_mother else "",
        "{f_m_id}": _short_id(getattr(mother_father, "id_n", "")) if mother_father else "",
        "{f_m_nick}": str(getattr(mother_father, "nick", "") or "") if mother_father else "",
        "{f_m_name}": str(getattr(mother_father, "nick", "") or "") if mother_father else "",
        "{f_m_breed}": BREED_NAME if mother_father else "",
        "{m_m_id}": _short_id(getattr(mother_mother, "id_n", "")) if mother_mother else "",
        "{m_m_nick}": str(getattr(mother_mother, "nick", "") or "") if mother_mother else "",
        "{m_m_name}": str(getattr(mother_mother, "nick", "") or "") if mother_mother else "",
        "{m_m_breed}": BREED_NAME if mother_mother else "",
    }
    for placeholder, value in replacements.items():
        _replace_placeholder(
            page,
            placeholder,
            value,
            line_map=LINE_EXTRA_BY_PLACEHOLDER,
            line_width=LINE_STROKE_WIDTH,
        )
    pdf_bytes = doc.tobytes()
    doc.close()
    return PdfReader(BytesIO(pdf_bytes)).pages[0]


def generate_passports_pdf(session, rows: Iterable[dict], owner=None):
    _register_fonts()
    ensure_state_dir()
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    printable_rows = [row for row in rows if row.get("can_print")]
    if not printable_rows:
        raise RuntimeError("Нет записей, доступных для печати.")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(EXPORTS_DIR, f"plemcard_{timestamp}.pdf")
    writer = PdfWriter()
    front_pages = []
    back_pages = []

    for row in printable_rows:
        template_page = _build_face_pdf_page(session, row, owner)
        overlay_page = _build_overlay_page(_draw_main_page, session, row, owner, False)
        template_page.merge_page(overlay_page)
        front_pages.append(template_page)

        back_template_page = _build_back_pdf_page(row)
        back_pages.append(back_template_page)

    for page in front_pages:
        writer.add_page(page)
    for page in back_pages:
        writer.add_page(page)

    with open(output_path, "wb") as fh:
        writer.write(fh)
    return output_path


def list_system_printers():
    if os.name == "nt":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            return []
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        printers = []
        for line in (result.stdout or "").splitlines():
            printer = line.strip()
            if printer and printer not in printers:
                printers.append(printer)
        return printers

    lpstat_path = shutil.which("lpstat")
    if lpstat_path is None:
        return []
    result = subprocess.run([lpstat_path, "-a"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    printers = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        printer = line.split()[0]
        if printer and printer not in printers:
            printers.append(printer)
    return printers


def get_saved_printer():
    if not os.path.exists(PRINT_SETTINGS_PATH):
        return ""
    try:
        with open(PRINT_SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return ""
    return str(data.get("printer_name") or "")


def save_selected_printer(printer_name: str):
    ensure_state_dir()
    current = {}
    if os.path.exists(PRINT_SETTINGS_PATH):
        try:
            with open(PRINT_SETTINGS_PATH, "r", encoding="utf-8") as fh:
                current = json.load(fh)
        except Exception:
            current = {}
    with open(PRINT_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        current["printer_name"] = printer_name or ""
        json.dump(current, fh, ensure_ascii=False, indent=2)


def get_print_batch_size():
    if not os.path.exists(PRINT_SETTINGS_PATH):
        return DEFAULT_PRINT_BATCH_SIZE
    try:
        with open(PRINT_SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return DEFAULT_PRINT_BATCH_SIZE
    value = data.get("print_batch_size", DEFAULT_PRINT_BATCH_SIZE)
    try:
        value = int(value)
    except Exception:
        return DEFAULT_PRINT_BATCH_SIZE
    return max(1, min(20, value))


def save_print_batch_size(batch_size: int):
    ensure_state_dir()
    current = {}
    if os.path.exists(PRINT_SETTINGS_PATH):
        try:
            with open(PRINT_SETTINGS_PATH, "r", encoding="utf-8") as fh:
                current = json.load(fh)
        except Exception:
            current = {}
    current["print_batch_size"] = max(1, min(20, int(batch_size)))
    with open(PRINT_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(current, fh, ensure_ascii=False, indent=2)


def get_back_print_order():
    if not os.path.exists(PRINT_SETTINGS_PATH):
        return DEFAULT_BACK_PRINT_ORDER
    try:
        with open(PRINT_SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return DEFAULT_BACK_PRINT_ORDER
    value = str(data.get("back_print_order", DEFAULT_BACK_PRINT_ORDER) or DEFAULT_BACK_PRINT_ORDER).strip()
    return value if value in {"forward", "reverse"} else DEFAULT_BACK_PRINT_ORDER


def save_back_print_order(order: str):
    ensure_state_dir()
    current = {}
    if os.path.exists(PRINT_SETTINGS_PATH):
        try:
            with open(PRINT_SETTINGS_PATH, "r", encoding="utf-8") as fh:
                current = json.load(fh)
        except Exception:
            current = {}
    current["back_print_order"] = "reverse" if order == "reverse" else "forward"
    with open(PRINT_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(current, fh, ensure_ascii=False, indent=2)


def get_pending_print_job():
    if not os.path.exists(PRINT_JOB_STATE_PATH):
        return None
    try:
        with open(PRINT_JOB_STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def save_pending_print_job(pdf_path: str, total_cards: int, owner_id=None, sheep_ids=None):
    ensure_state_dir()
    data = {
        "pdf_path": pdf_path,
        "total_cards": int(total_cards),
        "owner_id": owner_id,
        "sheep_ids": list(sheep_ids or []),
        "saved_at": datetime.datetime.now().isoformat(),
    }
    with open(PRINT_JOB_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def clear_pending_print_job():
    if os.path.exists(PRINT_JOB_STATE_PATH):
        os.remove(PRINT_JOB_STATE_PATH)


def print_pdf_page_range(pdf_path: str, start_page: int, end_page: int, printer_name: str | None = None):
    if start_page <= 0 or end_page < start_page:
        raise RuntimeError("Некорректный диапазон страниц для печати.")

    selected_printer = printer_name if printer_name is not None else get_saved_printer()

    if os.name == "nt":
        try:
            if selected_printer:
                os.startfile(pdf_path, "printto", f'"{selected_printer}"')
            else:
                os.startfile(pdf_path, "print")
        except AttributeError:
            raise RuntimeError("Печать через os.startfile недоступна в этой сборке Python.")
        except OSError as exc:
            raise RuntimeError(f"Не удалось отправить файл на печать: {exc}") from exc
        if selected_printer:
            return f"Документ отправлен на печать в принтер: {selected_printer}"
        return "Документ отправлен на печать в принтер по умолчанию."

    lp_path = shutil.which("lp")
    if lp_path is None:
        raise RuntimeError("Не найдена команда lp для отправки на печать.")

    cmd = [lp_path, "-o", "media=A4", "-P", f"{start_page}-{end_page}"]
    if selected_printer:
        cmd.extend(["-d", selected_printer])
    cmd.append(pdf_path)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Не удалось отправить на печать.").strip()
        scheduler_probe = subprocess.run(
            ["lpstat", "-p", "-d"],
            capture_output=True,
            text=True,
        )
        scheduler_status = (scheduler_probe.stderr or scheduler_probe.stdout or "").strip()
        if "Scheduler is not running" in scheduler_status:
            raise RuntimeError(
                "Система печати CUPS не запущена. Запусти службу печати и проверь, что принтер добавлен."
            )
        if "no system default destination" in scheduler_status and not selected_printer:
            raise RuntimeError(
                "Не задан принтер по умолчанию. Добавь принтер в системе или выбери его явно."
            )
        raise RuntimeError(message)
    return (result.stdout or "Документ отправлен на печать.").strip()


def print_pdf_pages(pdf_path: str, pages: list[int], printer_name: str | None = None):
    if not pages:
        raise RuntimeError("Не выбраны страницы для печати.")
    if min(pages) <= 0:
        raise RuntimeError("Некорректные номера страниц для печати.")

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    invalid = [page for page in pages if page > total_pages]
    if invalid:
        raise RuntimeError("Запрошены страницы, которых нет в PDF.")

    writer = PdfWriter()
    for page_number in pages:
        writer.add_page(reader.pages[page_number - 1])

    ensure_state_dir()
    with tempfile.NamedTemporaryFile(prefix="print_pages_", suffix=".pdf", dir=STATE_DIR, delete=False) as tmp:
        temp_pdf_path = tmp.name

    try:
        with open(temp_pdf_path, "wb") as fh:
            writer.write(fh)
        return print_pdf_page_range(temp_pdf_path, 1, len(pages), printer_name=printer_name)
    finally:
        try:
            os.remove(temp_pdf_path)
        except OSError:
            pass
