import csv
import io


def totals(text):
    """Parse CSV with header category,amount and sum integer amounts per category.

    Returns a dict mapping category name to total. Empty text or header-only
    input returns {}. An invalid amount raises ValueError.
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
            raise ValueError(f"Invalid row: {row}")
        category, amount_str = row
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount_str}")
        result[category] = result.get(category, 0) + amount

    return result
