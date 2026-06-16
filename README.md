# Pickems

A local desktop pickems tracker for CS Majors (and eventually LoL).
Built with Python + PyQt6.

---

## Quick start

```bash
cd pickems/
pip install -r requirements.txt
python main.py
```

---

## How to use

### 1. Set up a tournament

Edit `tournaments/<event_name>/tournament.json` once per event.
See `tournaments/iem_cologne_2026/tournament.json` as a template.

**Fields:**
| Field | Description |
|---|---|
| `id` | Unique slug (no spaces), used for the picks save file |
| `name` | Display name shown in the UI |
| `game` | `"cs"` or `"lol"` |
| `stages` | Ordered list of stages |

**Stage types:**
- `"swiss"` — CS Major Swiss format (16 teams, 5 rounds)
- `"single_elim"` — Single elimination bracket (8 teams)

**Team fields:**
- `id` — unique slug (used in results.json)
- `name` — display name
- `seed` — 1 = best, 16 = worst
- `logo_url` — *(optional)* HLTV CDN URL, downloaded and cached automatically

### 2. Make picks

Click either team in a match card to pick them.
Click the same team again to clear the pick.

Picks are saved automatically to `saves/<tournament_id>_picks.json`.

### 3. Add results at end of day

Edit `tournaments/<event_name>/results.json`:

```json
{
  "stage1": {
    "round_1": [
      { "winner": "navi", "loser": "vitality", "score": "16-10" }
    ]
  }
}
```

The app **auto-detects** changes to this file and refreshes immediately —
no need to restart or click anything.

**Rules:**
- Use the same team `id` values from `tournament.json`
- `score` is optional
- Picks for completed matches become **locked** — you can no longer change them
- Your accuracy counter updates in the top-right corner

### 4. How results override picks

| Situation | Display |
|---|---|
| Picked the right team | Green highlight |
| Picked the wrong team | Red highlight on your pick; green on actual winner |
| No pick yet, result in | Winner shown green, loser dimmed |

---

## Getting team logos

Run the helper script to look up HLTV logo URLs by team name:

```bash
python tools/fetch_logos.py "Natus Vincere" "Team Vitality" "FaZe Clan"
```

This outputs `logo_url` values to paste into `tournament.json`.
You can also find the HLTV team ID from the team page URL:
```
https://www.hltv.org/team/6651/natus-vincere
                              ^^^^
                              This number is the ID
```

Logo URL format: `https://img-cdn.hltv.org/teamlogo/6651.svg`

Logos are downloaded once and cached in `cache/logos/`.

---

## Swiss bracket rules (CS Major format)

The engine implements the full official rulebook:

- **Round 1**: Seeds 1v9, 2v10, 3v11, 4v12, 5v13, 6v14, 7v15, 8v16
- **Rounds 2-3**: Highest seed vs lowest seed (greedy, no rematch)
- **Rounds 4-5**: 15-row priority pairing table for 6-team groups
- **Match type**: Bo3 if either team is at 2W or 2L, otherwise Bo1
- **Seeding**: W-L record → Buchholz (difficulty score) → initial seed
- **Advance**: 3 wins | **Eliminate**: 3 losses

---

## File structure

```
pickems/
├── main.py                       # Entry point
├── requirements.txt
├── engine/
│   ├── swiss.py                  # Swiss bracket engine + Buchholz
│   └── bracket.py                # Single elimination engine
├── data/
│   └── manager.py                # Tournament state, picks, file watching
├── ui/
│   ├── main_window.py            # Top-level window
│   ├── sidebar.py                # Game/tournament navigation
│   ├── swiss_view.py             # Swiss bracket display
│   ├── bracket_view.py           # Playoffs display
│   ├── match_card.py             # Individual match widgets
│   ├── utils.py                  # Shared helpers
│   └── styles.qss                # Dark theme stylesheet
├── tools/
│   └── fetch_logos.py            # HLTV logo URL helper
├── tournaments/
│   └── iem_cologne_2026/
│       ├── tournament.json       # ← Edit once per event
│       └── results.json          # ← Edit at end of each day
├── saves/                        # Auto-created; don't edit manually
│   └── iem_cologne_2026_picks.json
└── cache/
    └── logos/                    # Auto-created logo cache
```
