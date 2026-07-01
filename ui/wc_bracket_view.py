"""
World Cup 2026 knockout bracket view.

5-round single elimination: R32 (16 matches) → R16 (8) → QF (4) → SF (2) → Final (1).
Laid out as 5 scrollable horizontal columns.
"""

from pathlib import Path
from typing import Optional, Dict, List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy,
)

from data.manager import TournamentManager
from engine.wc_bracket import WCBracketState, WCMatch
from ui.match_card import MatchCard
from ui.utils import find_local_logo


class _WCColumn(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl = QLabel(title)
        lbl.setObjectName("bracket-round-label")
        layout.addWidget(lbl)
        self._layout = layout

    def add_card(self, card: QWidget) -> None:
        self._layout.addWidget(card)

    def add_spacer(self, h: int) -> None:
        sp = QWidget()
        sp.setFixedHeight(h)
        self._layout.addWidget(sp)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)


class WCBracketView(QScrollArea):
    """32-team WC knockout bracket view."""

    state_changed = pyqtSignal()

    def __init__(
        self,
        manager: TournamentManager,
        stage_config: dict,
        cache_dir: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.manager = manager
        self.stage_config = stage_config
        self.stage_id = stage_config["id"]
        self.cache_dir = cache_dir

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content_layout = QHBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 16, 16, 16)
        self._content_layout.setSpacing(16)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self._content)

        self._build()

    def refresh(self) -> None:
        h = self.horizontalScrollBar().value()
        v = self.verticalScrollBar().value()
        self._clear()
        self._build()
        QTimer.singleShot(0, lambda: (
            self.horizontalScrollBar().setValue(h),
            self.verticalScrollBar().setValue(v),
        ))
        self.state_changed.emit()

    def _clear(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build(self) -> None:
        state: WCBracketState = self.manager.compute_stage_state(self.stage_config)
        if not state:
            return
        logo_cache = {tid: find_local_logo(self.cache_dir, tid) for tid in state.teams}

        r32, r16, qf, sf, final_rnd = state.rounds

        # Check lock status of each round
        r32_locked = any(self.manager.is_locked(m.match_id) for m in r32)
        r16_locked = any(self.manager.is_locked(m.match_id) for m in r16)
        qf_locked = any(self.manager.is_locked(m.match_id) for m in qf)
        sf_locked = any(self.manager.is_locked(m.match_id) for m in sf)
        final_locked = any(self.manager.is_locked(m.match_id) for m in final_rnd)

        r32_title = "Round of 32  🔒" if r32_locked else "Round of 32"
        r16_title = "Round of 16  🔒" if r16_locked else "Round of 16"
        qf_title = "Quarterfinals  🔒" if qf_locked else "Quarterfinals"
        sf_title = "Semifinals  🔒" if sf_locked else "Semifinals"
        final_title = "Final  🔒" if final_locked else "Final"

        # ── Round of 32 ─────────────────────────────────────────────────────
        col_r32 = _WCColumn(r32_title)
        col_r32.add_spacer(6)
        for m in r32:
            col_r32.add_card(self._make_card(m, state, logo_cache))
            col_r32.add_spacer(16)
        col_r32.add_stretch()
        self._content_layout.addWidget(col_r32)

        # ── Round of 16 ─────────────────────────────────────────────────────
        col_r16 = _WCColumn(r16_title)
        col_r16.add_spacer(57)
        for i, m in enumerate(r16):
            col_r16.add_card(self._make_card(m, state, logo_cache))
            if i < len(r16) - 1:
                col_r16.add_spacer(118)
        col_r16.add_stretch()
        self._content_layout.addWidget(col_r16)

        # ── Quarterfinals ────────────────────────────────────────────────────
        col_qf = _WCColumn(qf_title)
        col_qf.add_spacer(159)
        for i, m in enumerate(qf):
            col_qf.add_card(self._make_card(m, state, logo_cache))
            if i < len(qf) - 1:
                col_qf.add_spacer(322)
        col_qf.add_stretch()
        self._content_layout.addWidget(col_qf)

        # ── Semifinals ────────────────────────────────────────────────────────
        col_sf = _WCColumn(sf_title)
        col_sf.add_spacer(363)
        for i, m in enumerate(sf):
            col_sf.add_card(self._make_card(m, state, logo_cache))
            if i < len(sf) - 1:
                col_sf.add_spacer(730)
        col_sf.add_stretch()
        self._content_layout.addWidget(col_sf)

        # ── Final ─────────────────────────────────────────────────────────────
        col_fin = _WCColumn(final_title)
        col_fin.add_spacer(771)
        col_fin.add_card(self._make_card(final_rnd[0], state, logo_cache))
        col_fin.add_stretch()
        self._content_layout.addWidget(col_fin)

        self._content_layout.addStretch(1)

    def _make_card(
        self,
        match: WCMatch,
        state: WCBracketState,
        logo_cache: Dict[str, Optional[str]],
    ) -> QWidget:
        if not match.team1_id or not match.team2_id:
            placeholder = QWidget()
            placeholder.setFixedHeight(86)
            placeholder.setFixedWidth(200)
            placeholder.setStyleSheet(
                "background: #0d1117; border: 1px dashed #21262d; border-radius: 5px;"
            )
            lbl = QLabel("TBD")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #30363d; font-size: 11px; background: transparent;")
            from PyQt6.QtWidgets import QVBoxLayout as _VL
            vl = _VL(placeholder)
            vl.addWidget(lbl)
            return placeholder

        t1 = state.teams[match.team1_id]
        t2 = state.teams[match.team2_id]

        card = MatchCard(
            match_id=match.match_id,
            team1_id=match.team1_id,
            team1_name=t1.name,
            team1_seed=t1.seed,
            team1_wins=0, team1_losses=0,
            team2_id=match.team2_id,
            team2_name=t2.name,
            team2_seed=t2.seed,
            team2_wins=0, team2_losses=0,
            match_type="bo1",
            logo1_path=logo_cache.get(match.team1_id),
            logo2_path=logo_cache.get(match.team2_id),
        )
        card.setFixedWidth(220)

        picked = self.manager.get_pick(match.match_id)
        actual = self.manager.find_result_winner(
            self.stage_id, match.round_num, match.team1_id, match.team2_id, match.match_id
        )
        locked = self.manager.is_locked(match.match_id)
        card.apply_pick_state(picked, actual, locked)
        card.pick_made.connect(self._on_pick_made)
        return card

    def _on_pick_made(self, match_id: str, team_id: str) -> None:
        self.manager.make_pick(match_id, team_id)
