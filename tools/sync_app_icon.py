from pathlib import Path

from PIL import Image
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QGuiApplication, QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer


SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_svg_to_png_bytes(svg_path: Path, size: int) -> bytes:
    renderer = QSvgRenderer(QByteArray(svg_path.read_bytes()))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG icon: {svg_path}")

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    buffer = QByteArray()
    from PyQt5.QtCore import QBuffer, QIODevice

    qbuffer = QBuffer(buffer)
    qbuffer.open(QIODevice.WriteOnly)
    image.save(qbuffer, b"PNG")
    return bytes(buffer)


def main():
    app = QGuiApplication([])
    project_root = Path(__file__).resolve().parent.parent
    svg_path = project_root / "assets" / "app_icon.svg"
    ico_path = project_root / "assets" / "app_icon.ico"

    images = []
    for size in SIZES:
        png_bytes = render_svg_to_png_bytes(svg_path, size)
        image = Image.open(__import__("io").BytesIO(png_bytes)).convert("RGBA")
        images.append(image)

    base = images[-1]
    base.save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
        append_images=images[:-1],
    )
    print(f"Updated {ico_path}")
    app.quit()


if __name__ == "__main__":
    main()
