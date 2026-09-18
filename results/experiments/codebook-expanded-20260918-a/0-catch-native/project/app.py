def parse_count(text):
    try:
        value = int(text)
        return value
    except ValueError:
        return -1
SOURCE_VERSION = 2
