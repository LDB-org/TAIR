from pathlib import Path

def read_text(path):
    """Read the entire file as UTF-8 text and return it."""
    return Path(path).read_text(encoding='utf-8')

def write_text(path, text, *, append=False):
    """Write text as UTF-8, overwriting or appending."""
    p = Path(path)
    if append:
        with open(p, 'a', encoding='utf-8') as f:
            f.write(text)
    else:
        p.write_text(text, encoding='utf-8')
