import csv
from io import StringIO


def totals(text):
    """Parse CSV with header category,amount and sum integer amounts per category.

    Returns a dict mapping category name to total. Empty text or header-only
    input returns {}. An invalid amount raises ValueError.
    """
    if not text or not text.strip():
        return {}

    reader = csv.reader(StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}

    if not header:
        return {}

    # Normalize header names (strip whitespace)
    header = [h.strip() for h in header]
    if "category" not in header or "amount" not in header:
        raise ValueError("CSV must have category and amount columns")

    cat_idx = header.index("category")
    amt_idx = header.index("amount")

    result = {}
    for row in reader:
        if not row:
            continue
        # Skip fully empty rows
        if all(cell.strip() == "" for cell in row):
            continue
        category = row[cat_idx].strip()
        amount_str = row[amt_idx].strip()
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount_str!r}")
        result[category] = result.get(category, 0) + amount

    return result
