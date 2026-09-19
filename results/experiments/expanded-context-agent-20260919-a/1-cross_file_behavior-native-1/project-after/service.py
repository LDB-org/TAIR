from formatter import display_name
def render_users(users):
    names = [display_name(u) for u in users]
    names.sort(key=str.casefold)
    return '\n'.join(names)
