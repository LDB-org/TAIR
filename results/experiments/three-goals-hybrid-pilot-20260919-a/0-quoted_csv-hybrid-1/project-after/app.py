import csv
import io


def parse_people(text):
    reader = csv.DictReader(io.StringIO(text))
    people = []
    for row in reader:
        if not any((value or '').strip() for value in row.values()):
            continue
        people.append({
            'name': row['name'],
            'age': int(row['age']),
            'active': row['active'] == 'yes',
        })
    return people
