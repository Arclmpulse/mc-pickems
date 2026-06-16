"""
TournamentManager — coordinates data loading, state computation,
pick persistence, and auto-watching results.json for changes.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from PyQt6.QtCore import QObject, pyqtSignal, QFileSystemWatcher

from engine.swiss import (
    compute_swiss_state, SwissState, MatchInfo, get_final_standings
)
from engine.bracket import compute_bracket_state, BracketState
from engine.double_elim import compute_double_elim_state, DoubleElimState


StageState = Union[SwissState, BracketState, DoubleElimState]


class TournamentManager(QObject):
    """
    Manages one tournament directory.

    Directory layout expected:
        <dir>/tournament.json   — team / stage definitions (edit once per event)
        <dir>/results.json      — match results (you edit this at end of day)

    Picks are saved in the `saves_dir` as  <tournament_id>_picks.json.
    """

    state_changed = pyqtSignal()  # emitted when results or picks change

    def __init__(self, tournament_dir: str, saves_dir: str, parent=None):
        super().__init__(parent)
        self.tournament_dir = Path(tournament_dir)
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(parents=True, exist_ok=True)

        self._tournament: dict = {}
        self._results: dict = {}
        # match_id → {"picked": team_id, "locked": bool}
        self._picks: dict = {}

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_results_file_changed)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        self._load_all()

    # ── Loading / saving ─────────────────────────────────────────────────────

    def _load_all(self) -> None:
        self._load_tournament()
        self._load_picks()
        self._load_results()
        self._setup_watcher()

    def _load_tournament(self) -> None:
        path = self.tournament_dir / "tournament.json"
        with open(path, encoding="utf-8") as f:
            self._tournament = json.load(f)
        self._fill_missing_logo_urls()

    def _fill_missing_logo_urls(self) -> None:
        """Scan current and other tournament directories to find and copy missing team logo_urls."""
        missing_ids = set()
        for stage in self._tournament.get("stages", []):
            for team in stage.get("teams", []):
                if not team.get("logo_url"):
                    missing_ids.add(team["id"])

        if not missing_ids:
            return

        discovered = {}
        # First, scan current tournament stages for logos
        for stage in self._tournament.get("stages", []):
            for team in stage.get("teams", []):
                tid = team["id"]
                if team.get("logo_url"):
                    discovered[tid] = team["logo_url"]

        # Then, scan other tournaments
        parent_dir = self.tournament_dir.parent
        if parent_dir.exists():
            for d in parent_dir.iterdir():
                if d.is_dir() and d != self.tournament_dir:
                    t_json = d / "tournament.json"
                    if t_json.exists():
                        try:
                            with open(t_json, encoding="utf-8") as f:
                                other_t = json.load(f)
                            for stage in other_t.get("stages", []):
                                for team in stage.get("teams", []):
                                    tid = team["id"]
                                    if tid in missing_ids and team.get("logo_url"):
                                        discovered[tid] = team["logo_url"]
                        except Exception:
                            pass

        # Populate missing logo_urls
        for stage in self._tournament.get("stages", []):
            for team in stage.get("teams", []):
                tid = team["id"]
                if not team.get("logo_url") and tid in discovered:
                    team["logo_url"] = discovered[tid]

    def _load_results(self) -> None:
        path = self.tournament_dir / "results.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    self._results = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._results = {}
        else:
            self._results = {}

    def _save_picks(self) -> None:
        with open(self._picks_path, "w", encoding="utf-8") as f:
            json.dump(self._picks, f, indent=2)

    def _load_picks(self) -> None:
        if self._picks_path.exists():
            try:
                with open(self._picks_path, encoding="utf-8") as f:
                    self._picks = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._picks = {}
        else:
            self._picks = {}

    @property
    def _picks_path(self) -> Path:
        tid = self._tournament.get("id", "unknown")
        return self.saves_dir / f"{tid}_picks.json"

    # ── File watching ────────────────────────────────────────────────────────

    def _setup_watcher(self) -> None:
        # Watch the directory so we detect results.json being created
        dir_str = str(self.tournament_dir)
        if dir_str not in self._watcher.directories():
            self._watcher.addPath(dir_str)

        results_str = str(self.tournament_dir / "results.json")
        if os.path.exists(results_str) and results_str not in self._watcher.files():
            self._watcher.addPath(results_str)

    def _on_results_file_changed(self, path: str) -> None:
        """Called when results.json is modified (or replaced by atomic save)."""
        self._load_results()
        self._lock_picks_from_results()
        self._save_picks()
        # Some editors do atomic rename, removing the inode — re-add to watcher
        if path not in self._watcher.files():
            self._watcher.addPath(path)
        self.state_changed.emit()

    def _on_directory_changed(self, path: str) -> None:
        """Called when the tournament directory changes (results.json created)."""
        results_str = str(self.tournament_dir / "results.json")
        if os.path.exists(results_str) and results_str not in self._watcher.files():
            self._watcher.addPath(results_str)
            self._on_results_file_changed(results_str)

    # ── State computation ────────────────────────────────────────────────────

    def compute_stage_state(self, stage_config: dict) -> Optional[StageState]:
        """
        Compute the full bracket state for a stage, resolving any dynamic qualifiers first.
        """
        stage_id = stage_config["id"]
        stage_type = stage_config["type"]
        teams = stage_config["teams"]

        resolved_teams = self._resolve_dynamic_teams(teams)

        if stage_type == "swiss":
            return self._compute_swiss(stage_id, resolved_teams)
        if stage_type == "single_elim":
            return self._compute_bracket(stage_id, resolved_teams)
        if stage_type == "double_elim":
            return self._compute_double_elim(stage_id, resolved_teams, stage_config)
        return None

    def _resolve_playin_winner(self) -> Optional[dict]:
        playin_stage = next((s for s in self.stages if s["id"] == "playin"), None)
        if not playin_stage:
            return None
        state = self._compute_double_elim("playin", playin_stage["teams"], playin_stage)
        gf_match = next((m for r in state.rounds for m in r if m.bracket_half == "Final"), None)
        if gf_match and gf_match.winner_id:
            for team in playin_stage["teams"]:
                if team["id"] == gf_match.winner_id:
                    return team
        return None

    def _resolve_dynamic_teams(self, teams: List[dict]) -> List[dict]:
        resolved_teams = []
        for team in teams:
            tid = team["id"]
            if tid == "playin_winner":
                winner_team = self._resolve_playin_winner()
                if winner_team:
                    resolved_teams.append({
                        "id": winner_team["id"],
                        "name": winner_team["name"],
                        "seed": team["seed"],
                        "logo_url": winner_team.get("logo_url", "")
                    })
                    continue
            elif "_adv" in tid:
                parts = tid.split("_adv")
                if len(parts) == 2 and parts[1].isdigit():
                    prev_stage_id = parts[0]
                    idx = int(parts[1]) - 1  # 0-indexed
                    prev_stage = next((s for s in self.stages if s["id"] == prev_stage_id), None)
                    if prev_stage:
                        # Recursively compute preceding stage
                        state = self.compute_stage_state(prev_stage)
                        if state:
                            advancing = self._get_advancing_teams_from_state(state)
                            if idx < len(advancing):
                                resolved_teams.append({
                                    "id": advancing[idx]["id"],
                                    "name": advancing[idx]["name"],
                                    "seed": team["seed"],
                                    "logo_url": advancing[idx].get("logo_url", "")
                                })
                                continue
            resolved_teams.append(team)
        return resolved_teams

    def _get_advancing_teams_from_state(self, state: StageState) -> List[dict]:
        advancing = []
        if isinstance(state, SwissState):
            # Sort Swiss advanced teams: fewer losses, then higher Buchholz, then better seed
            swiss_adv = [t for t in state.teams.values() if t.status == "advanced"]
            swiss_adv.sort(key=lambda t: (t.losses, -t.buchholz, t.initial_seed))
            for t in swiss_adv:
                advancing.append({
                    "id": t.team_id,
                    "name": t.name,
                    "logo_url": t.logo_url or ""
                })
        elif isinstance(state, DoubleElimState):
            gf_match = next((m for r in state.rounds for m in r if m.bracket_half == "Final"), None)
            if gf_match and gf_match.winner_id:
                winner_id = gf_match.winner_id
                team_record = state.teams.get(winner_id)
                if team_record:
                    advancing.append({
                        "id": team_record.team_id,
                        "name": team_record.name,
                        "logo_url": team_record.logo_url or ""
                    })
        return advancing

    def _compute_double_elim(
        self,
        stage_id: str,
        teams: List[dict],
        stage_config: dict,
    ) -> DoubleElimState:
        collected: Dict[str, str] = {}
        for _ in range(16):
            state = compute_double_elim_state(stage_id, teams, collected, stage_config)
            prev_size = len(collected)
            stage_results = self._results.get(stage_id, {})

            for rnd_matches in state.rounds:
                for m in rnd_matches:
                    if m.match_id in collected or not m.team1_id or not m.team2_id:
                        continue
                    found = False
                    for r in stage_results.get(f"round_{m.round_num}", []):
                        w, lo = r.get("winner", ""), r.get("loser", "")
                        if w in (m.team1_id, m.team2_id) and lo in (m.team1_id, m.team2_id):
                            collected[m.match_id] = w
                            found = True
                            break
                    if not found:
                        p = self._picks.get(m.match_id, {}).get("picked")
                        if p in (m.team1_id, m.team2_id):
                            collected[m.match_id] = p

            if len(collected) == prev_size:
                break

        return compute_double_elim_state(stage_id, teams, collected, stage_config)

    def _collect_round_winners(
        self,
        stage_id: str,
        matches: List[MatchInfo],
    ) -> Dict[str, str]:
        """
        Build effective_winners for a list of matches.
        Real results take priority over user picks.
        """
        winners: Dict[str, str] = {}
        stage_results = self._results.get(stage_id, {})

        for m in matches:
            rnd_key = f"round_{m.round_num}"
            found_result = False
            for r in stage_results.get(rnd_key, []):
                w = r.get("winner", "")
                lo = r.get("loser", "")
                if w in (m.team1_id, m.team2_id) and lo in (m.team1_id, m.team2_id):
                    winners[m.match_id] = w
                    found_result = True
                    break
            if not found_result:
                p = self._picks.get(m.match_id, {}).get("picked")
                if p in (m.team1_id, m.team2_id):
                    winners[m.match_id] = p

        return winners

    def _compute_swiss(self, stage_id: str, teams: List[dict]) -> SwissState:
        """
        Iteratively compute Swiss state.
        Each iteration discovers one more round of winners.
        Converges when no new winners are found.
        """
        collected: Dict[str, str] = {}

        for _ in range(6):  # max 5 rounds + convergence check
            state = compute_swiss_state(stage_id, teams, collected)
            prev_size = len(collected)

            for rnd_matches in state.rounds:
                new_w = self._collect_round_winners(stage_id, rnd_matches)
                for mid, w in new_w.items():
                    if mid not in collected:
                        collected[mid] = w

            if len(collected) == prev_size:
                break

        return compute_swiss_state(stage_id, teams, collected)

    def _compute_bracket(self, stage_id: str, teams: List[dict]) -> BracketState:
        """Iteratively compute bracket state."""
        collected: Dict[str, str] = {}

        for _ in range(4):  # max 3 rounds + convergence check
            state = compute_bracket_state(stage_id, teams, collected)
            prev_size = len(collected)
            stage_results = self._results.get(stage_id, {})

            for rnd_matches in state.rounds:
                for m in rnd_matches:
                    if m.match_id in collected or not m.team1_id or not m.team2_id:
                        continue
                    rnd_key = f"round_{m.round_num}"
                    found = False
                    for r in stage_results.get(rnd_key, []):
                        w, lo = r.get("winner", ""), r.get("loser", "")
                        if w in (m.team1_id, m.team2_id) and lo in (m.team1_id, m.team2_id):
                            collected[m.match_id] = w
                            found = True
                            break
                    if not found:
                        p = self._picks.get(m.match_id, {}).get("picked")
                        if p in (m.team1_id, m.team2_id):
                            collected[m.match_id] = p

            if len(collected) == prev_size:
                break

        return compute_bracket_state(stage_id, teams, collected)

    # ── Pick management ───────────────────────────────────────────────────────

    def make_pick(self, match_id: str, team_id: str) -> bool:
        """Record a pick. Returns False if the match is locked."""
        if self.is_locked(match_id):
            return False
        existing = self._picks.get(match_id, {}).get("picked")
        if existing == team_id:
            # Toggle: clicking same team again clears the pick
            self._picks.pop(match_id, None)
        else:
            self._picks[match_id] = {"picked": team_id, "locked": False}
        self._save_picks()
        self.state_changed.emit()
        return True

    def is_locked(self, match_id: str) -> bool:
        return self._picks.get(match_id, {}).get("locked", False)

    def get_pick(self, match_id: str) -> Optional[str]:
        return self._picks.get(match_id, {}).get("picked")

    def find_result_winner(
        self, stage_id: str, round_num: int, team1_id: str, team2_id: str
    ) -> Optional[str]:
        """Return the actual winner from results.json, or None."""
        rnd_key = f"round_{round_num}"
        teams = {team1_id, team2_id}
        for r in self._results.get(stage_id, {}).get(rnd_key, []):
            w, lo = r.get("winner", ""), r.get("loser", "")
            if w in teams and lo in teams:
                return w
        return None

    def _lock_picks_from_results(self) -> None:
        """Lock all picks that now have actual results."""
        for stage in self.stages:
            stage_id = stage["id"]
            state = self.compute_stage_state(stage)
            if state is None:
                continue
            all_matches = [m for rnd in state.rounds for m in rnd]
            for m in all_matches:
                actual = self.find_result_winner(
                    stage_id, m.round_num, m.team1_id, m.team2_id
                )
                if actual:
                    if m.match_id not in self._picks:
                        self._picks[m.match_id] = {}
                    self._picks[m.match_id]["locked"] = True

    # ── Accuracy ──────────────────────────────────────────────────────────────

    def get_accuracy_stats(self) -> Tuple[int, int, float]:
        """Returns (correct, total, percentage)."""
        correct = total = 0
        for stage in self.stages:
            stage_id = stage["id"]
            state = self.compute_stage_state(stage)
            if state is None:
                continue
            all_matches = [m for rnd in state.rounds for m in rnd]
            for m in all_matches:
                actual = self.find_result_winner(
                    stage_id, m.round_num, m.team1_id, m.team2_id
                )
                picked = self.get_pick(m.match_id)
                if actual and picked:
                    total += 1
                    if picked == actual:
                        correct += 1
        pct = (correct / total * 100) if total else 0.0
        return correct, total, pct

    # ── Logo caching ──────────────────────────────────────────────────────────

    def ensure_logo_cached(
        self, team_id: str, logo_url: str, cache_dir: Path
    ) -> Optional[str]:
        """
        Download and cache a team logo if not already present.
        Returns the local file path, or None on failure.
        """
        import urllib.request

        cache_dir.mkdir(parents=True, exist_ok=True)
        ext = ".svg" if ".svg" in logo_url else ".png"
        cached = cache_dir / f"{team_id}{ext}"

        if cached.exists():
            return str(cached)

        try:
            req = urllib.request.Request(
                logo_url,
                headers={
                    "User-Agent": "PickemsLogoFetcher/1.0 (mchang@users.noreply.github.com)",
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read()
                if resp.info().get('Content-Encoding') == 'gzip':
                    import gzip
                    data = gzip.decompress(data)
            with open(cached, "wb") as f:
                f.write(data)
            return str(cached)
        except Exception:
            return None

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def tournament_name(self) -> str:
        return self._tournament.get("name", "Unknown Tournament")

    @property
    def tournament_id(self) -> str:
        return self._tournament.get("id", "unknown")

    @property
    def game(self) -> str:
        return self._tournament.get("game", "cs")

    @property
    def stages(self) -> List[dict]:
        return self._tournament.get("stages", [])
