import json
from pathlib import Path


def save_json(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    Path(path).write_text(text + "\n", encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
