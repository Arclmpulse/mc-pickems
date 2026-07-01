"""
World Cup 2026 knockout bracket engine.

32-team single elimination with FIFA-standard seeding rules.
The Round of 32 has 16 fixed matches derived from group positions.
8 of those 16 slots involve third-place finishers (determined by which
8 of the 12 third-place teams qualify based on points).

For the picks app, we treat each R32 slot as a predictable "role":
  winner_A, runner_up_A, winner_B, runner_up_B, ... winner_L, runner_up_L,
  plus best_3rd_1 .. best_3rd_8 (seeded 25-32).

The engine receives teams as a flat list of 32 dicts (roles resolved by the manager).
Match pairings are hardcoded per the FIFA 2026 bracket.

Round structure (16 R32 matches matching the FIFA 2026 bracket):
  Match 1:  2A vs 2B              (Match 73)
  Match 2:  1F vs 2C              (Match 75)
  Match 3:  1E vs 3rd A/B/C/D/F   (Match 74) [best 3rd #1]
  Match 4:  1I vs 3rd C/D/F/G/H   (Match 77) [best 3rd #2]
  Match 5:  1C vs 2F              (Match 76)
  Match 6:  2E vs 2I              (Match 78)
  Match 7:  1A vs 3rd C/E/F/H/I   (Match 79) [best 3rd #3]
  Match 8:  1L vs 3rd D/E/I/J/L   (Match 80) [best 3rd #4]
  Match 9:  2K vs 2L              (Match 83)
  Match 10: 1H vs 2J              (Match 84)
  Match 11: 1D vs 3rd B/E/F/I/J   (Match 81) [best 3rd #5]
  Match 12: 1G vs 3rd A/E/H/I/J   (Match 82) [best 3rd #6]
  Match 13: 1J vs 2H              (Match 86)
  Match 14: 2D vs 2G              (Match 88)
  Match 15: 1B vs 3rd E/F/G/I/J   (Match 85) [best 3rd #7]
  Match 16: 1K vs 3rd E/H/I/J/K   (Match 87) [best 3rd #8]

NOTE: Implementing the full 495-scenario third-place assignment is very complex.
For this app we simplify: the 8 advancing third-place teams are assigned to the
bracket slots in rank order (best 3rd → slot 1, 2nd best → slot 2, etc.).
The tournament.json lists these as seeds 25-32 so the manager can resolve them
from group state.

Bracket R16 pairings (winners of adjacent R32 matches):
  R16 m1: W(M1) vs W(M2)          (Match 90: W73 vs W75)
  R16 m2: W(M3) vs W(M4)          (Match 89: W74 vs W77)
  R16 m3: W(M5) vs W(M6)          (Match 91: W76 vs W78)
  R16 m4: W(M7) vs W(M8)          (Match 92: W79 vs W80)
  R16 m5: W(M9) vs W(M10)         (Match 93: W83 vs W84)
  R16 m6: W(M11) vs W(M12)        (Match 94: W81 vs W82)
  R16 m7: W(M13) vs W(M14)        (Match 95: W86 vs W88)
  R16 m8: W(M15) vs W(M16)        (Match 96: W85 vs W87)

QF (4 matches):
  QF1: W(R16 m1) vs W(R16 m2)     (Match 97: W89 vs W90)
  QF2: W(R16 m3) vs W(R16 m4)     (Match 98: W91 vs W92)
  QF3: W(R16 m5) vs W(R16 m6)     (Match 99: W93 vs W94)
  QF4: W(R16 m7) vs W(R16 m8)     (Match 100: W95 vs W96)

SF (2 matches):
  SF1: W(QF1) vs W(QF2)           (Semifinal 1)
  SF2: W(QF3) vs W(QF4)           (Semifinal 2)

Final: W(SF1) vs W(SF2)
"""

from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class WCTeam:
    team_id: str
    name: str
    seed: int   # 1-32; 1-12=group winners A-L, 13-24=runners-up A-L, 25-32=best 3rds
    logo_url: Optional[str] = None
    logo_path: Optional[str] = None
    status: str = "active"  # "active" | "champion" | "eliminated"


@dataclass
class WCMatch:
    match_id: str
    round_num: int    # 1=R32, 2=R16, 3=QF, 4=SF, 5=Final
    slot: str         # human label, e.g. "R32-1"
    team1_id: Optional[str] = None
    team2_id: Optional[str] = None
    winner_id: Optional[str] = None
    match_type: str = "bo1"  # all football matches are bo1


@dataclass
class WCBracketState:
    rounds: List[List[WCMatch]]  # [R32(16), R16(8), QF(4), SF(2), Final(1)]
    teams: Dict[str, WCTeam]


# ── Fixed R32 seeding pairs (seed numbers 1-32) ───────────────────────────────
# Seeds 1-12  = group winners A-L (by group letter order)
# Seeds 13-24 = group runners-up A-L
# Seeds 25-32 = best 8 third-place teams (ranked)
#
# FIFA 2026 standard bracket fixed pairings:
_R32_PAIRS = [
    # (slot_label, seed1, seed2)
    # ── Left Bracket ──────────────────────────────────────────────────────────
    ("R32-1",  13, 14),   # Match 73: 2A vs 2B
    ("R32-2",   6, 15),   # Match 75: 1F vs 2C
    
    ("R32-3",   5, 25),   # Match 74: 1E vs best 3rd #1
    ("R32-4",   9, 26),   # Match 77: 1I vs best 3rd #2
    
    ("R32-5",   3, 18),   # Match 76: 1C vs 2F
    ("R32-6",  17, 21),   # Match 78: 2E vs 2I
    
    ("R32-7",   1, 27),   # Match 79: 1A vs best 3rd #3
    ("R32-8",  12, 28),   # Match 80: 1L vs best 3rd #4

    # ── Right Bracket ─────────────────────────────────────────────────────────
    ("R32-9",  23, 24),   # Match 83: 2K vs 2L
    ("R32-10",  8, 22),   # Match 84: 1H vs 2J
    
    ("R32-11",  4, 29),   # Match 81: 1D vs best 3rd #5
    ("R32-12",  7, 30),   # Match 82: 1G vs best 3rd #6
    
    ("R32-13", 10, 20),   # Match 86: 1J vs 2H
    ("R32-14", 16, 19),   # Match 88: 2D vs 2G
    
    ("R32-15",  2, 31),   # Match 85: 1B vs best 3rd #7
    ("R32-16", 11, 32),   # Match 87: 1K vs best 3rd #8
]

# R16 pairings: which R32 match winners meet
_R16_PAIRS = [
    ("R16-1", 0, 1),
    ("R16-2", 2, 3),
    ("R16-3", 4, 5),
    ("R16-4", 6, 7),
    ("R16-5", 8, 9),
    ("R16-6", 10, 11),
    ("R16-7", 12, 13),
    ("R16-8", 14, 15),
]

_QF_PAIRS = [
    ("QF-1", 0, 1),
    ("QF-2", 2, 3),
    ("QF-3", 4, 5),
    ("QF-4", 6, 7),
]

_SF_PAIRS = [
    ("SF-1", 0, 1),
    ("SF-2", 2, 3),
]


def compute_wc_bracket_state(
    stage_id: str,
    initial_teams: List[dict],           # 32 teams, seeds 1-32
    effective_winners: Dict[str, str],   # match_id → winning team_id
) -> WCBracketState:
    """
    Compute the full 32-team WC single-elimination bracket.
    """
    teams: Dict[str, WCTeam] = {
        t["id"]: WCTeam(
            team_id=t["id"], name=t["name"], seed=t["seed"],
            logo_url=t.get("logo_url"),
        )
        for t in initial_teams
    }
    by_seed: Dict[int, str] = {t["seed"]: t["id"] for t in initial_teams}

    def _mk_id(slot: str, t1: Optional[str], t2: Optional[str]) -> str:
        a = t1 or "tbd"
        b = t2 or "tbd"
        x, y = sorted([a, b])
        return f"{stage_id}_{slot}_{x}_{y}"

    def _make(slot: str, rnd: int, t1: Optional[str], t2: Optional[str]) -> WCMatch:
        return WCMatch(
            match_id=_mk_id(slot, t1, t2),
            round_num=rnd, slot=slot,
            team1_id=t1, team2_id=t2,
        )

    # ── Round 1: R32 ────────────────────────────────────────────────────────
    r32: List[WCMatch] = []
    for slot, s1, s2 in _R32_PAIRS:
        t1, t2 = by_seed.get(s1), by_seed.get(s2)
        m = _make(slot, 1, t1, t2)
        r32.append(m)

    for m in r32:
        w = effective_winners.get(m.match_id)
        if w and m.team1_id and m.team2_id and w in (m.team1_id, m.team2_id):
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            if loser in teams:
                teams[loser].status = "eliminated"

    # ── Round 2: R16 ────────────────────────────────────────────────────────
    r16: List[WCMatch] = []
    for slot, i1, i2 in _R16_PAIRS:
        t1 = r32[i1].winner_id
        t2 = r32[i2].winner_id
        m = _make(slot, 2, t1, t2)
        r16.append(m)

    for m in r16:
        w = effective_winners.get(m.match_id)
        if w and m.team1_id and m.team2_id and w in (m.team1_id, m.team2_id):
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            if loser in teams:
                teams[loser].status = "eliminated"

    # ── Round 3: Quarterfinals ───────────────────────────────────────────────
    qf: List[WCMatch] = []
    for slot, i1, i2 in _QF_PAIRS:
        t1 = r16[i1].winner_id
        t2 = r16[i2].winner_id
        m = _make(slot, 3, t1, t2)
        qf.append(m)

    for m in qf:
        w = effective_winners.get(m.match_id)
        if w and m.team1_id and m.team2_id and w in (m.team1_id, m.team2_id):
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            if loser in teams:
                teams[loser].status = "eliminated"

    # ── Round 4: Semifinals ──────────────────────────────────────────────────
    sf: List[WCMatch] = []
    for slot, i1, i2 in _SF_PAIRS:
        t1 = qf[i1].winner_id
        t2 = qf[i2].winner_id
        m = _make(slot, 4, t1, t2)
        sf.append(m)

    for m in sf:
        w = effective_winners.get(m.match_id)
        if w and m.team1_id and m.team2_id and w in (m.team1_id, m.team2_id):
            m.winner_id = w
            loser = m.team2_id if w == m.team1_id else m.team1_id
            if loser in teams:
                teams[loser].status = "eliminated"

    # ── Round 5: Final ───────────────────────────────────────────────────────
    fin_t1 = sf[0].winner_id
    fin_t2 = sf[1].winner_id
    final = _make("Final", 5, fin_t1, fin_t2)
    w = effective_winners.get(final.match_id)
    if w and final.team1_id and final.team2_id and w in (final.team1_id, final.team2_id):
        final.winner_id = w
        loser = final.team2_id if w == final.team1_id else final.team1_id
        if w in teams:
            teams[w].status = "champion"
        if loser in teams:
            teams[loser].status = "eliminated"

    return WCBracketState(
        rounds=[r32, r16, qf, sf, [final]],
        teams=teams,
    )
