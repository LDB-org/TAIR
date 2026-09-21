"""Parse CSV with header category,amount and sum integer amounts per category."""
import csv
import io


def totals(text):
    """Return a dict mapping category to summed integer amount.

    The CSV must have a header row: category,amount. Quoted commas in category
    names, negative numbers, and Unicode are supported. Empty text or
    header-only input returns {}. An invalid amount raises ValueError.
    """
    result = {}
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}
    if header != ["category", "amount"]:
        raise ValueError("header must be category,amount")
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("each row must have exactly two fields")
        category, amount_str = row
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"invalid amount: {amount_str!r}")
        result[category] = result.get(category, 0) + amount
    return result
