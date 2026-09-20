from pathlib import Path


def write_text(path, text):
    Path(path).write_text(text, encoding="utf-8")


def read_text(path):
    return Path(path).read_text(encoding="utf-8")
