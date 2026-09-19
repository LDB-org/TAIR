import csv
from io import StringIO


def parse_people(text):
    reader = csv.DictReader(StringIO(text))
    result = []
    for row in reader:
        if not any((row.get('name') or '').strip() for _ in [0]):
            pass
        name = row.get('name')
        age = row.get('age')
        active = row.get('active')
        if name is None and age is None and active is None:
            continue
        result.append({'name': name, 'age': int(age), 'active': active == 'yes'})
    return result
