import zipfile
from pathlib import Path

zip_dir = Path("data/gkg_zips")
out_dir = Path("data/gkg_csv")
out_dir.mkdir(parents=True, exist_ok=True)

for zf in zip_dir.glob("*.zip"):
    outpath = out_dir / zf.name.replace(".zip", "")
    if outpath.exists():
        print("exists, skip:", outpath.name)
        continue

    print("unzipping:", zf.name)
    with zipfile.ZipFile(zf, "r") as z:
        z.extractall(out_dir)

print("done")