"""
Main application window.

Layout:
  ┌────────┬──────────────────────────────────────────────────────┐
  │        │  Header (tournament name · accuracy counter)         │
  │Sidebar ├──────────────────────────────────────────────────────┤
  │        │  Stage tabs                                          │
  │        ├──────────────────────────────────────────────────────┤
  │        │  Stage view (SwissView or BracketView)               │
  └────────┴──────────────────────────────────────────────────────┘
"""

import json
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QTimer, QEasingCurve, QPropertyAnimation, QParallelAnimationGroup
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QSizePolicy, QFrame,
    QGraphicsOpacityEffect,
)

from data.manager import TournamentManager
from ui.sidebar import Sidebar
from ui.swiss_view import SwissView
from ui.bracket_view import BracketView
from ui.double_elim_view import DoubleElimView
from ui.utils import set_prop


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pickems")
        self.setMinimumSize(1000, 680)
        self.resize(1440, 860)

        # Directory paths relative to this file's parent (project root)
        self._root = Path(__file__).resolve().parent.parent
        self._tournaments_dir = self._root / "tournaments"
        self._saves_dir = self._root / "saves"
        self._cache_dir = self._root / "cache" / "logos"

        self.manager: Optional[TournamentManager] = None
        self._current_stage_idx: int = 0
        self._stage_tab_buttons: List[QPushButton] = []
        self._current_view: Optional[QWidget] = None

        self._setup_ui()

        # Auto-load first tournament found
        first = self._discover_first_tournament()
        if first:
            self._load_tournament(first)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(self._tournaments_dir)
        self.sidebar.tournament_selected.connect(self._load_tournament)
        root_layout.addWidget(self.sidebar)

        # Right content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        # Header
        self._header = self._build_header()
        content_layout.addWidget(self._header)

        # Stage tab bar
        self._tab_bar = self._build_tab_bar()
        content_layout.addWidget(self._tab_bar)

        # Stage view stack
        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack, 1)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 0, 20, 0)
        layout.setSpacing(12)

        # Toggle sidebar button
        self._toggle_sidebar_btn = QPushButton("☰")
        self._toggle_sidebar_btn.setObjectName("toggle-sidebar-btn")
        self._toggle_sidebar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_sidebar_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._toggle_sidebar_btn)

        self._name_label = QLabel("Pickems")
        self._name_label.setObjectName("tournament-name-label")
        layout.addWidget(self._name_label)

        layout.addStretch()

        self._accuracy_label = QLabel()
        self._accuracy_label.setObjectName("accuracy-label")
        self._accuracy_label.setText("<span style='color: #8b949e;'>✓  —</span>")
        layout.addWidget(self._accuracy_label, 0, Qt.AlignmentFlag.AlignVCenter)

        return header

    def _build_tab_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("stage-tab-bar")
        self._tab_layout = QHBoxLayout(bar)
        self._tab_layout.setContentsMargins(12, 0, 12, 0)
        self._tab_layout.setSpacing(0)
        self._tab_layout.addStretch()
        return bar

    # ── Tournament loading ────────────────────────────────────────────────────

    def _discover_first_tournament(self) -> Optional[str]:
        if not self._tournaments_dir.exists():
            return None
        for d in sorted(self._tournaments_dir.iterdir()):
            if d.is_dir() and (d / "tournament.json").exists():
                return str(d)
        return None

    def _load_tournament(self, tournament_dir: str) -> None:
        # Disconnect old manager
        if self.manager:
            try:
                self.manager.state_changed.disconnect()
            except Exception:
                pass
            self.manager.deleteLater()

        self.manager = TournamentManager(tournament_dir, str(self._saves_dir))
        self.manager.state_changed.connect(self._on_state_changed)

        self._name_label.setText(self.manager.tournament_name)
        self._rebuild_tabs()
        self._update_accuracy()
        self._cache_logos_background()

        # Show first stage
        self._current_stage_idx = 0
        self._show_stage(0)

        # Update sidebar active state
        self.sidebar.set_active_tournament(tournament_dir)

    def _rebuild_tabs(self) -> None:
        # Remove all old tab buttons
        while self._tab_layout.count() > 1:  # keep trailing stretch
            item = self._tab_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._stage_tab_buttons.clear()

        if not self.manager:
            return

        for i, stage in enumerate(self.manager.stages):
            btn = QPushButton(stage["name"])
            btn.setObjectName("stage-tab")
            btn.clicked.connect(lambda checked, idx=i: self._show_stage(idx))
            self._tab_layout.insertWidget(i, btn)
            self._stage_tab_buttons.append(btn)

    def _show_stage(self, idx: int) -> None:
        if not self.manager:
            return
        if idx >= len(self.manager.stages):
            return

        self._current_stage_idx = idx

        # Update tab active states
        for i, btn in enumerate(self._stage_tab_buttons):
            set_prop(btn, "active", "true" if i == idx else "false")

        # Destroy old view
        if self._current_view is not None:
            self._stack.removeWidget(self._current_view)
            self._current_view.deleteLater()
            self._current_view = None

        stage = self.manager.stages[idx]

        if stage["type"] == "swiss":
            view = SwissView(self.manager, stage, self._cache_dir)
            view.state_changed.connect(self._update_accuracy)
        elif stage["type"] == "single_elim":
            view = BracketView(self.manager, stage, self._cache_dir)
            view.state_changed.connect(self._update_accuracy)
        elif stage["type"] == "double_elim":
            view = DoubleElimView(self.manager, stage, self._cache_dir)
            view.state_changed.connect(self._update_accuracy)
        else:
            view = QWidget()

        self._stack.addWidget(view)
        self._stack.setCurrentWidget(view)
        self._current_view = view

        # Add beautiful fade-in transition
        opacity_effect = QGraphicsOpacityEffect(view)
        view.setGraphicsEffect(opacity_effect)
        
        self._fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_state_changed(self) -> None:
        """Called when results.json changes or a pick is made."""
        # Refresh the current stage view
        if self._current_view and hasattr(self._current_view, "refresh"):
            self._current_view.refresh()
        self._update_accuracy()

    def _toggle_sidebar(self) -> None:
        start_w = self.sidebar.width()
        end_w = 0 if start_w > 100 else 210

        self._sidebar_anim = QParallelAnimationGroup()

        anim_min = QPropertyAnimation(self.sidebar, b"minimumWidth")
        anim_min.setDuration(250)
        anim_min.setStartValue(start_w)
        anim_min.setEndValue(end_w)
        anim_min.setEasingCurve(QEasingCurve.Type.InOutQuad)

        anim_max = QPropertyAnimation(self.sidebar, b"maximumWidth")
        anim_max.setDuration(250)
        anim_max.setStartValue(start_w)
        anim_max.setEndValue(end_w)
        anim_max.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._sidebar_anim.addAnimation(anim_min)
        self._sidebar_anim.addAnimation(anim_max)

        if end_w > 0:
            self.sidebar.show()

        try:
            self._sidebar_anim.finished.disconnect()
        except Exception:
            pass

        if end_w == 0:
            self._sidebar_anim.finished.connect(self.sidebar.hide)

        self._sidebar_anim.start()

    def _update_accuracy(self) -> None:
        if not self.manager:
            self._accuracy_label.setText("<span style='color: #8b949e;'>✓  —</span>")
            return
        correct, total, pct = self.manager.get_accuracy_stats()
        if total == 0:
            self._accuracy_label.setText("<span style='color: #8b949e;'>✓  —</span>")
        else:
            self._accuracy_label.setText(
                f"<span style='color: #3fb950; font-weight: bold;'>✓</span>  "
                f"<span style='color: #e6edf3; font-weight: 600;'>{pct:.0f}%</span>  "
                f"<span style='color: #8b949e;'>({correct}/{total})</span>"
            )

    # ── Logo caching ──────────────────────────────────────────────────────────

    def _cache_logos_background(self) -> None:
        """Download missing logos in a background thread (non-blocking)."""
        if not self.manager:
            return
        teams_to_cache = []
        for stage in self.manager.stages:
            for team in stage.get("teams", []):
                if team.get("logo_url"):
                    teams_to_cache.append((team["id"], team["logo_url"]))

        # Remove duplicates
        seen = set()
        unique = [(tid, url) for tid, url in teams_to_cache if tid not in seen and not seen.add(tid)]

        if not unique:
            return

        import threading
        import time

        def _do_cache():
            for tid, url in unique:
                self.manager.ensure_logo_cached(tid, url, self._cache_dir)
                time.sleep(0.5)  # Be polite to logo hosts
            
            def trigger_refresh():
                if self._current_view and hasattr(self._current_view, "refresh"):
                    self._current_view.refresh()
            QTimer.singleShot(0, trigger_refresh)

        thread = threading.Thread(target=_do_cache, daemon=True)
        thread.start()
