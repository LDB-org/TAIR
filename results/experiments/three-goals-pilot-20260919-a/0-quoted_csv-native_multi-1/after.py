import csv


def parse_people(text):
    reader = csv.reader(text.splitlines())
    header = next(reader, None)
    if header is None:
        return []
    result = []
    for row in reader:
        if not row or not any(field.strip() for field in row):
            continue
        name, age, active = row
        result.append({
            'name': name,
            'age': int(age),
            'active': active == 'yes',
        })
    return result
