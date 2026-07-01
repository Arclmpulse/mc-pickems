"""
Sidebar widget.

Shows a game list with collapsible tournament lists.
Emits tournament_selected(tournament_dir_path) when a tournament is clicked.
"""

from pathlib import Path
from typing import List, Dict

from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
)

from ui.utils import set_prop, load_game_icon


class GameSection(QWidget):
    """A collapsible section for a single game in the sidebar."""

    def __init__(self, game_id: str, game_name: str, emoji_char: str, tournaments_dir: Path, parent=None):
        super().__init__(parent)
        self.game_id = game_id
        self.game_name = game_name
        self.emoji_char = emoji_char
        self.tournaments_dir = tournaments_dir
        self._expanded = True

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Header button
        self.header_btn = QPushButton()
        self.header_btn.setObjectName("sidebar-game-header")
        self.header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn_layout = QHBoxLayout(self.header_btn)
        btn_layout.setContentsMargins(12, 0, 12, 0)
        btn_layout.setSpacing(8)

        # Try to load game icon
        icon_pm = load_game_icon(game_id, tournaments_dir, 24)
        if icon_pm:
            self.icon_lbl = QLabel()
            self.icon_lbl.setPixmap(icon_pm)
            self.icon_lbl.setFixedSize(24, 24)
            self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.icon_lbl = QLabel(emoji_char)
            self.icon_lbl.setObjectName("sidebar-game-icon")
        
        self.icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        btn_layout.addWidget(self.icon_lbl)

        self.name_lbl = QLabel(game_name)
        self.name_lbl.setObjectName("sidebar-game-name")
        self.name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        btn_layout.addWidget(self.name_lbl)

        btn_layout.addStretch()

        self.chevron_lbl = QLabel("▾" if self._expanded else "▸")
        self.chevron_lbl.setObjectName("sidebar-game-chevron")
        self.chevron_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        btn_layout.addWidget(self.chevron_lbl)

        self.header_btn.clicked.connect(self.toggle)
        self.layout.addWidget(self.header_btn)

        # Container for content (scrollable list of tournaments)
        self.container = QWidget()
        self.container.setObjectName("sidebar-game-container")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 2, 0, 4)
        self.container_layout.setSpacing(1)
        self.layout.addWidget(self.container)

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool, animate: bool = True):
        self._expanded = expanded
        self.chevron_lbl.setText("▾" if expanded else "▸")
        set_prop(self.header_btn, "expanded", "true" if expanded else "false")

        if not animate:
            if hasattr(self, "_anim") and self._anim.state() == QPropertyAnimation.State.Running:
                self._anim.stop()
            self.container.setVisible(expanded)
            self.container.setMaximumHeight(9999 if expanded else 0)
            return

        if expanded:
            self.container.setVisible(True)
            target_h = self.container.layout().sizeHint().height()
            if target_h <= 0:
                target_h = 100
        else:
            target_h = 0

        start_h = self.container.height()

        if hasattr(self, "_anim") and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        self._anim = QPropertyAnimation(self.container, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setStartValue(start_h)
        self._anim.setEndValue(target_h)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        try:
            self._anim.finished.disconnect()
        except Exception:
            pass

        if not expanded:
            self._anim.finished.connect(lambda: self.container.setVisible(False) if not self._expanded else None)
        else:
            self._anim.finished.connect(lambda: self.container.setMaximumHeight(9999) if self._expanded else None)

        self._anim.start()


class Sidebar(QWidget):
    """Left sidebar for game + tournament navigation."""

    tournament_selected = pyqtSignal(str)  # emits tournament directory path

    def __init__(self, tournaments_dir: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(210)
        self.setMaximumWidth(210)

        self._current_tournament: str = ""
        self._tournament_buttons: List[QPushButton] = []
        self._btn_paths: Dict[QPushButton, str] = {}
        self._tournaments_dir = tournaments_dir

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Logo container with fixed height of 56px to match main window header perfectly
        logo_container = QWidget()
        logo_container.setFixedHeight(56)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 0, 16, 0)
        logo_layout.setSpacing(0)

        logo_lbl = QLabel("⬡  Pickems")
        logo_lbl.setObjectName("sidebar-logo")
        logo_layout.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(logo_container)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #21262d;")
        outer.addWidget(sep)

        # Scroll area for content (games + tournaments)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("border: none; background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(0, 8, 0, 8)
        self._inner_layout.setSpacing(4)
        self._inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # Version label at the bottom
        version_lbl = QLabel("Version 3.1")
        version_lbl.setObjectName("sidebar-version")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(version_lbl)

        self._populate(tournaments_dir)

    def _populate(self, tournaments_dir: Path) -> None:
        self._btn_paths.clear()

        # ── CS section ──────────────────────────────────────────────────────
        self.cs_section = GameSection("cs", "Counter Strike", "⌖", tournaments_dir)
        self._inner_layout.addWidget(self.cs_section)

        cs_tournaments = self._discover(tournaments_dir, game="cs")
        if cs_tournaments:
            for t_dir, t_name in cs_tournaments:
                btn = QPushButton(t_name)
                btn.setObjectName("sidebar-tournament-btn")
                btn.clicked.connect(lambda checked, d=t_dir: self._select(d))
                self._tournament_buttons.append(btn)
                self._btn_paths[btn] = t_dir
                self.cs_section.container_layout.addWidget(btn)
        else:
            placeholder = QLabel("No tournaments found")
            placeholder.setStyleSheet("color: #30363d; font-size: 11px; padding: 6px 24px;")
            self.cs_section.container_layout.addWidget(placeholder)

        # ── LoL section ──────────────────────────────────────────────────────
        self.lol_section = GameSection("lol", "League of Legends", "⚔️", tournaments_dir)
        self._inner_layout.addWidget(self.lol_section)

        lol_tournaments = self._discover(tournaments_dir, game="lol")
        if lol_tournaments:
            for t_dir, t_name in lol_tournaments:
                btn = QPushButton(t_name)
                btn.setObjectName("sidebar-tournament-btn")
                btn.clicked.connect(lambda checked, d=t_dir: self._select(d))
                self._tournament_buttons.append(btn)
                self._btn_paths[btn] = t_dir
                self.lol_section.container_layout.addWidget(btn)
        else:
            placeholder = QLabel("No tournaments found")
            placeholder.setStyleSheet("color: #30363d; font-size: 11px; padding: 6px 24px;")
            self.lol_section.container_layout.addWidget(placeholder)

        # ── Football section ──────────────────────────────────────────────────
        self.football_section = GameSection("football", "Football", "⚽", tournaments_dir)
        self._inner_layout.addWidget(self.football_section)

        football_tournaments = self._discover(tournaments_dir, game="football")
        if football_tournaments:
            for t_dir, t_name in football_tournaments:
                btn = QPushButton(t_name)
                btn.setObjectName("sidebar-tournament-btn")
                btn.clicked.connect(lambda checked, d=t_dir: self._select(d))
                self._tournament_buttons.append(btn)
                self._btn_paths[btn] = t_dir
                self.football_section.container_layout.addWidget(btn)
        else:
            placeholder = QLabel("No tournaments found")
            placeholder.setStyleSheet("color: #30363d; font-size: 11px; padding: 6px 24px;")
            self.football_section.container_layout.addWidget(placeholder)

        # Default states: CS expanded, others collapsed
        self.cs_section.set_expanded(True, animate=False)
        self.lol_section.set_expanded(False, animate=False)
        self.football_section.set_expanded(False, animate=False)

    def _discover(self, tournaments_dir: Path, game: str) -> List[tuple]:
        """Find all tournament dirs for a given game slug."""
        import json
        result = []
        if not tournaments_dir.exists():
            return result
        for d in sorted(tournaments_dir.iterdir()):
            t_json = d / "tournament.json"
            if d.is_dir() and t_json.exists():
                try:
                    with open(t_json, encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("game", "cs") == game:
                        result.append((str(d), data.get("name", d.name)))
                except Exception:
                    pass
        return result

    def _select(self, tournament_dir: str) -> None:
        self._current_tournament = tournament_dir
        self._update_active_buttons(tournament_dir)
        self.tournament_selected.emit(tournament_dir)

    def set_active_tournament(self, tournament_dir: str) -> None:
        """Highlight the active tournament button."""
        self._current_tournament = tournament_dir
        self._update_active_buttons(tournament_dir)

        # Auto-expand the game section that contains the active tournament
        for btn, path in self._btn_paths.items():
            if path == tournament_dir:
                parent = btn.parent()
                while parent:
                    if isinstance(parent, GameSection):
                        parent.set_expanded(True, animate=True)
                        break
                    parent = parent.parent()

    def _update_active_buttons(self, active_dir: str) -> None:
        """Update which tournament button appears active."""
        for btn, path in self._btn_paths.items():
            set_prop(btn, "active", "true" if path == active_dir else "false")

    def rebuild(self, tournaments_dir: Path) -> None:
        """Rebuild the sidebar with new tournament data."""
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tournament_buttons.clear()
        self._populate(tournaments_dir)
