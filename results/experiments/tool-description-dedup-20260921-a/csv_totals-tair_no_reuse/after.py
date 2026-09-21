import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header row with columns 'category' and 'amount'.
    Returns a dict mapping category name to summed integer amount.
    Empty text or header-only input returns {}.
    An invalid (non-integer) amount raises ValueError.
    """
    if not text:
        return {}

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}

    if not header:
        return {}

    # Normalize header names (strip whitespace) and locate columns.
    header = [h.strip() for h in header]
    try:
        cat_idx = header.index("category")
        amt_idx = header.index("amount")
    except ValueError:
        raise ValueError("CSV must have 'category' and 'amount' columns")

    result = {}
    for row in reader:
        if not row:
            continue
        category = row[cat_idx]
        amount_str = row[amt_idx]
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount_str!r}")
        result[category] = result.get(category, 0) + amount

    return result
