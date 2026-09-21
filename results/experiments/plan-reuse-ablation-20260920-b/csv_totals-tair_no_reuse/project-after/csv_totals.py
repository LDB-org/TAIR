import csv
from collections import defaultdict
from io import StringIO


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header with columns 'category' and 'amount'.
    Amounts are integers (may be negative). Category names may contain
    quoted commas. Returns a dict mapping category -> total amount.
    Empty text or header-only input returns {}.
    Raises ValueError if an amount is not a valid integer.
    """
    if not text or not text.strip():
        return {}

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        return {}

    # Normalize header names (strip whitespace) and require category/amount.
    fieldnames = [name.strip() if name else name for name in reader.fieldnames]
    if "category" not in fieldnames or "amount" not in fieldnames:
        raise ValueError("CSV must have 'category' and 'amount' columns")

    result = defaultdict(int)
    for row in reader:
        category = row.get("category")
        amount_raw = row.get("amount")
        if category is None or amount_raw is None:
            raise ValueError("Missing category or amount")
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid amount: {amount_raw!r}")
        result[category] += amount

    return dict(result)
