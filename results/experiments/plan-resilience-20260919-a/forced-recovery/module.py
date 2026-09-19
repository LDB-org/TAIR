import os
from pathlib import Path

def read_text(path):
    """Read entire file as UTF-8 text."""
    return Path(path).read_text(encoding='utf-8')

def write_text(path, text, *, append=False):
    """Write text to file, creating parent directories if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-8') as f:
        f.write(text)
