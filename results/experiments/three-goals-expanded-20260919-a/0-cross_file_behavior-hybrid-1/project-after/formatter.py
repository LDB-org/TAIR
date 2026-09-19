def display_name(user):
    name = user.get('name')
    if name is None:
        return 'Unknown'
    name = name.strip()
    if not name:
        return 'Unknown'
    return name
