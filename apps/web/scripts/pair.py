"""Пары «макет | приложение» для сверки (E38-16): python apps/web/scripts/pair.py [out]. Нужен Pillow."""
import json, sys, pathlib
from PIL import Image
root = pathlib.Path(__file__).resolve().parents[3]
out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / "reports/design-check"
(out / "pair").mkdir(exist_ok=True)
for m in json.loads((out / "manifest.json").read_text(encoding="utf8")):
    a = Image.open(out / "app" / f"{m['name']}_{m['width']}.png").convert("RGB")
    d = Image.open(root / "docs/design/v2/png" / f"{m['mock']}.png").convert("RGB")
    h = max(a.height, d.height)
    h = min(h, 2600)
    c = Image.new("RGB", (a.width + d.width + 20, h), (255, 0, 255))
    c.paste(d.crop((0, 0, d.width, min(d.height, h))), (0, 0))
    c.paste(a.crop((0, 0, a.width, min(a.height, h))), (d.width + 20, 0))
    c.save(out / "pair" / f"{m['name']}_{m['width']}.png")
