def parse_count(text):
    try:
        value = int(text)
    except ValueError:
        return -1
    return value
SOURCE_VERSION = 2
