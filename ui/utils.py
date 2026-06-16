"""
Shared UI utilities.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QFontMetrics
from PyQt6.QtWidgets import QWidget, QLabel


def set_prop(widget: QWidget, prop: str, value) -> None:
    """Set a dynamic QSS property and trigger a style refresh."""
    widget.setProperty(prop, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class ElidedLabel(QLabel):
    """A QLabel that automatically elides text to fit its width, preventing layout overflow."""
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setWordWrap(False)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        fm = self.fontMetrics()
        rect = self.contentsRect()
        elided = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, rect.width())

        align = self.alignment()
        color = self.palette().color(self.foregroundRole())
        painter.setPen(color)
        painter.drawText(rect, align, elided)
        painter.end()


def load_logo(logo_path: Optional[str], size: int = 20) -> Optional[QPixmap]:
    """
    Load a team logo from a local path (SVG or raster).
    Returns a QPixmap scaled to `size × size`, or None on failure.
    """
    if not logo_path:
        return None
    p = Path(logo_path)
    if not p.exists():
        return None

    try:
        if p.suffix.lower() == ".svg":
            # Try QtSvg first (best quality)
            try:
                from PyQt6.QtSvg import QSvgRenderer
                from PyQt6.QtGui import QPainter
                renderer = QSvgRenderer(str(p))
                if renderer.isValid():
                    pm = QPixmap(size, size)
                    pm.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pm)
                    renderer.render(painter)
                    painter.end()
                    return pm
            except ImportError:
                pass
            # Fall back to direct QPixmap load (works if Qt has SVG plugin)
            pm = QPixmap(str(p))
            if not pm.isNull():
                return pm.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return None
        else:
            pm = QPixmap(str(p))
            if pm.isNull():
                return None
            return pm.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    except Exception:
        return None


def load_game_icon(game_id: str, tournaments_dir: Path, size: int = 20) -> Optional[QPixmap]:
    """
    Search for a game logo image inside `tournaments_dir` (e.g. tournaments/cs.png).
    Returns a scaled QPixmap, or None if not found.
    """
    if not tournaments_dir.exists():
        return None
    for ext in (".svg", ".png", ".webp", ".jpg", ".jpeg"):
        p = tournaments_dir / f"{game_id}{ext}"
        if p.exists():
            return load_logo(str(p), size)
    return None
