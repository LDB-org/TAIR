def parse_people(text):
    return [{'name': parts[0], 'age': int(parts[1]), 'active': parts[2]=='yes'}
            for line in text.splitlines()[1:] if line.strip()
            for parts in [line.split(',')]]
