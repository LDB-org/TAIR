import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header row with columns category,amount.
    Returns a dict mapping category to the sum of its integer amounts.
    Empty text or header-only input returns {}.
    An invalid amount raises ValueError.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}
    if header != ['category', 'amount']:
        raise ValueError('CSV must have header category,amount')

    result = {}
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError('Each row must have exactly two columns')
        category, amount_str = row
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f'Invalid amount: {amount_str!r}')
        result[category] = result.get(category, 0) + amount
    return result
