import csv


def parse_people(text):
    reader = csv.reader(text.splitlines())
    next(reader, None)  # skip header
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
