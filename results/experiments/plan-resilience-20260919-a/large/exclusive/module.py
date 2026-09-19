def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_text(path, text):
    with open(path, 'x', encoding='utf-8') as f:
        f.write(text)
