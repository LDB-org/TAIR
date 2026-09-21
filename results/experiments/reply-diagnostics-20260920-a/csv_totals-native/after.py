"""Parse CSV with header category,amount and sum integer amounts per category."""

import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header row with columns ``category`` and ``amount``.
    Amounts are parsed as integers (negative numbers are supported). Category
    names may contain quoted commas and Unicode characters.

    Returns a dict mapping category name to the summed integer amount.
    Empty text or header-only input returns ``{}``. An invalid amount raises
    ``ValueError``.
    """
    if not text:
        return {}

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return {}

    result = {}
    for row in reader:
        category = row.get("category")
        amount_raw = row.get("amount")
        if amount_raw is None:
            raise ValueError("missing amount for category: %r" % (category,))
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            raise ValueError("invalid amount: %r" % (amount_raw,))
        result[category] = result.get(category, 0) + amount

    return result
