import csv


def parse_people(text):
    rows = csv.reader(text.splitlines())
    header = next(rows, None)
    if header is None:
        return []
    result = []
    for row in rows:
        if not row or not any(cell.strip() for cell in row):
            continue
        name, age, active = row
        result.append({'name': name, 'age': int(age), 'active': active == 'yes'})
    return result
