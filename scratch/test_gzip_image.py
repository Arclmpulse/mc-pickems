import urllib.request
import urllib.error
import gzip

url = "https://liquipedia.net/commons/images/3/3f/Natus_Vincere_2021_lightmode.png"
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "PickemsLogoFetcher/1.0 (mchang@users.noreply.github.com)",
        "Accept-Encoding": "gzip",
    }
)
try:
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = resp.read()
        if resp.info().get('Content-Encoding') == 'gzip':
            data = gzip.decompress(data)
        print("Success!", len(data))
except urllib.error.HTTPError as e:
    print(f"HTTPError: {e.code} {e.reason}")
except Exception as e:
    print(f"Error: {e}")
