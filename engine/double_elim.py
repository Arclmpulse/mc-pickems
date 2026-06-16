"""
Double elimination bracket engine.
Supports both 4-team (GSL group/play-in) and 8-team double elimination formats.
Matches are resolved topologically down the bracket.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class DoubleElimTeam:
    team_id: str
    name: str
    seed: int
    logo_url: Optional[str] = None
    logo_path: Optional[str] = None
    status: str = "active"  # "active" | "champion" | "eliminated"


@dataclass
class DoubleElimMatch:
    match_id: str
    round_num: int
    bracket_half: str          # "Upper", "Lower", or "Final"
    team1_id: Optional[str] = None
    team2_id: Optional[str] = None
    match_type: str = "bo3"
    winner_id: Optional[str] = None
    score: Optional[str] = None


@dataclass
class DoubleElimState:
    rounds: List[List[DoubleElimMatch]]   # [column1_matches, column2_matches, ...]
    teams: Dict[str, DoubleElimTeam]


def compute_double_elim_state(
    stage_id: str,
    initial_teams: List[dict],
    effective_winners: Dict[str, str],
    stage_config: dict,
) -> DoubleElimState:
    """
    Topologically computes the state of a double elimination bracket.
    Supports 4-team GSL play-in or 8-team Main Event.
    """
    teams: Dict[str, DoubleElimTeam] = {
        t["id"]: DoubleElimTeam(
            team_id=t["id"], name=t["name"], seed=t["seed"],
            logo_url=t.get("logo_url"),
        )
        for t in initial_teams
    }

    by_seed: Dict[int, str] = {t["seed"]: t["id"] for t in initial_teams}
    default_mt = stage_config.get("match_type", "bo3")
    matches: Dict[str, DoubleElimMatch] = {}

    def get_winner(mid: str) -> Optional[str]:
        m = matches.get(mid)
        if m and m.team1_id and m.team2_id:
            w = effective_winners.get(mid)
            if w in (m.team1_id, m.team2_id):
                return w
        return None

    def get_loser(mid: str) -> Optional[str]:
        m = matches.get(mid)
        if m and m.team1_id and m.team2_id:
            w = get_winner(mid)
            if w:
                return m.team2_id if w == m.team1_id else m.team1_id
        return None

    if len(initial_teams) == 4:
        # ── 4-Team Double Elim (GSL Group) ──────────────────────────────────
        m1_id = f"{stage_id}_m1"
        m2_id = f"{stage_id}_m2"
        m3_id = f"{stage_id}_m3"
        m4_id = f"{stage_id}_m4"
        m5_id = f"{stage_id}_m5"
        m6_id = f"{stage_id}_m6"

        # Round 1: Upper Semis (Opening Matches)
        matches[m1_id] = DoubleElimMatch(m1_id, 1, "Upper", by_seed.get(1), by_seed.get(4), default_mt)
        matches[m2_id] = DoubleElimMatch(m2_id, 1, "Upper", by_seed.get(2), by_seed.get(3), default_mt)

        # Round 2: Upper Final (Winners Match) & Lower Semis (Elimination Match)
        matches[m3_id] = DoubleElimMatch(m3_id, 2, "Upper", get_winner(m1_id), get_winner(m2_id), default_mt)
        matches[m4_id] = DoubleElimMatch(m4_id, 2, "Lower", get_loser(m1_id), get_loser(m2_id), default_mt)

        # Round 3: Lower Final (Decider Match)
        matches[m5_id] = DoubleElimMatch(m5_id, 3, "Lower", get_loser(m3_id), get_winner(m4_id), default_mt)

        # Round 4: Grand Final (Play-in Champion decider)
        matches[m6_id] = DoubleElimMatch(m6_id, 4, "Final", get_winner(m3_id), get_winner(m5_id), default_mt)

        rounds = [
            [matches[m1_id], matches[m2_id]],
            [matches[m3_id], matches[m4_id]],
            [matches[m5_id]],
            [matches[m6_id]]
        ]

    else:
        # ── 8-Team Double Elim (Main Event) ──────────────────────────────────
        m1_id = f"{stage_id}_m1"
        m2_id = f"{stage_id}_m2"
        m3_id = f"{stage_id}_m3"
        m4_id = f"{stage_id}_m4"
        m5_id = f"{stage_id}_m5"
        m6_id = f"{stage_id}_m6"
        m7_id = f"{stage_id}_m7"
        m8_id = f"{stage_id}_m8"
        m9_id = f"{stage_id}_m9"
        m10_id = f"{stage_id}_m10"
        m11_id = f"{stage_id}_m11"
        m12_id = f"{stage_id}_m12"
        m13_id = f"{stage_id}_m13"
        m14_id = f"{stage_id}_m14"

        # Upper Round 1
        matches[m1_id] = DoubleElimMatch(m1_id, 1, "Upper", by_seed.get(1), by_seed.get(8), default_mt)
        matches[m2_id] = DoubleElimMatch(m2_id, 1, "Upper", by_seed.get(4), by_seed.get(5), default_mt)
        matches[m3_id] = DoubleElimMatch(m3_id, 1, "Upper", by_seed.get(2), by_seed.get(7), default_mt)
        matches[m4_id] = DoubleElimMatch(m4_id, 1, "Upper", by_seed.get(3), by_seed.get(6), default_mt)

        # Lower Round 1 (Matches between Upper R1 losers)
        matches[m8_id] = DoubleElimMatch(m8_id, 1, "Lower", get_loser(m1_id), get_loser(m2_id), default_mt)
        matches[m9_id] = DoubleElimMatch(m9_id, 1, "Lower", get_loser(m3_id), get_loser(m4_id), default_mt)

        # Upper Round 2 (Upper Semis)
        matches[m5_id] = DoubleElimMatch(m5_id, 2, "Upper", get_winner(m1_id), get_winner(m2_id), default_mt)
        matches[m6_id] = DoubleElimMatch(m6_id, 2, "Upper", get_winner(m3_id), get_winner(m4_id), default_mt)

        # Lower Round 2 (Upper Semis losers vs Lower R1 winners)
        matches[m10_id] = DoubleElimMatch(m10_id, 2, "Lower", get_loser(m6_id), get_winner(m8_id), default_mt)
        matches[m11_id] = DoubleElimMatch(m11_id, 2, "Lower", get_loser(m5_id), get_winner(m9_id), default_mt)

        # Upper Round 3 (Upper Final)
        matches[m7_id] = DoubleElimMatch(m7_id, 3, "Upper", get_winner(m5_id), get_winner(m6_id), default_mt)

        # Lower Round 3 (Lower Semis)
        matches[m12_id] = DoubleElimMatch(m12_id, 3, "Lower", get_winner(m10_id), get_winner(m11_id), default_mt)

        # Lower Round 4 (Lower Final)
        matches[m13_id] = DoubleElimMatch(m13_id, 4, "Lower", get_loser(m7_id), get_winner(m12_id), default_mt)

        # Grand Final
        matches[m14_id] = DoubleElimMatch(m14_id, 5, "Final", get_winner(m7_id), get_winner(m13_id), default_mt)

        rounds = [
            [matches[m1_id], matches[m2_id], matches[m3_id], matches[m4_id]],
            [matches[m5_id], matches[m6_id], matches[m8_id], matches[m9_id]],
            [matches[m7_id], matches[m10_id], matches[m11_id]],
            [matches[m12_id]],
            [matches[m13_id]],
            [matches[m14_id]]
        ]

    # Resolve actual winners and mark team statuses
    for mid, m in matches.items():
        w = get_winner(mid)
        if w:
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            # In double-elim, teams are only eliminated if they lose in Lower or Grand Final
            if m.bracket_half in ("Lower", "Final"):
                if loser in teams:
                    teams[loser].status = "eliminated"

    # Set champion
    final_mid = f"{stage_id}_m6" if len(initial_teams) == 4 else f"{stage_id}_m14"
    final_winner = get_winner(final_mid)
    if final_winner and final_winner in teams:
        teams[final_winner].status = "champion"

    return DoubleElimState(rounds=rounds, teams=teams)
