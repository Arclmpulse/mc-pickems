"""
Swiss bracket view.

Renders a horizontal scrollable layout with one column per round
plus a "Final Result" column on the right.
Refreshes automatically when the TournamentManager emits state_changed.
"""

from pathlib import Path
from typing import Optional, Dict, List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QHBoxLayout, QVBoxLayout,
    QLabel, QSizePolicy, QFrame,
)

from data.manager import TournamentManager
from engine.swiss import SwissState, MatchInfo, TeamRecord, get_final_standings
from ui.match_card import MatchCard
from ui.utils import set_prop, ElidedLabel, find_local_logo, load_logo


# W-L records for teams that have advanced (3 wins) or eliminated (3 losses)
_ADVANCED_GROUPS = {"3-0", "3-1", "3-2"}
_ELIMINATED_GROUPS = {"0-3", "1-3", "2-3"}


class RoundColumn(QWidget):
    """One vertical column representing a single Swiss round."""

    def __init__(self, round_num: int, parent=None):
        super().__init__(parent)
        self.setObjectName("round-column")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._build_header(round_num)

    def _build_header(self, round_num: int) -> None:
        header = QWidget()
        header.setObjectName("round-header")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(10, 7, 10, 7)
        h_layout.setSpacing(1)

        title = QLabel(f"Round {round_num}")
        title.setObjectName("round-title")
        h_layout.addWidget(title)

        self._subtitle = QLabel("")
        self._subtitle.setObjectName("round-subtitle")
        h_layout.addWidget(self._subtitle)

        self._layout.addWidget(header)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)

    def add_group_label(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("wl-group-label")
        self._layout.addWidget(lbl)

    def add_match_card(self, card: MatchCard) -> None:
        self._layout.addWidget(card)

    def add_placeholder(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("wl-group-label")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #30363d; font-size: 11px; padding: 16px 8px;")
        self._layout.addWidget(lbl)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)


class FinalResultColumn(QWidget):
    """Rightmost column grouping advanced/eliminated teams by final W-L."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("final-column")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._build_header()

    def _build_header(self) -> None:
        hdr = QLabel("Final Result")
        hdr.setObjectName("final-header")
        self._layout.addWidget(hdr)

    def populate(self, standings: Dict[str, List[TeamRecord]], cache_dir: Path) -> None:
        # Clear existing (except header)
        while self._layout.count() > 1:
            item = self._layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        order = ["3-0", "3-1", "3-2", "0-3", "1-3", "2-3"]
        shown = set()
        for key in order:
            if key not in standings:
                continue
            shown.add(key)
            is_adv = key in _ADVANCED_GROUPS
            group_lbl = QLabel(f"  {key}")
            group_lbl.setObjectName("final-group-label")
            group_lbl.setProperty("group", "advanced" if is_adv else "eliminated")
            set_prop(group_lbl, "group", "advanced" if is_adv else "eliminated")
            self._layout.addWidget(group_lbl)

            for team in standings[key]:
                row = self._make_team_row(team, cache_dir)
                self._layout.addWidget(row)

        # Any remaining groups not in the order
        for key, teams in standings.items():
            if key in shown:
                continue
            is_adv = key in _ADVANCED_GROUPS
            group_lbl = QLabel(f"  {key}")
            group_lbl.setObjectName("final-group-label")
            set_prop(group_lbl, "group", "advanced" if is_adv else "eliminated")
            self._layout.addWidget(group_lbl)
            for team in teams:
                self._layout.addWidget(self._make_team_row(team, cache_dir))

        self._layout.addStretch(1)

    def _make_team_row(self, team: TeamRecord, cache_dir: Path) -> QWidget:
        row = QWidget()
        row.setObjectName("final-team-row")
        row.setFixedHeight(28)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 0, 8, 0)
        rl.setSpacing(5)

        seed_lbl = QLabel(f"#{team.initial_seed}")
        seed_lbl.setObjectName("final-seed")
        seed_lbl.setFixedWidth(26)
        rl.addWidget(seed_lbl)

        # Team logo or initials
        logo_path = team.logo_path or find_local_logo(cache_dir, team.team_id)
        logo_pm = load_logo(logo_path, 18)
        if logo_pm:
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pm)
            logo_lbl.setFixedSize(20, 20)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(logo_lbl)
        else:
            init_lbl = QLabel(team.name[:2].upper())
            init_lbl.setObjectName("initials-label")
            init_lbl.setFixedSize(20, 20)
            init_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(init_lbl)

        name_lbl = ElidedLabel(team.name)
        name_lbl.setObjectName("final-name")
        rl.addWidget(name_lbl, 1)
        return row


class SwissView(QScrollArea):
    """
    Horizontally scrollable Swiss bracket view.
    Reacts to TournamentManager.state_changed to refresh.
    """
    state_changed = pyqtSignal()  # propagate upward for accuracy counter

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
        self._content.setObjectName("swiss-scroll-content")
        self._content_layout = QHBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 16, 16, 16)
        self._content_layout.setSpacing(12)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._content)

        self._build()

    # ── Build / refresh ──────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Rebuild the view, preserving scroll position."""
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
        state: SwissState = self.manager.compute_stage_state(self.stage_config)

        # Build logo path cache
        logo_cache: Dict[str, Optional[str]] = {}
        for team_id, tr in state.teams.items():
            lp = tr.logo_path or self._find_logo(team_id)
            logo_cache[team_id] = lp

        self._build_round_columns(state, logo_cache)
        self._build_final_column(state)

    def _find_logo(self, team_id: str) -> Optional[str]:
        return find_local_logo(self.cache_dir, team_id)

    def _build_round_columns(self, state: SwissState, logo_cache: Dict[str, Optional[str]]) -> None:
        num_generated = state.num_rounds

        for rnd_idx in range(5):   # always show 5 round columns
            round_num = rnd_idx + 1
            col = RoundColumn(round_num)

            if rnd_idx < num_generated:
                matches = state.rounds[rnd_idx]
                self._populate_round_column(col, matches, state, logo_cache, round_num)
            else:
                needed = round_num - 1
                msg = (
                    f"Complete Round {needed} picks\nto see matchups"
                    if needed > 0
                    else "Make picks to continue"
                )
                col.set_subtitle("pending")
                col.add_placeholder(msg)

            col.add_stretch()
            self._content_layout.addWidget(col, 1)

    def _populate_round_column(
        self,
        col: RoundColumn,
        matches: List[MatchInfo],
        state: SwissState,
        logo_cache: Dict[str, Optional[str]],
        round_num: int,
    ) -> None:
        # Determine subtitle from first match
        types = sorted({m.match_type for m in matches}, reverse=True)  # bo3 first
        type_str = "Bo3" if "bo3" in types else "Bo1"
        # Sort groups: better W-L record on top (wins desc, losses asc)
        def _wl_key(wl: str) -> tuple:
            w, l = wl.split("-")
            return (-int(w), int(l))
        groups = sorted({m.wl_group for m in matches}, key=_wl_key)
        group_str = " / ".join(groups) if groups else ""

        # Check if round has results to show lock symbol
        round_results = self.manager._results.get(self.stage_config["id"], {}).get(f"round_{round_num}", [])
        lock_str = "  🔒" if round_results else ""
        col.set_subtitle(f"{group_str}  ·  {type_str}{lock_str}")

        # Group matches by W-L
        by_wl: Dict[str, List[MatchInfo]] = {}
        for m in matches:
            by_wl.setdefault(m.wl_group, []).append(m)

        col.add_stretch()  # Push content down from header
        first_group = True
        for wl in sorted(by_wl.keys(), key=_wl_key):
            if not first_group:
                col.add_stretch()  # Add space between different W-L groups
            first_group = False

            grp_matches = by_wl[wl]
            mt = grp_matches[0].match_type
            col.add_group_label(f"{wl}  ·  {'Bo3' if mt == 'bo3' else 'Bo1'}")

            for match in grp_matches:
                t1 = state.teams[match.team1_id]
                t2 = state.teams[match.team2_id]

                card = MatchCard(
                    match_id=match.match_id,
                    team1_id=match.team1_id,
                    team1_name=t1.name,
                    team1_seed=t1.initial_seed,
                    team1_wins=t1.wins,
                    team1_losses=t1.losses,
                    team2_id=match.team2_id,
                    team2_name=t2.name,
                    team2_seed=t2.initial_seed,
                    team2_wins=t2.wins,
                    team2_losses=t2.losses,
                    match_type=match.match_type,
                    logo1_path=logo_cache.get(match.team1_id),
                    logo2_path=logo_cache.get(match.team2_id),
                )

                # Determine state
                picked = self.manager.get_pick(match.match_id)
                actual = self.manager.find_result_winner(
                    self.stage_id, match.round_num, match.team1_id, match.team2_id, match.match_id
                )
                locked = self.manager.is_locked(match.match_id)
                card.apply_pick_state(picked, actual, locked)

                card.pick_made.connect(self._on_pick_made)
                col.add_match_card(card)

    def _build_final_column(self, state: SwissState) -> None:
        standings = get_final_standings(state)
        if not standings:
            return
        col = FinalResultColumn()
        col.populate(standings, self.cache_dir)
        self._content_layout.addWidget(col, 1)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _on_pick_made(self, match_id: str, team_id: str) -> None:
        self.manager.make_pick(match_id, team_id)
        # manager.state_changed is connected to the MainWindow which calls refresh
