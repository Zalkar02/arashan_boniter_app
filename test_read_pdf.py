from pathlib import Path
import sys

from pypdf import PdfReader


def main() -> int:
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1]).expanduser()
    else:
        pdf_path = Path("/home/zuko/Downloads/face_племкарт.pdf")

    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
        return 1

    reader = PdfReader(str(pdf_path))
    print(f"Файл: {pdf_path}")
    print(f"Страниц: {len(reader.pages)}")
    print("=" * 60)

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        print(f"Страница {index}")
        print("-" * 60)
        print(text.strip())
        print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
