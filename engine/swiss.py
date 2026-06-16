"""
Swiss bracket engine — CS Major rules.

Rules implemented:
  - 16 teams, up to 5 rounds
  - 3 wins → advance, 3 losses → eliminate
  - Round 1: seed 1v9, 2v10, …, 8v16
  - Rounds 2-3: greedy highest-vs-lowest within W-L group, no rematch
  - Rounds 4-5: 15-row priority table for groups of exactly 6, no rematch
  - Match type: Bo3 if either team is at 2W or 2L, otherwise Bo1
  - Seeding: W-L differential desc → Buchholz desc → initial seed asc
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

# 15-row priority table for 6-team groups (rounds 4-5).
# Numbers are 1-indexed positions in the seed-ranked group (1 = best seed).
PRIORITY_TABLE: List[List[Tuple[int, int]]] = [
    [(1, 6), (2, 5), (3, 4)],
    [(1, 6), (2, 4), (3, 5)],
    [(1, 5), (2, 6), (3, 4)],
    [(1, 5), (2, 4), (3, 6)],
    [(1, 4), (2, 6), (3, 5)],
    [(1, 4), (2, 5), (3, 6)],
    [(1, 6), (2, 3), (4, 5)],
    [(1, 5), (2, 3), (4, 6)],
    [(1, 3), (2, 6), (4, 5)],
    [(1, 3), (2, 5), (4, 6)],
    [(1, 4), (2, 3), (5, 6)],
    [(1, 3), (2, 4), (5, 6)],
    [(1, 2), (3, 6), (4, 5)],
    [(1, 2), (3, 5), (4, 6)],
    [(1, 2), (3, 4), (5, 6)],
]


@dataclass
class TeamRecord:
    """State of a team within a Swiss stage."""
    team_id: str
    name: str
    initial_seed: int
    wins: int = 0
    losses: int = 0
    buchholz: int = 0
    opponents_faced: List[str] = field(default_factory=list)
    status: str = "active"  # "active" | "advanced" | "eliminated"
    logo_url: Optional[str] = None
    logo_path: Optional[str] = None  # cached local path


@dataclass
class MatchInfo:
    """A single Swiss match."""
    match_id: str
    round_num: int
    team1_id: str   # higher seed (lower seed number)
    team2_id: str   # lower seed
    match_type: str  # "bo1" | "bo3"
    wl_group: str    # W-L of both teams before this match, e.g. "1-1"
    winner_id: Optional[str] = None
    score: Optional[str] = None  # optional display string e.g. "2-0"


@dataclass
class SwissState:
    """Complete computed state of a Swiss stage."""
    rounds: List[List[MatchInfo]]
    teams: Dict[str, TeamRecord]
    num_rounds: int


# ── Seeding helpers ──────────────────────────────────────────────────────────

def _seed_key(t: TeamRecord) -> tuple:
    """Lower tuple = better seed rank."""
    return (-(t.wins - t.losses), -t.buchholz, t.initial_seed)


def _sort_group(ids: List[str], teams: Dict[str, TeamRecord]) -> List[str]:
    return sorted(ids, key=lambda tid: _seed_key(teams[tid]))


def _recompute_buchholz(teams: Dict[str, TeamRecord]) -> None:
    """Recalculate Buchholz scores for all teams."""
    for team in teams.values():
        team.buchholz = sum(
            teams[o].wins - teams[o].losses
            for o in team.opponents_faced
            if o in teams
        )


# ── Pairing helpers ──────────────────────────────────────────────────────────

def _has_played(teams: Dict[str, TeamRecord], a: str, b: str) -> bool:
    return b in teams[a].opponents_faced


def _match_type(t1: TeamRecord, t2: TeamRecord) -> str:
    """Bo3 if either team is at 2 wins or 2 losses (advancement/elimination)."""
    if t1.wins == 2 or t1.losses == 2 or t2.wins == 2 or t2.losses == 2:
        return "bo3"
    return "bo1"


def _greedy_pairs(group: List[str], teams: Dict[str, TeamRecord]) -> List[Tuple[str, str]]:
    """
    Greedy: pair highest seed vs lowest available without rematch.
    Used for rounds 2-3.
    """
    avail = list(group)
    pairs: List[Tuple[str, str]] = []
    while len(avail) >= 2:
        best = avail.pop(0)
        # Try from the lowest seed upward to avoid rematch
        for i in range(len(avail) - 1, -1, -1):
            if not _has_played(teams, best, avail[i]):
                pairs.append((best, avail.pop(i)))
                break
        else:
            # Unavoidable rematch — pair with worst seed remaining
            pairs.append((best, avail.pop(-1)))
    return pairs


def _priority_pairs(group: List[str], teams: Dict[str, TeamRecord]) -> List[Tuple[str, str]]:
    """
    Priority-table matching for exactly 6 teams.
    Used for rounds 4-5.
    """
    assert len(group) == 6
    for row in PRIORITY_TABLE:
        pairs = [(group[p1 - 1], group[p2 - 1]) for p1, p2 in row]
        if all(not _has_played(teams, a, b) for a, b in pairs):
            return pairs
    # All rows caused rematches — fall back to priority 1
    return [(group[p1 - 1], group[p2 - 1]) for p1, p2 in PRIORITY_TABLE[0]]


def _make_match_id(stage_id: str, rnd: int, a: str, b: str) -> str:
    """Stable match ID (team IDs sorted alphabetically)."""
    x, y = sorted([a, b])
    return f"{stage_id}_r{rnd}_{x}_{y}"


# ── Main engine ──────────────────────────────────────────────────────────────

def compute_swiss_state(
    stage_id: str,
    initial_teams: List[dict],
    effective_winners: Dict[str, str],
) -> SwissState:
    """
    Compute the complete Swiss bracket state from scratch.

    Args:
        stage_id:          e.g. "stage1"
        initial_teams:     list of {id, name, seed, logo_url?}
        effective_winners: match_id → winner_team_id
                           (caller merges results + picks; results take priority)

    Stops generating rounds when a round has at least one unresolved match.
    """
    teams: Dict[str, TeamRecord] = {
        t["id"]: TeamRecord(
            team_id=t["id"],
            name=t["name"],
            initial_seed=t["seed"],
            logo_url=t.get("logo_url"),
        )
        for t in initial_teams
    }

    all_rounds: List[List[MatchInfo]] = []

    for rnd in range(1, 6):
        active = [tid for tid, t in teams.items() if t.status == "active"]
        if not active:
            break

        matches: List[MatchInfo] = []

        if rnd == 1:
            # Fixed initial matchups: top half vs bottom half
            sorted_all = _sort_group(active, teams)
            half = len(sorted_all) // 2
            for i in range(half):
                a, b = sorted_all[i], sorted_all[i + half]
                matches.append(MatchInfo(
                    match_id=_make_match_id(stage_id, 1, a, b),
                    round_num=1, team1_id=a, team2_id=b,
                    match_type="bo1", wl_group="0-0",
                ))
        else:
            # Group active teams by W-L record
            groups: Dict[str, List[str]] = {}
            for tid in active:
                t = teams[tid]
                key = f"{t.wins}-{t.losses}"
                groups.setdefault(key, []).append(tid)

            for wl in sorted(groups):
                grp = _sort_group(groups[wl], teams)
                # Priority table for 6-team groups in rounds 4-5
                if rnd >= 4 and len(grp) == 6:
                    pairs = _priority_pairs(grp, teams)
                else:
                    pairs = _greedy_pairs(grp, teams)

                for a, b in pairs:
                    mt = _match_type(teams[a], teams[b])
                    matches.append(MatchInfo(
                        match_id=_make_match_id(stage_id, rnd, a, b),
                        round_num=rnd, team1_id=a, team2_id=b,
                        match_type=mt, wl_group=wl,
                    ))

        all_rounds.append(matches)

        # Apply winners and check if the round is fully resolved
        fully_resolved = True
        for m in matches:
            w = effective_winners.get(m.match_id)
            if w and w in (m.team1_id, m.team2_id):
                m.winner_id = w
                loser = m.team2_id if w == m.team1_id else m.team1_id
                teams[w].wins += 1
                teams[loser].losses += 1
                teams[w].opponents_faced.append(loser)
                teams[loser].opponents_faced.append(w)
                if teams[w].wins == 3:
                    teams[w].status = "advanced"
                if teams[loser].losses == 3:
                    teams[loser].status = "eliminated"
            else:
                fully_resolved = False

        _recompute_buchholz(teams)

        # Don't generate next round until this one is fully resolved
        if not fully_resolved:
            break

    return SwissState(rounds=all_rounds, teams=teams, num_rounds=len(all_rounds))


def get_final_standings(state: SwissState) -> Dict[str, List[TeamRecord]]:
    """
    Group finished teams by final W-L record for the 'Final Result' column.
    Returns a dict like {"3-0": [...], "3-1": [...], ...} sorted by seed.
    """
    groups: Dict[str, List[TeamRecord]] = {}
    for t in state.teams.values():
        if t.status != "active":
            key = f"{t.wins}-{t.losses}"
            groups.setdefault(key, []).append(t)
    for key in groups:
        groups[key].sort(key=_seed_key)
    return groups
