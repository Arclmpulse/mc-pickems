"""
Match card widgets.

TeamCard  — a single clickable team row.
MatchCard — two TeamCards stacked, emitting pick_made signals.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)

from ui.utils import set_prop, load_logo, ElidedLabel


class TeamCard(QWidget):
    """
    A single team row inside a match card.
    Clickable unless locked.
    """
    clicked = pyqtSignal()

    def __init__(
        self,
        team_id: str,
        name: str,
        seed: int,
        wins: int,
        losses: int,
        is_top: bool = True,
        logo_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.team_id = team_id
        self._locked = False
        self.setObjectName("team-card")
        self.setProperty("position", "top" if is_top else "bottom")
        self.setProperty("state", "default")
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(5)

        # Seed badge
        seed_lbl = QLabel(f"#{seed}")
        seed_lbl.setObjectName("seed-label")
        seed_lbl.setFixedWidth(26)
        layout.addWidget(seed_lbl)

        # Logo or initials
        logo_pm = load_logo(logo_path, 18)
        if logo_pm:
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pm)
            logo_lbl.setFixedSize(20, 20)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_lbl)
        else:
            init_lbl = QLabel(name[:2].upper())
            init_lbl.setObjectName("initials-label")
            init_lbl.setFixedSize(20, 20)
            init_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(init_lbl)

        # Team name
        name_lbl = ElidedLabel(name)
        name_lbl.setObjectName("team-name-label")
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name_lbl, 1)

        # W-L record (only if meaningful)
        if wins > 0 or losses > 0:
            rec_lbl = QLabel(f"{wins}-{losses}")
            rec_lbl.setObjectName("team-record-label")
            layout.addWidget(rec_lbl)

    # ── State ────────────────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """
        Valid states: "default", "picked", "correct", "wrong", "winner", "loser",
                      "advanced", "eliminated"
        """
        set_prop(self, "state", state)
        if state in ("loser", "wrong", "correct", "winner", "advanced", "eliminated"):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif not self._locked:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if locked:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Events ───────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._locked:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        if not self._locked and self.property("state") == "default":
            set_prop(self, "state", "default")  # keep styled; hover handled by QSS :hover
        super().enterEvent(event)


class MatchCard(QWidget):
    """
    Displays one match: two TeamCards stacked vertically.
    Emits pick_made(match_id, team_id) when a team is clicked.
    """
    pick_made = pyqtSignal(str, str)  # match_id, team_id

    def __init__(
        self,
        match_id: str,
        team1_id: str,
        team1_name: str,
        team1_seed: int,
        team1_wins: int,
        team1_losses: int,
        team2_id: str,
        team2_name: str,
        team2_seed: int,
        team2_wins: int,
        team2_losses: int,
        match_type: str = "bo1",
        logo1_path: Optional[str] = None,
        logo2_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.match_id = match_id
        self.team1_id = team1_id
        self.team2_id = team2_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Bo3 badge above the card
        if match_type == "bo3":
            badge_row = QWidget()
            badge_row.setFixedHeight(14)
            badge_layout = QHBoxLayout(badge_row)
            badge_layout.setContentsMargins(0, 0, 2, 0)
            badge_layout.addStretch()
            bo3_lbl = QLabel("Bo3")
            bo3_lbl.setObjectName("bo3-badge")
            badge_layout.addWidget(bo3_lbl)
            layout.addWidget(badge_row)
        else:
            spacer = QWidget()
            spacer.setFixedHeight(14)
            layout.addWidget(spacer)

        # Container for the two team cards (the matchup box)
        self.container = QWidget()
        self.container.setObjectName("matchup-box")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.card1 = TeamCard(
            team1_id, team1_name, team1_seed, team1_wins, team1_losses,
            is_top=True, logo_path=logo1_path,
        )
        self.card2 = TeamCard(
            team2_id, team2_name, team2_seed, team2_wins, team2_losses,
            is_top=False, logo_path=logo2_path,
        )

        container_layout.addWidget(self.card1)
        container_layout.addWidget(self.card2)
        layout.addWidget(self.container)

        self.card1.clicked.connect(lambda: self.pick_made.emit(match_id, team1_id))
        self.card2.clicked.connect(lambda: self.pick_made.emit(match_id, team2_id))

    def apply_pick_state(
        self,
        picked_id: Optional[str],
        actual_winner_id: Optional[str],
        is_locked: bool,
    ) -> None:
        """
        Compute and apply the visual state for both team cards and the matchup box.
        """
        for card in (self.card1, self.card2):
            tid = card.team_id
            if actual_winner_id:
                if tid == actual_winner_id:
                    card.set_state("correct" if tid == picked_id else "winner")
                else:
                    card.set_state("wrong" if tid == picked_id else "loser")
            elif picked_id:
                card.set_state("picked" if tid == picked_id else "unpicked")
            else:
                card.set_state("default")
            card.set_locked(is_locked)

        # Apply match-level outcome on container for box highlighting
        if actual_winner_id and picked_id:
            outcome = "correct" if picked_id == actual_winner_id else "wrong"
        else:
            outcome = "none"
        set_prop(self.container, "outcome", outcome)
