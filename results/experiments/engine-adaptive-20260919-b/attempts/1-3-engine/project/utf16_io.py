def read_text(path):
    with open(path, 'r', encoding='utf-16') as f:
        return f.read()

def write_text(path, text, *, append=False):
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-16') as f:
        f.write(text)
