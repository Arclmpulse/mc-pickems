"""
Group Stage View — World Cup / football format.

Renders a scrollable grid of group cards (4 columns × 3 rows).
Each card shows a group (A-L) with 4 draggable team rows.
Top 2 rows = green (advancing), bottom 2 rows = red (eliminated).

Drag-and-drop is implemented with Qt's internal drag mechanism on a
custom list widget. Picking is stored as a full ordering of team IDs.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import QDrag, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSizePolicy, QFrame, QAbstractItemView,
    QListWidget, QListWidgetItem,
)

from data.manager import TournamentManager
from engine.group_stage import GroupState, Group, GroupTeam
from ui.utils import set_prop, find_local_logo, load_logo, ElidedLabel, COUNTRY_FLAG_EMOJI


class _TeamItem(QListWidgetItem):
    """A list item representing one team in the group drag list."""

    def __init__(self, team: GroupTeam, logo_path: Optional[str] = None):
        super().__init__()
        self.team_id = team.team_id
        self.team_name = team.name
        self.logo_path = logo_path
        self.setText(team.name)
        self.setSizeHint(QListWidgetItem().sizeHint())


class _GroupList(QListWidget):
    """
    Draggable list widget for one group's teams.
    Emits order_changed(group_id, [team_ids]) after a drag reorder.
    """
    order_changed = pyqtSignal(str, list)

    def __init__(self, group: Group, logo_cache: Dict[str, Optional[str]], parent=None):
        super().__init__(parent)
        self.group_id = group.group_id
        self._locked = group.is_locked
        self._logo_cache = logo_cache

        self.setDragDropMode(
            QAbstractItemView.DragDropMode.NoDragDrop if self._locked
            else QAbstractItemView.DragDropMode.InternalMove
        )
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(1)
        self.setObjectName("group-list")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._populate(group)
        self.setFixedHeight(self._calc_height())

        if not self._locked:
            self.model().rowsMoved.connect(self._on_rows_moved)

    def _populate(self, group: Group) -> None:
        self.clear()
        for tid in group.predicted_order:
            team = next((t for t in group.teams if t.team_id == tid), None)
            if team:
                item = _TeamItem(team, self._logo_cache.get(tid))
                self.addItem(item)

    def _calc_height(self) -> int:
        # Each row ~36px + 1px spacing × 4 rows + 2px border
        return 36 * self.count() + self.count() - 1 + 4

    def _on_rows_moved(self, *_) -> None:
        order = [self.item(i).team_id for i in range(self.count())]
        self.order_changed.emit(self.group_id, order)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

    def update_zone_colors(self) -> None:
        """Color items green (top 2) or red (bottom 2)."""
        n = self.count()
        for i in range(n):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget:
                zone = "advance" if i < 2 else "eliminate"
                set_prop(widget, "zone", zone)


class _GroupCard(QFrame):
    """One group card: header + draggable team list."""
    order_changed = pyqtSignal(str, list)  # group_id, [team_ids]

    def __init__(
        self,
        group: Group,
        logo_cache: Dict[str, Optional[str]],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("group-card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._group = group
        self._logo_cache = logo_cache

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("group-card-header")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 8, 10, 8)
        hl.setSpacing(8)

        letter_lbl = QLabel(group.name)
        letter_lbl.setObjectName("group-letter-label")
        hl.addWidget(letter_lbl)
        hl.addStretch()

        if group.is_locked:
            lock_lbl = QLabel("🔒")
            lock_lbl.setObjectName("group-lock-icon")
            hl.addWidget(lock_lbl)

        layout.addWidget(header)

        # ── Separator ───────────────────────────────────────────────────────
        sep = QFrame()
        sep.setObjectName("separator")
        layout.addWidget(sep)

        # ── Team rows ────────────────────────────────────────────────────────
        self._team_rows = _GroupTeamRows(group, logo_cache)
        self._team_rows.order_changed.connect(self.order_changed)
        layout.addWidget(self._team_rows)

    def refresh(self, group: Group, logo_cache: Dict[str, Optional[str]]) -> None:
        self._group = group
        self._team_rows.refresh(group, logo_cache)


class _GroupTeamRows(QWidget):
    """Custom drag-and-drop team row container (no QListWidget quirks)."""
    order_changed = pyqtSignal(str, list)

    def __init__(self, group: Group, logo_cache: Dict[str, Optional[str]], parent=None):
        super().__init__(parent)
        self._group = group
        self._logo_cache = logo_cache
        self._dragging_idx: Optional[int] = None
        self._drag_start_pos: Optional[QPoint] = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._rows: List[_TeamRow] = []
        self._build(group, logo_cache)

    def _build(self, group: Group, logo_cache: Dict[str, Optional[str]]) -> None:
        for i, tid in enumerate(group.predicted_order):
            team = next((t for t in group.teams if t.team_id == tid), None)
            if not team:
                continue
            actual_pos = None
            if group.actual_order and tid in group.actual_order:
                actual_pos = group.actual_order.index(tid)

            # Determine zone for this row position
            if i < 2:
                zone = "advance"
            elif i == 2:
                # 3rd place: grey until third_place_rankings is known
                if group.third_place_zone == "advancing":
                    zone = "third_advancing"
                elif group.third_place_zone == "eliminated":
                    zone = "third_eliminated"
                else:
                    zone = "third"
            else:
                zone = "eliminate"

            row = _TeamRow(
                team=team,
                position=i,
                zone=zone,
                logo_path=logo_cache.get(tid),
                locked=group.is_locked,
                actual_zone=("advance" if actual_pos is not None and actual_pos < 2
                             else "eliminate" if actual_pos is not None else None),
                predicted_correct=(actual_pos is not None and actual_pos == i),
            )
            if not group.is_locked:
                row.drag_started.connect(lambda idx=i: self._begin_drag(idx))
            self._layout.addWidget(row)
            self._rows.append(row)

    def refresh(self, group: Group, logo_cache: Dict[str, Optional[str]]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()
        self._group = group
        self._logo_cache = logo_cache
        self._build(group, logo_cache)

    def _begin_drag(self, idx: int) -> None:
        self._dragging_idx = idx

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_idx is None or self._group.is_locked:
            return
        # Find which row we're over
        target_idx = self._row_at_y(event.pos().y())
        if target_idx is not None and target_idx != self._dragging_idx:
            self._swap_rows(self._dragging_idx, target_idx)
            self._dragging_idx = target_idx
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging_idx is not None:
            order = [r.team_id for r in self._rows]
            self.order_changed.emit(self._group.group_id, order)
            self._dragging_idx = None
        super().mouseReleaseEvent(event)

    def _row_at_y(self, y: int) -> Optional[int]:
        for i, row in enumerate(self._rows):
            if row.y() <= y < row.y() + row.height():
                return i
        return None

    def _swap_rows(self, i: int, j: int) -> None:
        if i == j:
            return
        # Swap in layout
        item_i = self._layout.takeAt(i)
        item_j = self._layout.takeAt(j - (1 if i < j else 0))
        self._layout.insertWidget(i, item_j.widget())
        self._layout.insertWidget(j, item_i.widget())
        # Swap in list
        self._rows[i], self._rows[j] = self._rows[j], self._rows[i]
        # Update zones
        for k, row in enumerate(self._rows):
            if k < 2:
                new_zone = "advance"
            elif k == 2:
                if self._group.third_place_zone == "advancing":
                    new_zone = "third_advancing"
                elif self._group.third_place_zone == "eliminated":
                    new_zone = "third_eliminated"
                else:
                    new_zone = "third"
            else:
                new_zone = "eliminate"
            row.set_zone(new_zone)


class _TeamRow(QWidget):
    """A single draggable team row within a group card."""
    drag_started = pyqtSignal()

    def __init__(
        self,
        team: GroupTeam,
        position: int,
        zone: str,
        logo_path: Optional[str],
        locked: bool,
        actual_zone: Optional[str] = None,
        predicted_correct: Optional[bool] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.team_id = team.team_id
        self._locked = locked
        self._zone = zone
        self.setObjectName("group-team-row")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        if not locked:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        # Position badge
        pos_lbl = QLabel(str(position + 1))
        pos_lbl.setObjectName("group-position-label")
        pos_lbl.setFixedWidth(18)
        pos_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(pos_lbl)

        # Flag/logo — prefer cached image, fall back to emoji flag, then initials
        logo_pm = load_logo(logo_path, 20)
        if logo_pm:
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pm)
            logo_lbl.setFixedSize(22, 22)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_lbl)
        else:
            flag = COUNTRY_FLAG_EMOJI.get(team.team_id, team.name[:2].upper())
            flag_lbl = QLabel(flag)
            flag_lbl.setObjectName("flag-emoji-label")
            flag_lbl.setFixedSize(22, 22)
            flag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(flag_lbl)

        # Team name
        name_lbl = ElidedLabel(team.name)
        name_lbl.setObjectName("group-team-name")
        layout.addWidget(name_lbl, 1)

        # Correctness indicator (if result is known)
        if actual_zone is not None and predicted_correct is not None:
            if predicted_correct:
                result_lbl = QLabel("✓")
                result_lbl.setStyleSheet("color: #3fb950; font-weight: 700; background: transparent;")
            else:
                result_lbl = QLabel("✗")
                result_lbl.setStyleSheet("color: #f85149; font-weight: 700; background: transparent;")
            layout.addWidget(result_lbl)

        # Drag handle (when not locked)
        if not locked:
            handle_lbl = QLabel("⠿")
            handle_lbl.setObjectName("group-drag-handle")
            layout.addWidget(handle_lbl)

        self._apply_zone(zone)

    def set_zone(self, zone: str) -> None:
        self._zone = zone
        self._apply_zone(zone)

    def _apply_zone(self, zone: str) -> None:
        set_prop(self, "zone", zone)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._locked:
            self.drag_started.emit()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if not self._locked:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class GroupStageView(QScrollArea):
    """
    Scrollable view showing all 12 group cards in a 4-column grid.
    Teams can be dragged within each group to predict finish order.
    """
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
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content_layout = QGridLayout(self._content)
        self._content_layout.setContentsMargins(20, 20, 20, 20)
        self._content_layout.setSpacing(16)
        self.setWidget(self._content)

        self._group_cards: Dict[str, _GroupCard] = {}
        self._build()

    def refresh(self) -> None:
        v = self.verticalScrollBar().value()
        self._clear()
        self._build()
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(v))
        self.state_changed.emit()

    def _clear(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._group_cards.clear()

    def _build(self) -> None:
        state: GroupState = self.manager.compute_stage_state(self.stage_config)
        if not state:
            return

        # Build logo cache
        logo_cache: Dict[str, Optional[str]] = {}
        for group in state.groups:
            for team in group.teams:
                logo_cache[team.team_id] = (
                    team.logo_path or find_local_logo(self.cache_dir, team.team_id)
                )

        cols = 4
        for idx, group in enumerate(state.groups):
            row = idx // cols
            col = idx % cols
            card = _GroupCard(group, logo_cache)
            card.order_changed.connect(self._on_order_changed)
            self._content_layout.addWidget(card, row, col)
            self._group_cards[group.group_id] = card

    def _on_order_changed(self, group_id: str, team_ids: List[str]) -> None:
        """Save pick and propagate state change."""
        match_id = f"{self.stage_id}_{group_id}_order"
        # Store as JSON-encoded list in the pick value field
        self.manager.make_group_pick(match_id, team_ids)
