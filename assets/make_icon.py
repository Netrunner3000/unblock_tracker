"""One-off generator for the app icon (run manually, not at app runtime).

An eye on a violet gradient: the app watches whether a profile is visible.

    python assets/make_icon.py

Drawn with QPainter rather than PIL so icon generation needs nothing the app
does not already depend on. Each size is rendered natively instead of being
downsampled from one master, which keeps the stroke crisp at 16px.
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)

ASSETS = Path(__file__).resolve().parent
ICONSET = ASSETS / "icon.iconset"

VIOLET_TOP = QColor("#6D4AE0")
VIOLET_BOTTOM = QColor("#3B2192")
WHITE = QColor("#FFFFFF")

SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Rounded-square tile with a diagonal gradient.
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, VIOLET_TOP)
    gradient.setColorAt(1.0, VIOLET_BOTTOM)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    painter.fillPath(tile, QBrush(gradient))

    # Eye outline: two mirrored curves meeting at the corners.
    centre = size / 2
    half_width = size * 0.30
    lid = size * 0.168  # how far each lid bows from the centre line

    eye = QPainterPath()
    eye.moveTo(centre - half_width, centre)
    eye.quadTo(QPointF(centre, centre - lid * 2), QPointF(centre + half_width, centre))
    eye.quadTo(QPointF(centre, centre + lid * 2), QPointF(centre - half_width, centre))

    stroke = max(1.5, size * 0.062)
    pen = QPen(WHITE, stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(eye)

    # Pupil.
    pupil = size * 0.092
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(centre, centre), pupil, pupil)

    painter.end()
    return image


def main() -> int:
    QGuiApplication([])  # QImage/QPainter need an application instance.
    ICONSET.mkdir(exist_ok=True)

    for name, px in SIZES.items():
        if not draw_icon(px).save(str(ICONSET / name)):
            print(f"Failed to write {name}", file=sys.stderr)
            return 1

    icns = ASSETS / "icon.icns"
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(icns)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    print(f"Wrote {len(SIZES)} PNGs to {ICONSET}")
    print(f"Wrote {icns} ({icns.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
