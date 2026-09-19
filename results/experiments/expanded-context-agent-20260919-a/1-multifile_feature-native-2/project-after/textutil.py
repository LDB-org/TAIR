def slugify(text):
    """Convert text to a slug.

    Lowercases the text, splits on whitespace, and joins the words with
    hyphens. Whitespace-only input returns an empty string.
    """
    words = text.strip().split()
    return '-'.join(words).lower()
