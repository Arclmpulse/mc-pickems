import urllib.request
import urllib.error
import time

url = "https://liquipedia.net/commons/images/3/3f/Natus_Vincere_2021_lightmode.png"

user_agents = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "Chrome Browser"),
    ("PickemsLogoFetcher/1.0 (mchang@users.noreply.github.com)", "Custom Pickems (Recommended)"),
    ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36", "Linux Chrome"),
]

for ua, desc in user_agents:
    print(f"Testing {desc}...")
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            print(f"  Success! Status: {resp.status}, Length: {len(resp.read())}")
            break
    except urllib.error.HTTPError as e:
        print(f"  HTTPError: {e.code} {e.reason}")
    except Exception as e:
        print(f"  Error: {e}")
    time.sleep(2)
