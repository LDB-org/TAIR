from formatter import display_name
def render_users(users):
    names = [display_name(u) for u in users]
    return '\n'.join(sorted(names, key=str.casefold))
