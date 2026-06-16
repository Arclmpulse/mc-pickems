import urllib.request
import urllib.error
import gzip
import json

url = "https://liquipedia.net/leagueoflegends/api.php?action=query&list=search&srsearch=Natus+Vincere&format=json"
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "PickemsLogoFetcher/1.0 (mchang@users.noreply.github.com)",
        "Accept-Encoding": "gzip",
    }
)
try:
    with urllib.request.urlopen(req, timeout=6) as resp:
        content = resp.read()
        if resp.info().get('Content-Encoding') == 'gzip':
            content = gzip.decompress(content)
        data = json.loads(content.decode('utf-8'))
        print("API Query Successful!")
        print(json.dumps(data, indent=2)[:500])
except urllib.error.HTTPError as e:
    print(f"API HTTPError: {e.code} {e.reason}")
except Exception as e:
    print(f"API Error: {e}")
