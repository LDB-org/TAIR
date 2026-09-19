def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()

def write_bytes(path, data, *, append=False):
    mode = 'ab' if append else 'wb'
    with open(path, mode) as f:
        f.write(data)
