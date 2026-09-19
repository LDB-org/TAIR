import csv


def parse_people(text):
    result = []
    for row in csv.reader(text.splitlines()):
        if not row or not any(cell.strip() for cell in row):
            continue
        if row[0] == 'name':
            continue
        name, age, active = row[0], row[1], row[2]
        result.append({'name': name, 'age': int(age), 'active': active == 'yes'})
    return result
