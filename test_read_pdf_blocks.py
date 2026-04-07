from pathlib import Path
import sys

from services.pdf_runtime import import_pymupdf

fitz = import_pymupdf()


def main() -> int:
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1]).expanduser()
    else:
        pdf_path = Path("/home/zuko/Downloads/face_племкарт.pdf")

    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
        return 1

    doc = fitz.open(str(pdf_path))
    print(f"Файл: {pdf_path}")
    print(f"Страниц: {doc.page_count}")
    print("=" * 80)

    for page_index in range(doc.page_count):
        page = doc[page_index]
        print(f"Страница {page_index + 1}")
        print("-" * 80)
        blocks = page.get_text("blocks")
        for block_index, block in enumerate(blocks, start=1):
            x0, y0, x1, y1, text, *_rest = block
            text = (text or "").strip()
            if not text:
                continue
            print(f"Блок {block_index}: ({x0:.2f}, {y0:.2f}) - ({x1:.2f}, {y1:.2f})")
            print(text)
            print("-" * 80)

    doc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
