"""Single elimination bracket engine (Legends / playoffs stage)."""

from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class BracketTeam:
    team_id: str
    name: str
    seed: int
    logo_url: Optional[str] = None
    logo_path: Optional[str] = None
    status: str = "active"  # "active" | "champion" | "eliminated"


@dataclass
class BracketMatch:
    match_id: str
    round_num: int
    bracket_half: str          # "A", "B", or "Final"
    team1_id: Optional[str] = None
    team2_id: Optional[str] = None
    match_type: str = "bo3"
    winner_id: Optional[str] = None
    score: Optional[str] = None


@dataclass
class BracketState:
    rounds: List[List[BracketMatch]]   # [quarterfinals, semifinals, [final]]
    teams: Dict[str, BracketTeam]


def _mk_id(stage_id: str, rnd: int, half: str, t1: Optional[str], t2: Optional[str]) -> str:
    a, b = sorted([str(t1 or "tbd"), str(t2 or "tbd")])
    return f"{stage_id}_r{rnd}_{half}_{a}_{b}"


def compute_bracket_state(
    stage_id: str,
    initial_teams: List[dict],
    effective_winners: Dict[str, str],
) -> BracketState:
    """
    Compute an 8-team single-elimination bracket.

    Seedings:
      Bracket A: seed 1 vs 8, seed 4 vs 5
      Bracket B: seed 2 vs 7, seed 3 vs 6
      Semis: A-QF winners play each other, B-QF winners play each other
      Final: A-SF winner vs B-SF winner

    All matches are Bo3.
    """
    teams: Dict[str, BracketTeam] = {
        t["id"]: BracketTeam(
            team_id=t["id"], name=t["name"], seed=t["seed"],
            logo_url=t.get("logo_url"),
        )
        for t in initial_teams
    }
    by_seed: Dict[int, str] = {t["seed"]: t["id"] for t in initial_teams}

    def fixed(rnd: str, half: str, s1: int, s2: int) -> BracketMatch:
        t1, t2 = by_seed.get(s1), by_seed.get(s2)
        return BracketMatch(
            match_id=_mk_id(stage_id, rnd, half, t1, t2),
            round_num=rnd, bracket_half=half,
            team1_id=t1, team2_id=t2,
        )

    def dynamic(rnd: int, half: str, t1: Optional[str], t2: Optional[str]) -> BracketMatch:
        return BracketMatch(
            match_id=_mk_id(stage_id, rnd, half, t1, t2),
            round_num=rnd, bracket_half=half,
            team1_id=t1, team2_id=t2,
        )

    # ── Round 1: Quarterfinals ───────────────────────────────────────────────
    qa1 = fixed(1, "A", 1, 8)
    qa2 = fixed(1, "A", 4, 5)
    qb1 = fixed(1, "B", 2, 7)
    qb2 = fixed(1, "B", 3, 6)
    r1 = [qa1, qa2, qb1, qb2]

    for m in r1:
        w = effective_winners.get(m.match_id)
        if w and m.team1_id and m.team2_id and w in (m.team1_id, m.team2_id):
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            teams[loser].status = "eliminated"

    # ── Round 2: Semifinals ──────────────────────────────────────────────────
    sf_a = dynamic(2, "A", qa1.winner_id, qa2.winner_id)
    sf_b = dynamic(2, "B", qb1.winner_id, qb2.winner_id)
    r2 = [sf_a, sf_b]

    for m in r2:
        w = effective_winners.get(m.match_id)
        if w and m.team1_id and m.team2_id and w in (m.team1_id, m.team2_id):
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            teams[loser].status = "eliminated"

    # ── Round 3: Grand Final ─────────────────────────────────────────────────
    gf = dynamic(3, "Final", sf_a.winner_id, sf_b.winner_id)
    w = effective_winners.get(gf.match_id)
    if w and gf.team1_id and gf.team2_id and w in (gf.team1_id, gf.team2_id):
        gf.winner_id = w
        loser = gf.team2_id if w == gf.team1_id else gf.team1_id
        teams[w].status = "champion"
        teams[loser].status = "eliminated"

    return BracketState(rounds=[r1, r2, [gf]], teams=teams)
