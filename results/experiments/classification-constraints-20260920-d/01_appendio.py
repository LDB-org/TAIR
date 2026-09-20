from pathlib import Path


def write_text(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def read_text(path):
    return Path(path).read_text(encoding="utf-8")
