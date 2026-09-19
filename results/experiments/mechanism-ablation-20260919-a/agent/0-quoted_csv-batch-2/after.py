import csv

def parse_people(text):
    result = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        if not any(row.values()):
            continue
        result.append({'name': row['name'], 'age': int(row['age']), 'active': row['active'] == 'yes'})
    return result
