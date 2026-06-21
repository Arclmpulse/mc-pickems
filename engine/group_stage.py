"""
Group stage engine — World Cup / football format.

Each group has 4 teams. The user predicts the finishing order via
drag-and-drop (no individual match picking). The top 2 advance, bottom 2 are
eliminated.

Accuracy scoring (hybrid):
  Per group (max 1.0 pts):
    - 0.125 pts for each team in the correct exact position (0–4 × 0.125 = 0–0.5)
    - 0.25 pts for each team correctly placed in the top-2 or bottom-2 half (0–2 × 0.25 = 0–0.5)
  Total: max 1.0 per group, max 12.0 across all groups.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple


@dataclass
class GroupTeam:
    """A team within a group stage."""
    team_id: str
    name: str
    seed: int  # original seed within the group (1-4)
    logo_url: Optional[str] = None
    logo_path: Optional[str] = None


@dataclass
class Group:
    """State of one group."""
    group_id: str       # e.g. "group_a"
    name: str           # e.g. "Group A"
    teams: List[GroupTeam]           # original order (seed 1→4)
    predicted_order: List[str]       # user's predicted finishing order (team_ids, top→bottom)
    actual_order: Optional[List[str]] = None   # from results.json when known
    is_locked: bool = False          # True when actual result is filled in
    # "advancing" | "eliminated" | "unknown" — fate of the 3rd-place team in this group
    third_place_zone: str = "unknown"


@dataclass
class GroupState:
    """Complete computed state of the group stage."""
    groups: List[Group]
    third_place_rankings_known: bool = False  # True once rankings list is populated


def compute_group_state(
    stage_id: str,
    groups_config: List[dict],   # list of {id, name, teams: [{id, name, seed, logo_url?}]}
    predicted_orders: Dict[str, List[str]],   # group_id → ordered list of team_ids
    actual_orders: Dict[str, List[str]],      # group_id → ordered list from results.json (or [])
    third_place_rankings: Optional[List[str]] = None,  # group_ids ranked best→worst 3rd place
) -> GroupState:
    """
    Compute the full group stage state.

    Args:
        stage_id:               e.g. "groups"
        groups_config:          list of group definitions from tournament.json
        predicted_orders:       user's predicted finish orders (saved in picks)
        actual_orders:          real finish orders from results.json
        third_place_rankings:   ordered list of group_ids by 3rd-place performance
                                (top 8 of 12 advance; if None or empty, all 3rds are "unknown")

    Returns:
        GroupState with all groups populated.
    """
    # Determine which 3rd-place groups are advancing/eliminated
    _third_advancing: set = set()
    _third_eliminated: set = set()
    rankings_known = bool(third_place_rankings)
    if rankings_known:
        _third_advancing = set(third_place_rankings[:8])
        _third_eliminated = set(third_place_rankings[8:])

    groups: List[Group] = []

    for gconf in groups_config:
        gid = gconf["id"]
        teams = [
            GroupTeam(
                team_id=t["id"],
                name=t["name"],
                seed=t["seed"],
                logo_url=t.get("logo_url"),
            )
            for t in gconf["teams"]
        ]
        # Default prediction: original seed order
        default_order = [t.team_id for t in sorted(teams, key=lambda t: t.seed)]
        pred = predicted_orders.get(gid, default_order)
        # Validate predicted order — if any team is missing, fall back to default
        team_ids = {t.team_id for t in teams}
        if not all(tid in team_ids for tid in pred) or len(pred) != len(teams):
            pred = default_order

        actual = actual_orders.get(gid) or None
        locked = bool(actual)

        # Determine 3rd-place zone for this group
        if rankings_known:
            if gid in _third_advancing:
                third_zone = "advancing"
            elif gid in _third_eliminated:
                third_zone = "eliminated"
            else:
                third_zone = "unknown"  # rankings given but this group not listed yet
        else:
            third_zone = "unknown"

        groups.append(Group(
            group_id=gid,
            name=gconf["name"],
            teams=teams,
            predicted_order=pred,
            actual_order=actual,
            is_locked=locked,
            third_place_zone=third_zone,
        ))

    return GroupState(groups=groups, third_place_rankings_known=rankings_known)


def score_group_picks(group: Group) -> Tuple[float, float]:
    """
    Score a single group's picks against the actual result.

    Returns:
        (earned, max_possible) — max_possible is always 1.0 if actual is known, else 0.0
    """
    if not group.actual_order or not group.predicted_order:
        return 0.0, 0.0

    actual = group.actual_order
    predicted = group.predicted_order
    n = len(actual)
    if n == 0:
        return 0.0, 0.0

    # Exact position: 0.125 per correct position
    exact = sum(0.125 for i in range(n) if i < len(predicted) and predicted[i] == actual[i])

    # Correct half (top-2 vs bottom-2): 0.25 per team in correct half
    half = n // 2
    actual_top = set(actual[:half])
    predicted_top = set(predicted[:half]) if len(predicted) >= half else set()
    correct_half = sum(0.25 for tid in actual_top if tid in predicted_top)

    return exact + correct_half, 1.0


def get_advancing_teams(group: Group) -> List[str]:
    """Return the top-2 team IDs from a group (actual if known, predicted otherwise)."""
    order = group.actual_order if group.actual_order else group.predicted_order
    return order[:2] if order else []


def get_all_third_place_teams(groups: List[Group]) -> List[str]:
    """Return the 3rd-place finisher from each group (actual if known, predicted otherwise)."""
    result = []
    for g in groups:
        order = g.actual_order if g.actual_order else g.predicted_order
        if len(order) >= 3:
            result.append(order[2])
    return result
