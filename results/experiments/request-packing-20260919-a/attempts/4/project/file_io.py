from pathlib import Path


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text, append=False):
    mode = "a" if append else "w"
    with open(Path(path), mode, encoding="utf-8") as f:
        f.write(text)
