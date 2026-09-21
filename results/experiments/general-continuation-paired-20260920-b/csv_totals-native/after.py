"""Parse a CSV with header 'category,amount' and sum integer amounts per category."""

import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header row of 'category,amount'. Amounts are parsed
    as integers (negative numbers are supported). Category names may contain
    quoted commas and Unicode characters.

    Returns a dict mapping category name to the summed integer amount.
    Empty text or header-only input returns {}.
    Raises ValueError if an amount is not a valid integer.
    """
    if not text:
        return {}

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}

    if header != ["category", "amount"]:
        raise ValueError("CSV must have header 'category,amount'")

    result = {}
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError(f"Expected 2 columns, got {len(row)}: {row!r}")
        category, amount_str = row
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount_str!r}")
        result[category] = result.get(category, 0) + amount

    return result
