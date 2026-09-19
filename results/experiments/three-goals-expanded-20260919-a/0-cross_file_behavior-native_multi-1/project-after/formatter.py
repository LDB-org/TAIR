def display_name(user):
    name = user.get('name')
    if name is None:
        return 'Unknown'
    stripped = name.strip()
    if not stripped:
        return 'Unknown'
    return stripped
