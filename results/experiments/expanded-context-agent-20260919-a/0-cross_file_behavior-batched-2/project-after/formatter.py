def display_name(user):
    name = user.get('name')
    if name is None:
        return 'Unknown'
    name = name.strip()
    return name if name else 'Unknown'
