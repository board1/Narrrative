import requests
from pathlib import Path

url = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
out = Path("data/masterfilelist.txt")
out.parent.mkdir(parents=True, exist_ok=True)

r = requests.get(url, timeout=60)
r.raise_for_status()

out.write_bytes(r.content)
print("done:", out, "bytes=", len(r.content))