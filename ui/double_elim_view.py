"""
Double elimination view component.
Lays out Upper and Lower bracket matches in horizontal lanes,
with the Grand Final situated on the right side.
"""

from pathlib import Path
from typing import Optional, Dict, List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy, QFrame
)

from data.manager import TournamentManager
from engine.double_elim import DoubleElimState, DoubleElimMatch
from ui.match_card import MatchCard
from ui.utils import set_prop, find_local_logo


class _DoubleElimColumn(QWidget):
    """A vertical column representing a round in the double-elimination bracket."""

    def __init__(self, title: str, top_spacer_height: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("round-column")
        self.setFixedWidth(220)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        if top_spacer_height > 0:
            sp = QWidget()
            sp.setFixedHeight(top_spacer_height)
            self._layout.addWidget(sp)

        lbl = QLabel(title)
        lbl.setObjectName("bracket-round-label")
        self._layout.addWidget(lbl)

    def add_card(self, card: QWidget) -> None:
        self._layout.addWidget(card)

    def add_spacer(self, h: int) -> None:
        sp = QWidget()
        sp.setFixedHeight(h)
        self._layout.addWidget(sp)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)


class DoubleElimView(QScrollArea):
    """Scrollable double-elimination bracket view."""

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
        self._content_layout.setSpacing(24)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self._content)

        self._build()

    def refresh(self) -> None:
        """Rebuild view and preserve scroll states."""
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
        state: DoubleElimState = self.manager.compute_stage_state(self.stage_config)
        logo_cache = self._build_logo_cache(state)

        # Compute dynamic top spacer for Grand Final column to align its round title with the others
        temp_lbl = QLabel("Upper Bracket")
        temp_lbl.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        header_h = temp_lbl.sizeHint().height()
        temp_lbl.deleteLater()
        gf_top_spacer = header_h + 20  # header height + left_side_layout spacing (20px)

        # Main horizontal layout: [Left Side Columns (Upper & Lower Brackets)] | [Right Side (Grand Final)]
        left_side_widget = QWidget()
        left_side_layout = QVBoxLayout(left_side_widget)
        left_side_layout.setContentsMargins(0, 0, 0, 0)
        left_side_layout.setSpacing(20)

        # Split matches by round columns
        if len(state.teams) == 4:
            self._build_4team_layout(left_side_layout, state, logo_cache)
        else:
            self._build_8team_layout(left_side_layout, state, logo_cache)

        self._content_layout.addWidget(left_side_widget, 0)

        # Vertical line divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("color: #21262d;")
        self._content_layout.addWidget(divider)

        # Grand Final Match Column on the right
        gf_match_id = f"{self.stage_id}_m6" if len(state.teams) == 4 else f"{self.stage_id}_m14"
        gf_match = next((m for r in state.rounds for m in r if m.match_id == gf_match_id), None)
        gf_locked = gf_match and self.manager.is_locked(gf_match.match_id)
        gf_title = "Grand Finals  🔒" if gf_locked else "Grand Finals"
        gf_col = _DoubleElimColumn(gf_title, top_spacer_height=gf_top_spacer)
        if gf_match:
            gf_col.add_spacer(140)
            gf_col.add_card(self._make_card(gf_match, state, logo_cache))
            gf_col.add_stretch()
        self._content_layout.addWidget(gf_col)
        self._content_layout.addStretch(1)

    def _build_4team_layout(self, parent_layout: QVBoxLayout, state: DoubleElimState, logo_cache: Dict[str, Optional[str]]) -> None:
        # GSL Play-in Upper Bracket
        upper_header = QLabel("Winners Bracket")
        upper_header.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        parent_layout.addWidget(upper_header)

        upper_row = QWidget()
        upper_row_layout = QHBoxLayout(upper_row)
        upper_row_layout.setContentsMargins(0, 0, 0, 0)
        upper_row_layout.setSpacing(24)

        m1 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m1")
        m2 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m2")
        m3 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m3")

        u1_locked = any(self.manager.is_locked(m.match_id) for m in (m1, m2))
        u2_locked = self.manager.is_locked(m3.match_id)

        u_col1 = _DoubleElimColumn("Opening Matches  🔒" if u1_locked else "Opening Matches")
        u_col1.add_card(self._make_card(m1, state, logo_cache))
        u_col1.add_card(self._make_card(m2, state, logo_cache))
        upper_row_layout.addWidget(u_col1)

        u_col2 = _DoubleElimColumn("Winners Match  🔒" if u2_locked else "Winners Match")
        u_col2.add_spacer(44)
        u_col2.add_card(self._make_card(m3, state, logo_cache))
        u_col2.add_stretch()
        upper_row_layout.addWidget(u_col2)
        upper_row_layout.addStretch(1)

        parent_layout.addWidget(upper_row)

        # GSL Play-in Lower Bracket
        lower_header = QLabel("Elimination Bracket")
        lower_header.setStyleSheet("color: #f85149; font-weight: bold; font-size: 13px;")
        parent_layout.addWidget(lower_header)

        lower_row = QWidget()
        lower_row_layout = QHBoxLayout(lower_row)
        lower_row_layout.setContentsMargins(0, 0, 0, 0)
        lower_row_layout.setSpacing(24)

        m4 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m4")
        m5 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m5")

        l1_locked = self.manager.is_locked(m4.match_id)
        l2_locked = self.manager.is_locked(m5.match_id)

        l_col1 = _DoubleElimColumn("Elimination Match  🔒" if l1_locked else "Elimination Match")
        l_col1.add_card(self._make_card(m4, state, logo_cache))
        lower_row_layout.addWidget(l_col1)

        l_col2 = _DoubleElimColumn("Decider Match  🔒" if l2_locked else "Decider Match")
        l_col2.add_spacer(44)
        l_col2.add_card(self._make_card(m5, state, logo_cache))
        l_col2.add_stretch()
        lower_row_layout.addWidget(l_col2)
        lower_row_layout.addStretch(1)

        parent_layout.addWidget(lower_row)

    def _build_8team_layout(self, parent_layout: QVBoxLayout, state: DoubleElimState, logo_cache: Dict[str, Optional[str]]) -> None:
        # Upper Bracket Section
        upper_header = QLabel("Upper Bracket")
        upper_header.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        parent_layout.addWidget(upper_header)

        upper_row = QWidget()
        upper_row_layout = QHBoxLayout(upper_row)
        upper_row_layout.setContentsMargins(0, 0, 0, 0)
        upper_row_layout.setSpacing(24)

        m1 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m1")
        m2 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m2")
        m3 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m3")
        m4 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m4")
        m5 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m5")
        m6 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m6")
        m7 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m7")

        u1_locked = any(self.manager.is_locked(m.match_id) for m in (m1, m2, m3, m4))
        u2_locked = any(self.manager.is_locked(m.match_id) for m in (m5, m6))
        u3_locked = self.manager.is_locked(m7.match_id)

        u_col1 = _DoubleElimColumn("Upper Round 1  🔒" if u1_locked else "Upper Round 1")
        u_col1.add_card(self._make_card(m1, state, logo_cache))
        u_col1.add_card(self._make_card(m2, state, logo_cache))
        u_col1.add_spacer(14)
        u_col1.add_card(self._make_card(m3, state, logo_cache))
        u_col1.add_card(self._make_card(m4, state, logo_cache))
        upper_row_layout.addWidget(u_col1)

        u_col2 = _DoubleElimColumn("Upper Semis  🔒" if u2_locked else "Upper Semis")
        u_col2.add_spacer(44)
        u_col2.add_card(self._make_card(m5, state, logo_cache))
        u_col2.add_spacer(100)
        u_col2.add_card(self._make_card(m6, state, logo_cache))
        u_col2.add_stretch()
        upper_row_layout.addWidget(u_col2)

        u_col3 = _DoubleElimColumn("Upper Final  🔒" if u3_locked else "Upper Final")
        u_col3.add_spacer(120)
        u_col3.add_card(self._make_card(m7, state, logo_cache))
        u_col3.add_stretch()
        upper_row_layout.addWidget(u_col3)

        # Fill column 4 spacer to align lower bracket Final column
        u_col4 = _DoubleElimColumn("")
        u_col4.add_stretch()
        upper_row_layout.addWidget(u_col4)
        upper_row_layout.addStretch(1)

        parent_layout.addWidget(upper_row)

        # Lower Bracket Section
        lower_header = QLabel("Lower Bracket")
        lower_header.setStyleSheet("color: #f85149; font-weight: bold; font-size: 13px;")
        parent_layout.addWidget(lower_header)

        lower_row = QWidget()
        lower_row_layout = QHBoxLayout(lower_row)
        lower_row_layout.setContentsMargins(0, 0, 0, 0)
        lower_row_layout.setSpacing(24)

        m8 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m8")
        m9 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m9")
        m10 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m10")
        m11 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m11")
        m12 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m12")
        m13 = next(m for r in state.rounds for m in r if m.match_id == f"{self.stage_id}_m13")

        l1_locked = any(self.manager.is_locked(m.match_id) for m in (m8, m9))
        l2_locked = any(self.manager.is_locked(m.match_id) for m in (m10, m11))
        l3_locked = self.manager.is_locked(m12.match_id)
        l4_locked = self.manager.is_locked(m13.match_id)

        l_col1 = _DoubleElimColumn("Lower Round 1  🔒" if l1_locked else "Lower Round 1")
        l_col1.add_card(self._make_card(m8, state, logo_cache))
        l_col1.add_card(self._make_card(m9, state, logo_cache))
        lower_row_layout.addWidget(l_col1)

        l_col2 = _DoubleElimColumn("Lower Round 2  🔒" if l2_locked else "Lower Round 2")
        l_col2.add_card(self._make_card(m10, state, logo_cache))
        l_col2.add_card(self._make_card(m11, state, logo_cache))
        lower_row_layout.addWidget(l_col2)

        l_col3 = _DoubleElimColumn("Lower Semis  🔒" if l3_locked else "Lower Semis")
        l_col3.add_spacer(44)
        l_col3.add_card(self._make_card(m12, state, logo_cache))
        l_col3.add_stretch()
        lower_row_layout.addWidget(l_col3)

        l_col4 = _DoubleElimColumn("Lower Final  🔒" if l4_locked else "Lower Final")
        l_col4.add_spacer(44)
        l_col4.add_card(self._make_card(m13, state, logo_cache))
        l_col4.add_stretch()
        lower_row_layout.addWidget(l_col4)
        lower_row_layout.addStretch(1)

        parent_layout.addWidget(lower_row)

    def _build_logo_cache(self, state: DoubleElimState) -> Dict[str, Optional[str]]:
        cache: Dict[str, Optional[str]] = {}
        for team_id in state.teams:
            cache[team_id] = find_local_logo(self.cache_dir, team_id)
        return cache

    def _make_card(
        self,
        match: DoubleElimMatch,
        state: DoubleElimState,
        logo_cache: Dict[str, Optional[str]],
    ) -> QWidget:
        if not match.team1_id or not match.team2_id:
            # Teams not yet determined
            placeholder = QWidget()
            placeholder.setFixedHeight(86)
            placeholder.setStyleSheet(
                "background: #0d1117; border: 1px dashed #21262d; border-radius: 5px;"
            )
            lbl = QLabel("TBD")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #30363d; font-size: 11px; background: transparent;")
            vl = QVBoxLayout(placeholder)
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
            match_type=match.match_type,
            logo1_path=logo_cache.get(match.team1_id),
            logo2_path=logo_cache.get(match.team2_id),
        )

        picked = self.manager.get_pick(match.match_id)
        actual = self.manager.find_result_winner(
            self.stage_id, match.round_num, match.team1_id, match.team2_id
        )
        locked = self.manager.is_locked(match.match_id)
        card.apply_pick_state(picked, actual, locked)
        card.pick_made.connect(self._on_pick_made)
        return card

    def _on_pick_made(self, match_id: str, team_id: str) -> None:
        self.manager.make_pick(match_id, team_id)
