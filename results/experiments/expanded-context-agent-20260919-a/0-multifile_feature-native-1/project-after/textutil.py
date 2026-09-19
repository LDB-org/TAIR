def slugify(text):
    """Convert text to a URL-friendly slug.

    Lowercases the text, splits on whitespace, and joins the words with
    hyphens. Whitespace-only input returns an empty string.
    """
    words = text.lower().split()
    return '-'.join(words)
