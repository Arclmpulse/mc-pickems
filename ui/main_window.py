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
from ui.dashboard_view import DashboardView
from ui.sidebar import Sidebar
from ui.swiss_view import SwissView
from ui.bracket_view import BracketView
from ui.double_elim_view import DoubleElimView
from ui.group_stage_view import GroupStageView
from ui.wc_bracket_view import WCBracketView
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
        self._stage_views = {}
        self._stages_needing_refresh = set()

        self._setup_ui()

        # Show dashboard home screen on startup
        self._show_dashboard()

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

    def _show_dashboard(self) -> None:
        """Show the one-time startup dashboard. Navigating away destroys it."""
        self._tab_bar.setVisible(False)
        self._name_label.setText("Pickems")
        self._accuracy_label.setText("<span style='color: #8b949e;'>✓  —</span>")

        # Hide sidebar with slide animation
        self._set_sidebar_visible(False, animate=False)

        dashboard = DashboardView(self._tournaments_dir, self._saves_dir)
        # Cross-fade transition: fade dashboard out, then load the tournament
        dashboard.navigate_requested.connect(self._begin_navigate)
        dashboard._faded_out.connect(lambda: None)  # placeholder; real handler set in _begin_navigate
        self._stack.addWidget(dashboard)
        self._stack.setCurrentWidget(dashboard)
        # No outer fade-in here — applying QGraphicsOpacityEffect directly to a
        # QScrollArea prevents the viewport from laying out all its children
        # correctly on first paint. The card stagger animations handle the intro.

    def _begin_navigate(self, tournament_dir: str) -> None:
        """Start the cross-fade-out then load the tournament."""
        # Find the dashboard in the stack
        dashboard = self._stack.currentWidget()
        if isinstance(dashboard, DashboardView):
            # Disconnect old faded_out connections and wire the real one
            try:
                dashboard._faded_out.disconnect()
            except Exception:
                pass
            dashboard._faded_out.connect(
                lambda d=tournament_dir: self._load_tournament(d)
            )
            dashboard.fade_out(220)
        else:
            self._load_tournament(tournament_dir)

    def _set_sidebar_visible(self, visible: bool, animate: bool = True) -> None:
        """Show or hide the sidebar, optionally with a slide animation."""
        target_w = 210 if visible else 0
        current_w = self.sidebar.width()
        if current_w == target_w:
            return

        if not animate:
            self.sidebar.setMinimumWidth(target_w)
            self.sidebar.setMaximumWidth(target_w)
            self.sidebar.setVisible(visible)
            return

        if visible:
            self.sidebar.show()

        self._sidebar_anim = QParallelAnimationGroup()
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self.sidebar, prop)
            a.setDuration(280)
            a.setStartValue(current_w)
            a.setEndValue(target_w)
            a.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self._sidebar_anim.addAnimation(a)

        if not visible:
            try:
                self._sidebar_anim.finished.disconnect()
            except Exception:
                pass
            self._sidebar_anim.finished.connect(self.sidebar.hide)

        self._sidebar_anim.start()

    def _load_tournament(self, tournament_dir: str) -> None:
        # Restore tab bar and sidebar
        self._tab_bar.setVisible(True)
        self._set_sidebar_visible(True, animate=True)
        # Disconnect old manager
        if self.manager:
            try:
                self.manager.state_changed.disconnect()
            except Exception:
                pass
            self.manager.deleteLater()

        # Clear old views from stack
        while self._stack.count():
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.deleteLater()

        self._stage_views.clear()
        self._stages_needing_refresh.clear()
        self._current_view = None

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

        # Get or create view
        if idx in self._stage_views:
            view = self._stage_views[idx]
            self._stack.setCurrentWidget(view)
            if idx in self._stages_needing_refresh:
                if hasattr(view, "refresh"):
                    view.refresh()
                self._stages_needing_refresh.discard(idx)
        else:
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
            elif stage["type"] == "group_stage":
                view = GroupStageView(self.manager, stage, self._cache_dir)
                view.state_changed.connect(self._update_accuracy)
            elif stage["type"] == "wc_bracket":
                view = WCBracketView(self.manager, stage, self._cache_dir)
                view.state_changed.connect(self._update_accuracy)
            else:
                view = QWidget()
            
            self._stage_views[idx] = view
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

        self._update_accuracy()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_state_changed(self) -> None:
        """Called when results.json changes or a pick is made."""
        # Mark all other stages as needing refresh
        if self.manager:
            for i in range(len(self.manager.stages)):
                if i != self._current_stage_idx:
                    self._stages_needing_refresh.add(i)

        # Refresh the current stage view immediately
        if self._current_view and hasattr(self._current_view, "refresh"):
            self._current_view.refresh()
        self._update_accuracy()

    def _toggle_sidebar(self) -> None:
        visible = self.sidebar.width() <= 100
        self._set_sidebar_visible(visible, animate=True)

    def _update_accuracy(self) -> None:
        if not self.manager:
            self._accuracy_label.setText("<span style='color: #8b949e;'>✓  —</span>")
            return

        # Stage accuracy (current tab only)
        stage_id = None
        if self._current_stage_idx < len(self.manager.stages):
            stage_id = self.manager.stages[self._current_stage_idx]["id"]

        stage_correct, stage_total, stage_pct = self.manager.get_accuracy_stats(stage_id=stage_id)
        event_correct, event_total, event_pct = self.manager.get_accuracy_stats()

        if stage_total == 0:
            stage_str = "<span style='color: #8b949e;'>Stage: —</span>"
        else:
            stage_str = (
                f"<span style='color: #8b949e;'>Stage:</span> "
                f"<span style='color: #3fb950; font-weight: 600;'>{stage_pct:.0f}%</span> "
                f"<span style='color: #8b949e;'>({stage_correct}/{stage_total})</span>"
            )

        if event_total == 0:
            event_str = "<span style='color: #8b949e;'>Event: —</span>"
        else:
            event_str = (
                f"<span style='color: #8b949e;'>Event:</span> "
                f"<span style='color: #3fb950; font-weight: 600;'>{event_pct:.0f}%</span> "
                f"<span style='color: #8b949e;'>({event_correct}/{event_total})</span>"
            )

        self._accuracy_label.setText(f"{stage_str}  <span style='color: #30363d;'>|</span>  {event_str}")

    # ── Logo caching ──────────────────────────────────────────────────────────

    def _cache_logos_background(self) -> None:
        """Download missing logos and pre-cache other tournaments' stats in a background thread (non-blocking)."""
        if not self.manager:
            return

        # Discover all tournament directories to pre-cache
        to_precache = []
        parent_dir = self.manager.tournament_dir.parent
        if parent_dir.exists():
            for d in parent_dir.iterdir():
                if d.is_dir() and d != self.manager.tournament_dir:
                    t_json = d / "tournament.json"
                    if t_json.exists():
                        to_precache.append(d)

        teams_to_cache = []
        for stage in self.manager.stages:
            for team in stage.get("teams", []):
                if team.get("logo_url"):
                    teams_to_cache.append((team["id"], team["logo_url"]))

        # Remove duplicates
        seen = set()
        unique = [(tid, url) for tid, url in teams_to_cache if tid not in seen and not seen.add(tid)]

        import threading
        import time

        def _do_cache():
            # 1. Pre-populate tournament accuracy stats cache
            for d in to_precache:
                d_str = str(d)
                if d_str not in TournamentManager._other_accuracy_cache:
                    try:
                        # Instantiate temporary manager to populate cache
                        mgr = TournamentManager(d_str, str(self._saves_dir), watch=False)
                        mgr.deleteLater()
                    except Exception:
                        pass

            # 2. Cache logos
            for tid, url in unique:
                self.manager.ensure_logo_cached(tid, url, self._cache_dir)
                time.sleep(0.5)  # Be polite to logo hosts
            
            def trigger_refresh():
                if self._current_view and hasattr(self._current_view, "refresh"):
                    self._current_view.refresh()
                self._update_accuracy()
            QTimer.singleShot(0, trigger_refresh)

        thread = threading.Thread(target=_do_cache, daemon=True)
        thread.start()
