from pathlib import Path
from io import BytesIO
import datetime
import sqlite3

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from services.pdf_runtime import import_pymupdf
from state_paths import ensure_db_path

fitz = import_pymupdf()


PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
TEMPLATE_PATH_EWE = Path("/home/zuko/Projects/Python/arashan_boniter_app/assets/passport_template/face_page1_no_tables.pdf")
TEMPLATE_PATH_RAM = Path("/home/zuko/Projects/Python/arashan_boniter_app/assets/passport_template/face_page1_no_tables_baran.pdf")
OUTPUT_PATH = Path("/home/zuko/Projects/Python/arashan_boniter_app/.app_state/exports/test_face_generated.pdf")
SAMPLE_ID_N = "996000000050003"
FONT_CANDIDATES = [
    str(Path("/home/zuko/Projects/Python/arashan_boniter_app/assets/DejaVuSans.ttf")),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
LINE_EXTRA_BY_PLACEHOLDER = {
    "{id_n}": 70,
    "{breed}": 50,
    "{color}": 70,
    "{nick}": 150,
    "{dob}": 35,
    "{weight}": 8,
    "{birthCount}": 22,
    "{birth_place}": 250,
}
REPORTLAB_FONT = "DejaVuSans"
CURRENT_APP_ROWS = []
CURRENT_PARENT_ROWS = {"father": None, "mother": None}
CURRENT_SHEEP_DOB = ""


def cm(value: float) -> float:
    return value / 2.54 * 72


def y_from_top_cm(top_cm: float, height_cm: float = 0.0) -> float:
    page_height_cm = PAGE_HEIGHT / 72 * 2.54
    return cm(page_height_cm - top_cm - height_cm)


def replace_placeholder(page, placeholder: str, value: str, fontname: str = "Times-Roman"):
    rects = page.search_for(placeholder)
    if not rects:
        return
    fontfile = next((path for path in FONT_CANDIDATES if Path(path).exists()), None)
    for rect in rects:
        page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
    for rect in rects:
        fontsize = max(min(rect.height * 0.85, 10), 8)
        text_y = rect.y1 - 3.4
        font_name = "DejaVuSans" if fontfile else "helv"
        measure_font = "helv"
        text_length = fitz.get_text_length(value, fontname=measure_font, fontsize=fontsize) if value else 0
        if value:
            page.insert_text(
                fitz.Point(rect.x0 + 1, text_y),
                value,
                fontsize=fontsize,
                fontname=font_name,
                fontfile=fontfile,
                color=(0, 0, 0),
                overlay=True,
            )
        line_y = rect.y1 - 1.2
        extra = LINE_EXTRA_BY_PLACEHOLDER.get(placeholder, 24)
        line_end_x = min(rect.x1 + extra, max(rect.x1, rect.x0 + 1 + text_length + 4) + extra)
        page.draw_line(
            fitz.Point(rect.x0, line_y),
            fitz.Point(line_end_x, line_y),
            color=(0, 0, 0),
            width=0.6,
            overlay=True,
        )


def register_reportlab_font():
    if REPORTLAB_FONT in pdfmetrics.getRegisteredFontNames():
        return
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont(REPORTLAB_FONT, path))
            return
    raise RuntimeError("Не найден шрифт DejaVuSans для генерации PDF.")


def fmt_number(value):
    if value in (None, ""):
        return ""
    try:
        value = float(value)
    except Exception:
        return str(value)
    return str(int(value)) if value.is_integer() else f"{value:.1f}".rstrip("0").rstrip(".")


def calc_age(dob: str | None, on_date: str | None) -> str:
    if not dob or not on_date:
        return ""
    dob_y, dob_m, dob_d = [int(part) for part in str(dob).split("-")]
    dt_y, dt_m, dt_d = [int(part) for part in str(on_date).split("-")]
    years = dt_y - dob_y
    months = dt_m - dob_m
    if dt_d < dob_d:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return f"{max(0, years)}.{max(0, months)}"


def map_kurdyk(value):
    return {
        "raised": "Припод.",
        "medium": "Средн.",
        "lowered": "Опущ.",
    }.get(value, value or "")


def map_size(value):
    return {
        "big": "Крупн.",
        "medium": "Средн.",
        "small": "Мелк.",
    }.get(value, value or "")


def map_fur(value):
    return {
        "strong": "Крепк.",
        "loose": "Рыхл.",
    }.get(value, value or "")


def draw_row_values(pdf: canvas.Canvas, x_lines, top_y, bottom_y, values, font_size=7):
    pdf.setFont(REPORTLAB_FONT, font_size)
    baseline = PAGE_HEIGHT - ((top_y + bottom_y) / 2) - (font_size / 3)
    for index, value in enumerate(values):
        text = str(value or "").strip()
        if not text:
            continue
        left = x_lines[index]
        right = x_lines[index + 1]
        center_x = (left + right) / 2
        pdf.drawCentredString(center_x, baseline, text)


def build_main_row_values(app, sheep_dob: str):
    return [
        app["date"] or "",
        calc_age(sheep_dob, app["date"]),
        fmt_number(app["weight"]),
        fmt_number(app["crest_height"]),
        fmt_number(app["sacrum_height"]),
        fmt_number(app["oblique_torso"]),
        fmt_number(app["chest_width"]),
        fmt_number(app["chest_depth"]),
        fmt_number(app["maklokakh_width"]),
        fmt_number(app["chest_girth"]),
        fmt_number(app["kurdyk_girth"]),
        map_kurdyk(app["kurdyk_form"]),
        fmt_number(app["pasterns_girth"]),
        fmt_number(app["ears_height"]),
        fmt_number(app["ears_width"]),
        fmt_number(app["head_height"]),
        fmt_number(app["head_width"]),
        fmt_number(app["exterior"]),
        map_size(app["size"]),
        map_fur(app["fur_structure"]),
        str(app["rank"] or ""),
        str(app["note"] or ""),
        "",
    ]


def build_parent_row_values(app, sheep_dob: str):
    generated_on = datetime.date.today().isoformat()
    return [
        calc_age(sheep_dob, generated_on),
        fmt_number(app["weight"]),
        fmt_number(app["crest_height"]),
        fmt_number(app["sacrum_height"]),
        fmt_number(app["oblique_torso"]),
        fmt_number(app["chest_width"]),
        fmt_number(app["chest_depth"]),
        fmt_number(app["maklokakh_width"]),
        fmt_number(app["chest_girth"]),
        fmt_number(app["kurdyk_girth"]),
        map_kurdyk(app["kurdyk_form"]),
        fmt_number(app["pasterns_girth"]),
        fmt_number(app["ears_height"]),
        fmt_number(app["ears_width"]),
        fmt_number(app["head_height"]),
        fmt_number(app["head_width"]),
        fmt_number(app["exterior"]),
        map_size(app["size"]),
        map_fur(app["fur_structure"]),
        str(app["rank"] or ""),
        str(app["note"] or ""),
        "",
    ]


def build_overlay() -> BytesIO:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setLineWidth(0.35)
    register_reportlab_font()

    # Main bonitation table aligned to actual header column borders from the PDF template
    x_lines = [
        32.66, 84.78, 114.29, 144.04, 173.88, 203.73, 233.67, 263.54,
        290.62, 317.38, 347.24, 377.18, 420.46, 446.80, 475.29, 503.60,
        531.17, 559.64, 592.44, 634.25, 675.01, 715.71, 763.20, 810.10,
    ]
    y_top = 371.20
    row_height = cm(1.0)
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

    # Parents table aligned to the template width
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
    for idx, app in enumerate(CURRENT_APP_ROWS[:4]):
        row_top = y_top + row_height * idx
        row_bottom = row_top + row_height
        draw_row_values(pdf, x_lines, row_top, row_bottom, build_main_row_values(app, CURRENT_SHEEP_DOB), font_size=6.6)

    if CURRENT_PARENT_ROWS.get("father"):
        draw_row_values(
            pdf,
            parent_x_lines,
            parent_top,
            parent_mid,
            build_parent_row_values(CURRENT_PARENT_ROWS["father"]["app"], CURRENT_PARENT_ROWS["father"]["dob"]),
            font_size=6.2,
        )
    if CURRENT_PARENT_ROWS.get("mother"):
        draw_row_values(
            pdf,
            parent_x_lines,
            parent_mid,
            parent_bottom,
            build_parent_row_values(CURRENT_PARENT_ROWS["mother"]["app"], CURRENT_PARENT_ROWS["mother"]["dob"]),
            font_size=6.2,
        )

    pdf.save()
    buffer.seek(0)
    return buffer


def load_sample_data(id_n: str) -> dict:
    conn = sqlite3.connect(ensure_db_path())
    conn.row_factory = sqlite3.Row
    try:
        sheep = conn.execute(
            """
            SELECT s.*, c.name AS color_name, u.name AS owner_name, u.area AS owner_area,
                   u.region AS owner_region, u.city AS owner_city, u.home AS owner_home
            FROM sheep s
            LEFT JOIN colors c ON c.id = s.color_id
            LEFT JOIN users u ON u.id = s.owner_id
            WHERE s.id_n = ?
            """,
            (id_n,),
        ).fetchone()
        if sheep is None:
            raise RuntimeError(f"Овца с id_n={id_n} не найдена в базе.")

        applications = conn.execute(
            """
            SELECT *
            FROM applications
            WHERE sheep_id = ? AND COALESCE(is_deleted, 0) = 0
            ORDER BY date ASC, id ASC
            """,
            (sheep["id"],),
        ).fetchall()

        latest_app = applications[-1] if applications else None
        lamb = conn.execute(
            """
            SELECT *
            FROM lambs
            WHERE sheep_id = ? AND COALESCE(is_deleted, 0) = 0
            LIMIT 1
            """,
            (sheep["id"],),
        ).fetchone()

        parents = conn.execute(
            """
            SELECT p.id, p.id_n, p.nick, p.gender, p.dob
            FROM sheep_parents sp
            JOIN sheep p ON p.id = sp.parent_id
            WHERE sp.sheep_id = ?
            """,
            (sheep["id"],),
        ).fetchall()

        parent_rows = {"father": None, "mother": None}
        for parent in parents:
            latest_parent_app = conn.execute(
                """
                SELECT *
                FROM applications
                WHERE sheep_id = ? AND COALESCE(is_deleted, 0) = 0
                ORDER BY date DESC, id DESC
                LIMIT 1
                """,
                (parent["id"],),
            ).fetchone()
            if latest_parent_app is None:
                continue
            key = "father" if parent["gender"] == "B" else "mother"
            parent_rows[key] = {
                "app": latest_parent_app,
                "dob": parent["dob"] or "",
            }

        place_parts = [
            sheep["owner_name"],
            sheep["owner_area"],
            sheep["owner_region"],
            sheep["owner_city"],
            sheep["owner_home"],
        ]
        birth_place = ", ".join([str(part).strip() for part in place_parts if part])

        weight = ""
        if lamb is not None and lamb["weight"] is not None:
            weight_value = float(lamb["weight"])
            weight = str(int(weight_value)) if weight_value.is_integer() else str(lamb["weight"])

        return {
            "placeholders": {
                "{id_n}": sheep["id_n"] or "",
                "{breed}": "Арашан",
                "{color}": sheep["color_name"] or "",
                "{nick}": sheep["nick"] or "",
                "{dob}": sheep["dob"] or "",
                "{weight}": weight,
                "{birthCount}": str(lamb["litter_size"]) if lamb is not None and lamb["litter_size"] is not None else "",
                "{birth_place}": birth_place,
            },
            "gender": sheep["gender"] or "",
            "sheep_dob": sheep["dob"] or "",
            "applications": applications,
            "parents": parent_rows,
        }
    finally:
        conn.close()


def main() -> int:
    global CURRENT_APP_ROWS, CURRENT_PARENT_ROWS, CURRENT_SHEEP_DOB
    sample = load_sample_data(SAMPLE_ID_N)
    template_path = TEMPLATE_PATH_RAM if sample["gender"] == "B" else TEMPLATE_PATH_EWE
    doc = fitz.open(str(template_path))
    page = doc[0]
    replacements = sample["placeholders"]
    CURRENT_APP_ROWS = sample["applications"]
    CURRENT_PARENT_ROWS = sample["parents"]
    CURRENT_SHEEP_DOB = sample["sheep_dob"]
    for placeholder, value in replacements.items():
        replace_placeholder(page, placeholder, value)

    base_pdf = PdfReader(BytesIO(doc.tobytes()))
    doc.close()

    overlay_pdf = PdfReader(build_overlay())

    base_page = base_pdf.pages[0]
    base_page.merge_page(overlay_pdf.pages[0])

    writer = PdfWriter()
    writer.add_page(base_page)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "wb") as fh:
        writer.write(fh)

    print(f"Сохранено: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
