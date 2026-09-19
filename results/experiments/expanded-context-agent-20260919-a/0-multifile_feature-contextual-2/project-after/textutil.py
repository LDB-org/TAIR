def slugify(text):
    words = text.split()
    return '-'.join(words).lower()
