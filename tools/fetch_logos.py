#!/usr/bin/env python3
"""
fetch_logos.py — helper to search Liquipedia for team logos and build logo_url entries.

Usage:
    python tools/fetch_logos.py "Natus Vincere" "Team Vitality" "G2 Esports"

Output:
    JSON snippet ready to paste into your tournament.json team entries.

The Liquipedia logo URLs will point to original high-resolution logo images.
"""

import sys
import json
import urllib.request
import urllib.parse
import gzip
import re


def get_liquipedia_logo(game: str, name: str) -> tuple[str | None, str | None]:
    """
    Search Liquipedia (for a given game wiki) and return (logo_url, canonical_title).
    """
    encoded = urllib.parse.quote(name)
    search_url = f"https://liquipedia.net/{game}/api.php?action=query&list=search&srsearch={encoded}&format=json"
    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": "PickemsLogoFetcher/1.0 (mchang@users.noreply.github.com)",
            "Accept-Encoding": "gzip",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.loads(gzip.decompress(r.read()).decode('utf-8'))
            results = res.get("query", {}).get("search", [])
            if not results:
                return None, None
            title = results[0]["title"]
    except Exception as e:
        print(f"  [warn] Search failed on {game} for '{name}': {e}", file=sys.stderr)
        return None, None

    encoded_title = urllib.parse.quote(title)
    parse_url = f"https://liquipedia.net/{game}/api.php?action=parse&page={encoded_title}&prop=text&format=json"
    req = urllib.request.Request(
        parse_url,
        headers={
            "User-Agent": "PickemsLogoFetcher/1.0 (mchang@users.noreply.github.com)",
            "Accept-Encoding": "gzip",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.loads(gzip.decompress(r.read()).decode('utf-8'))
            html = res.get("parse", {}).get("text", {}).get("*", "")
            
            # Find the main logo image in the HTML (infobox-image class or first image in infobox table)
            img_match = re.search(r'class="infobox-image"[^>]*>.*?src="([^"]+)"', html, re.DOTALL)
            if not img_match:
                img_match = re.search(r'<table class="infobox.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
            if not img_match:
                img_match = re.search(r'<img[^>]+src="([^"]+)"', html)
                
            if img_match:
                src = img_match.group(1)
                # Prefix with domain if relative
                if src.startswith("/"):
                    src = "https://liquipedia.net" + src
                
                # Clean thumbnail format to get original resolution image
                if "/thumb/" in src:
                    parts = src.split("/")
                    if "thumb" in parts:
                        parts.remove("thumb")
                    parts = parts[:-1]
                    src = "/".join(parts)
                return src, title
    except Exception as e:
        print(f"  [warn] Parse failed on {game} for '{title}': {e}", file=sys.stderr)
    return None, None


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    team_names = sys.argv[1:]
    results = []

    for name in team_names:
        print(f"Searching: {name} ...", file=sys.stderr)
        logo_url = None
        canonical = None
        
        # Try League of Legends first
        logo_url, canonical = get_liquipedia_logo("leagueoflegends", name)
        
        # If not found, try Counter-Strike
        if not logo_url:
            logo_url, canonical = get_liquipedia_logo("counterstrike", name)
            
        if logo_url:
            print(f"  ✓ Found  →  {logo_url}", file=sys.stderr)
            results.append({
                "name": canonical or name,
                "logo_url": logo_url,
            })
        else:
            print(f"  ✗ Not found — add logo_url manually", file=sys.stderr)
            results.append({"name": name, "logo_url": ""})

    print("\n── Paste the logo_url values into your tournament.json: ──\n")
    for r in results:
        snippet = {
            "name": r["name"],
            "logo_url": r["logo_url"],
        }
        print(json.dumps(snippet, indent=2))
        print()


if __name__ == "__main__":
    main()
