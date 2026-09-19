def slugify(text):
    text = text.lower()
    words = text.split()
    return '-'.join(words)
