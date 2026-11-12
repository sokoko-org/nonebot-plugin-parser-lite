import json
from pathlib import Path

NEW = {}
with open(Path(__file__).parent / "emotion.json", encoding="utf8") as f:
    DATA = json.loads(f.read())

for li in DATA["data"]["list"]:
    for item in li["list"]:
        NEW[item["name"]] = item["icon"]
        print("Success", item["id"], item["name"])  # noqa: T201

with open(Path(__file__).parent / "f_e.json", "w", encoding="utf8") as e:
    e.write(json.dumps(NEW, ensure_ascii=False))
