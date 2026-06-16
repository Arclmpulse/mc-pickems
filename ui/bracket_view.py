"""
Single elimination bracket view (Legends stage).

Laid out as three column groups: Quarterfinals | Semifinals | Final.
Teams shown as match cards, aligned so bracket A is on top and B is below.
"""

from pathlib import Path
from typing import Optional, Dict

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy,
)

from data.manager import TournamentManager
from engine.bracket import BracketState, BracketMatch
from ui.match_card import MatchCard
from ui.utils import set_prop


class _BracketColumn(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl = QLabel(title)
        lbl.setObjectName("bracket-round-label")
        layout.addWidget(lbl)
        self._layout = layout

    def add_half_label(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("bracket-half-label")
        self._layout.addWidget(lbl)

    def add_card(self, card: MatchCard) -> None:
        self._layout.addWidget(card)

    def add_spacer(self, h: int) -> None:
        sp = QWidget()
        sp.setFixedHeight(h)
        self._layout.addWidget(sp)

    def add_tbd(self) -> None:
        lbl = QLabel("TBD")
        lbl.setFixedHeight(86)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "color: #30363d; font-size: 11px; background: #0d1117;"
            "border: 1px dashed #21262d; border-radius: 5px;"
        )
        self._layout.addWidget(lbl)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)


class BracketView(QScrollArea):
    """8-team single elimination bracket view."""

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
        state: BracketState = self.manager.compute_stage_state(self.stage_config)
        logo_cache = self._build_logo_cache(state)

        r1, r2, r3 = state.rounds[0], state.rounds[1], state.rounds[2]
        qa1, qa2, qb1, qb2 = r1[0], r1[1], r1[2], r1[3]
        sf_a, sf_b = r2[0], r2[1]
        final = r3[0]

        # ── QF column ──────────────────────────────────────────────────────
        qf_col = _BracketColumn("Quarterfinals")
        qf_col.add_half_label("BRACKET A")
        qf_col.add_card(self._make_card(qa1, state, logo_cache))
        qf_col.add_card(self._make_card(qa2, state, logo_cache))
        qf_col.add_spacer(24)
        qf_col.add_half_label("BRACKET B")
        qf_col.add_card(self._make_card(qb1, state, logo_cache))
        qf_col.add_card(self._make_card(qb2, state, logo_cache))
        qf_col.add_stretch()
        self._content_layout.addWidget(qf_col)

        # ── SF column ──────────────────────────────────────────────────────
        sf_col = _BracketColumn("Semifinals")
        sf_col.add_spacer(44)   # align A semis with A quarterfinals
        sf_col.add_half_label("BRACKET A")
        sf_col.add_card(self._make_card(sf_a, state, logo_cache))
        sf_col.add_spacer(60)
        sf_col.add_half_label("BRACKET B")
        sf_col.add_card(self._make_card(sf_b, state, logo_cache))
        sf_col.add_stretch()
        self._content_layout.addWidget(sf_col)

        # ── Final column ───────────────────────────────────────────────────
        fin_col = _BracketColumn("Grand Final")
        fin_col.add_spacer(120)
        fin_col.add_card(self._make_card(final, state, logo_cache))
        fin_col.add_stretch()
        self._content_layout.addWidget(fin_col)

        self._content_layout.addStretch(1)

    def _build_logo_cache(self, state: BracketState) -> Dict[str, Optional[str]]:
        cache: Dict[str, Optional[str]] = {}
        for team_id in state.teams:
            for ext in (".svg", ".png", ".webp", ".jpg"):
                p = self.cache_dir / f"{team_id}{ext}"
                if p.exists():
                    cache[team_id] = str(p)
                    break
            else:
                cache[team_id] = None
        return cache

    def _make_card(
        self,
        match: BracketMatch,
        state: BracketState,
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
            match_type="bo3",
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
