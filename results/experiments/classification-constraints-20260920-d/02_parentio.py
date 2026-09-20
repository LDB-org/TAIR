from pathlib import Path


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def read_text(path):
    return Path(path).read_text(encoding="utf-8")
