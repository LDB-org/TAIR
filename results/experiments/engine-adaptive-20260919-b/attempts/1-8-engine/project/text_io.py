def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_text(path, text, *, append=False):
    import os
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-8') as f:
        f.write(text)
