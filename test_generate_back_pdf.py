import datetime
import os

from pypdf import PdfWriter

from db.models import Sheep, init_db
import services.passport_print_service as pps
from services.passport_print_service import _build_back_pdf_page
from state_paths import ensure_state_dir, STATE_DIR


OUTPUT_PATH = os.path.join(STATE_DIR, "exports", "test_back_generated.pdf")
SAMPLE_ID_N = "996000000050003"
LINE_EXTRA_OVERRIDES = {
    "{id}":20,
    "{nick}": 45,
    "{breed}": 20
}
LINE_STROKE_WIDTH = 0.4


def _pick_sheep(session, gender: str | None = None):
    query = session.query(Sheep)
    if gender:
        query = query.filter_by(gender=gender)
    return query.order_by(Sheep.id.desc()).first()


def main():
    ensure_state_dir()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    session = init_db()
    pps.LINE_EXTRA_BY_PLACEHOLDER.update(LINE_EXTRA_OVERRIDES)
    pps.LINE_STROKE_WIDTH = LINE_STROKE_WIDTH

    sheep = session.query(Sheep).filter_by(id_n=SAMPLE_ID_N).first()
    candidates = []
    if sheep is not None:
        candidates.append(sheep)
    else:
        ewe = _pick_sheep(session, "O")
        ram = _pick_sheep(session, "B")
        if ewe is not None:
            candidates.append(ewe)
        if ram is not None:
            candidates.append(ram)

    if not candidates:
        raise RuntimeError("Нет овец в базе для тестовой генерации оборота.")

    writer = PdfWriter()
    for item in candidates:
        page = _build_back_pdf_page({"sheep": item})
        writer.add_page(page)

    with open(OUTPUT_PATH, "wb") as fh:
        writer.write(fh)

    print(f"OK: {OUTPUT_PATH} ({len(candidates)} стр.)")


if __name__ == "__main__":
    main()
