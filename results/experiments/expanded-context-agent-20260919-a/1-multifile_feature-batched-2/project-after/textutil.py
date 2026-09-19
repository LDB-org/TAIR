def slugify(text):
    """Convert text to a slug: lowercase, split on whitespace, join with hyphens.

    Whitespace-only input returns an empty string.
    """
    words = text.strip().lower().split()
    return '-'.join(words)
