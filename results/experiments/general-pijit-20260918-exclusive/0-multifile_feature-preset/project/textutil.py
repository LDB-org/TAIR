def slugify(text):
    words = text.split()
    if not words:
        return ""
    return "-".join(words).lower()
