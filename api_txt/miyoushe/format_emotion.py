import json

NEW = {}
with open("./emotion.json", encoding="utf8") as f:
    DATA = json.loads(f.read())

for li in DATA["data"]["list"]:
    for item in li["list"]:
        NEW[item["name"]] = item["icon"]
        print("Success", item["id"], item["name"])

with open("./f_e.json", "w", encoding="utf8") as e:
    e.write(str(NEW))
