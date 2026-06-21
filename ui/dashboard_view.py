"""
DashboardView — startup home screen.

Shown once on launch. Displays:
  • A hero strip with overall accuracy across all tournaments/games.
  • One game card per distinct game found in tournaments/.
    Each card shows the game icon (the only clickable element → navigates
    to the most recently created tournament for that game), the game name,
    an animated accuracy bar, and up to three recent tournament rows.

Adding a new sport requires no code changes here — it is discovered
automatically from tournament.json "game" fields.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve,
    QSequentialAnimationGroup, pyqtSignal, pyqtProperty,
)
from PyQt6.QtGui import QColor, QIcon, QPainter
from PyQt6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from data.manager import TournamentManager
from ui.utils import load_game_icon


# Display metadata for known games. Unknown games fall back gracefully.
_GAME_META: Dict[str, Tuple[str, str]] = {
    "cs":       ("Counter-Strike", "⌖"),
    "lol":      ("League of Legends", "⚔️"),
    "football": ("Football", "⚽"),
}


def _pct_color(pct: float) -> str:
    if pct >= 65:
        return "#3fb950"
    if pct >= 45:
        return "#e3b341"
    return "#f85149"


# ── Accuracy bar (animated) ───────────────────────────────────────────────────

class _AccuracyBar(QWidget):
    """Rounded bar that animates from 0 → target % on first show."""

    def __init__(self, target_pct: float, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._target_pct = max(0.0, min(100.0, target_pct))
        self._current_pct: float = 0.0
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim_started = False

    # Qt property so QPropertyAnimation can drive it
    def _get_fill(self) -> float:
        return self._current_pct

    def _set_fill(self, v: float) -> None:
        self._current_pct = v
        self.update()

    fill = pyqtProperty(float, fget=_get_fill, fset=_set_fill)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._anim_started and self._target_pct > 0:
            self._anim_started = True
            anim = QPropertyAnimation(self, b"fill", self)
            anim.setDuration(900)
            anim.setStartValue(0.0)
            anim.setEndValue(self._target_pct)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def paintEvent(self, _event) -> None:
        from PyQt6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        r = h / 2.0

        p.setBrush(QColor("#21262d"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        if self._current_pct > 0:
            fill_w = max(h, w * self._current_pct / 100.0)
            p.setBrush(QColor(_pct_color(self._target_pct)))
            p.drawRoundedRect(QRectF(0, 0, fill_w, h), r, r)

        p.end()


# ── Game card ─────────────────────────────────────────────────────────────────

class _GameCard(QWidget):
    """Card for a single game. Only the icon button is interactive."""

    navigate_requested = pyqtSignal(str)  # emits tournament dir path

    def __init__(
        self,
        game_id: str,
        tournaments_dir: Path,
        saves_dir: Path,
        stats: Dict[str, Tuple[int, int, float]],  # pre-computed: dir → (c, t, pct)
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("dashboard-game-card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        game_name, fallback_emoji = _GAME_META.get(game_id, (game_id.upper(), "🎮"))

        # Filter + sort tournaments for this game (newest dir mtime first)
        all_t = _filter_game_tournaments(game_id, tournaments_dir, stats)
        latest_dir = all_t[0][0] if all_t else None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # ── Header (icon + name + overall %) ─────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(14)

        icon_btn = QPushButton()
        icon_btn.setObjectName("dashboard-icon-btn")
        icon_btn.setFixedSize(60, 60)
        icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icon_btn.setToolTip(f"Open latest {game_name} tournament")
        if latest_dir:
            icon_btn.clicked.connect(
                lambda _c, d=latest_dir: self._on_icon_clicked(d)
            )
        else:
            icon_btn.setEnabled(False)

        pm = load_game_icon(game_id, tournaments_dir, 36)
        if pm:
            icon_btn.setIcon(QIcon(pm))
            icon_btn.setIconSize(QSize(36, 36))
        else:
            icon_btn.setText(fallback_emoji)

        header.addWidget(icon_btn)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)

        name_lbl = QLabel(game_name)
        name_lbl.setObjectName("dashboard-game-name")
        name_col.addWidget(name_lbl)

        total_c = sum(r[2] for r in all_t)
        total_t = sum(r[3] for r in all_t)
        overall_pct = (total_c / total_t * 100) if total_t else 0.0

        if total_t:
            col = _pct_color(overall_pct)
            acc_html = (
                f"<span style='color:{col}; font-weight:600;'>{overall_pct:.0f}%</span>"
                f"<span style='color:#484f58;'>  ·  {total_c}/{total_t} correct</span>"
            )
        else:
            acc_html = "<span style='color:#484f58;'>No picks recorded yet</span>"

        acc_lbl = QLabel(acc_html)
        acc_lbl.setObjectName("dashboard-overall-acc")
        acc_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_col.addWidget(acc_lbl)

        header.addLayout(name_col, 1)
        root.addLayout(header)

        # ── Animated accuracy bar ─────────────────────────────────────────────
        root.addWidget(_AccuracyBar(overall_pct if total_t else 0.0))

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setObjectName("separator")
        root.addWidget(sep)

        # ── Recent tournaments (up to 3) ──────────────────────────────────────
        recents_lbl = QLabel("Recent Tournaments")
        recents_lbl.setObjectName("dashboard-recents-header")
        root.addWidget(recents_lbl)

        shown = all_t[:3]
        if shown:
            for t_dir, t_name, t_c, t_t, t_pct in shown:
                root.addWidget(_make_tournament_row(t_name, t_c, t_t, t_pct))
        else:
            no_lbl = QLabel("No tournaments found")
            no_lbl.setObjectName("dashboard-no-tournaments")
            root.addWidget(no_lbl)

        root.addStretch()

    def _on_icon_clicked(self, d: str) -> None:
        self.navigate_requested.emit(d)


def _make_tournament_row(name: str, correct: int, total: int, pct: float) -> QWidget:
    row = QWidget()
    row.setObjectName("dashboard-tournament-row")
    row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    hl = QHBoxLayout(row)
    hl.setContentsMargins(10, 6, 10, 6)
    hl.setSpacing(8)

    name_lbl = QLabel(name)
    name_lbl.setObjectName("dashboard-tournament-name")
    hl.addWidget(name_lbl, 1)

    if total:
        pct_lbl = QLabel(f"{pct:.0f}%")
        pct_lbl.setStyleSheet(
            f"color: {_pct_color(pct)}; font-weight: 600;"
            " font-size: 12px; background: transparent;"
        )
        hl.addWidget(pct_lbl)
        sub = QLabel(f"({correct}/{total})")
        sub.setObjectName("dashboard-tournament-sub")
        hl.addWidget(sub)
    else:
        no = QLabel("—")
        no.setObjectName("dashboard-tournament-sub")
        hl.addWidget(no)

    return row


# ── Hero strip ────────────────────────────────────────────────────────────────

def _build_hero(stats: Dict[str, Tuple[int, int, float]]) -> QWidget:
    hero = QWidget()
    hero.setObjectName("dashboard-hero")
    hero.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    hl = QHBoxLayout(hero)
    hl.setContentsMargins(28, 22, 28, 22)
    hl.setSpacing(24)

    total_c = sum(v[0] for v in stats.values())
    total_t = sum(v[1] for v in stats.values())
    pct = (total_c / total_t * 100) if total_t else 0.0
    color = _pct_color(pct) if total_t else "#484f58"

    pct_lbl = QLabel(f"{pct:.0f}%" if total_t else "—")
    pct_lbl.setObjectName("dashboard-hero-pct")
    pct_lbl.setStyleSheet(f"color: {color}; background: transparent;")
    hl.addWidget(pct_lbl)

    vl = QVBoxLayout()
    vl.setSpacing(3)

    title_lbl = QLabel("Overall Accuracy")
    title_lbl.setObjectName("dashboard-hero-title")
    vl.addWidget(title_lbl)

    detail_text = (
        f"{total_c} correct out of {total_t} picks across all tournaments"
        if total_t else "Make some picks to see your accuracy here"
    )
    detail_lbl = QLabel(detail_text)
    detail_lbl.setObjectName("dashboard-hero-detail")
    vl.addWidget(detail_lbl)

    hl.addLayout(vl, 1)

    brand_lbl = QLabel("⬡  Pickems")
    brand_lbl.setObjectName("dashboard-hero-brand")
    hl.addWidget(brand_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

    return hero


# ── Main view ─────────────────────────────────────────────────────────────────

class DashboardView(QScrollArea):
    """
    Startup home screen. Emits navigate_requested(path) when a game icon is
    clicked — the caller is responsible for animating the transition.
    Everything else on the dashboard is non-interactive.
    """

    navigate_requested = pyqtSignal(str)  # path to navigate to after transition

    def __init__(
        self,
        tournaments_dir: Path,
        saves_dir: Path,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Compute all stats once — each tournament dir → (correct, total, pct)
        all_stats = _compute_all_stats(tournaments_dir, saves_dir)

        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(32, 32, 32, 32)
        main.setSpacing(24)

        main.addWidget(_build_hero(all_stats))

        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        cards_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        game_ids = _discover_game_ids(tournaments_dir)
        for delay_idx, gid in enumerate(game_ids):
            card = _GameCard(gid, tournaments_dir, saves_dir, all_stats)
            card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            card.setMinimumWidth(320)
            card.setMaximumWidth(460)
            card.navigate_requested.connect(self.navigate_requested)
            cards_row.addWidget(card)

            # Staggered fade-in per card
            fx = QGraphicsOpacityEffect(card)
            fx.setOpacity(0.0)
            card.setGraphicsEffect(fx)
            anim = QPropertyAnimation(fx, b"opacity", card)
            anim.setDuration(400)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            QTimer.singleShot(delay_idx * 90, anim.start)

        cards_row.addStretch()
        main.addLayout(cards_row)
        main.addStretch()

        self.setWidget(content)

    def fade_out(self, duration_ms: int = 220) -> None:
        """
        Fade the viewport out then emit _faded_out.
        Applied to self.viewport() (plain QWidget) rather than self
        (QScrollArea) to avoid the offscreen-pixmap layout bug that
        causes Qt to not render the scroll area's children properly.
        """
        target = self.viewport()
        fx = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InQuad)
        anim.finished.connect(self._faded_out)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    _faded_out = pyqtSignal()


# ── Module-level helpers ──────────────────────────────────────────────────────

def _compute_all_stats(
    tournaments_dir: Path,
    saves_dir: Path,
) -> Dict[str, Tuple[int, int, float]]:
    """
    Instantiate one non-watching TournamentManager per tournament dir and
    return a dict: dir_path → (correct, total, pct).
    Called once at DashboardView construction.
    """
    result: Dict[str, Tuple[int, int, float]] = {}
    if not tournaments_dir.exists():
        return result
    for d in tournaments_dir.iterdir():
        if not (d.is_dir() and (d / "tournament.json").exists()):
            continue
        try:
            mgr = TournamentManager(str(d), str(saves_dir), watch=False)
            c, t, p = mgr.get_accuracy_stats()
            mgr.deleteLater()
            result[str(d)] = (c, t, p)
        except Exception:
            result[str(d)] = (0, 0, 0.0)
    return result


def _discover_game_ids(tournaments_dir: Path) -> List[str]:
    """Return unique game IDs in the order they first appear (alphabetical dirs)."""
    seen: List[str] = []
    if not tournaments_dir.exists():
        return seen
    for d in sorted(tournaments_dir.iterdir()):
        tj = d / "tournament.json"
        if not (d.is_dir() and tj.exists()):
            continue
        try:
            with open(tj, encoding="utf-8") as f:
                gid = json.load(f).get("game", "cs")
            if gid not in seen:
                seen.append(gid)
        except Exception:
            pass
    return seen


def _filter_game_tournaments(
    game_id: str,
    tournaments_dir: Path,
    stats: Dict[str, Tuple[int, int, float]],
) -> List[Tuple[str, str, int, int, float]]:
    """
    Return list of (dir_path, name, correct, total, pct) for *game_id*,
    sorted by directory mtime descending (newest first).
    Uses pre-computed stats dict — no new manager instantiation.
    """
    raw: List[Tuple[str, str, int, int, float, float]] = []
    if not tournaments_dir.exists():
        return []
    for d in tournaments_dir.iterdir():
        tj = d / "tournament.json"
        if not (d.is_dir() and tj.exists()):
            continue
        try:
            with open(tj, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("game", "cs") != game_id:
                continue
            name = data.get("name", d.name)
            mtime = d.stat().st_mtime
            c, t, p = stats.get(str(d), (0, 0, 0.0))
            raw.append((str(d), name, c, t, p, mtime))
        except Exception:
            pass
    raw.sort(key=lambda x: x[5], reverse=True)
    return [(r[0], r[1], r[2], r[3], r[4]) for r in raw]
