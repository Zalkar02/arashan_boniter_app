import json
from services.pdf_runtime import import_pymupdf


PDFS = {
    "matka": "/home/zuko/Projects/Python/arashan_boniter_app/assets/passport_template/back_page_matka.pdf",
    "baran": "/home/zuko/Projects/Python/arashan_boniter_app/assets/passport_template/back_page_baran.pdf",
}


def main():
    fitz = import_pymupdf()
    result = {}
    for key, path in PDFS.items():
        doc = fitz.open(path)
        page = doc[0]
        blocks = []
        for b in page.get_text("blocks"):
            x0, y0, x1, y1, text, *_ = b
            t = " ".join(text.split())
            if not t:
                continue
            blocks.append(
                {
                    "text": t,
                    "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                }
            )
        result[key] = {
            "page_size": [page.rect.width, page.rect.height],
            "blocks": blocks,
        }
        doc.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
