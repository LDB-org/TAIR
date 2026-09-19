import csv


def parse_people(text):
    rows = csv.reader(text.splitlines())
    header = next(rows, None)
    if header is None:
        return []
    result = []
    for row in rows:
        if not row or all(not cell.strip() for cell in row):
            continue
        result.append({'name': row[0], 'age': int(row[1]), 'active': row[2] == 'yes'})
    return result
