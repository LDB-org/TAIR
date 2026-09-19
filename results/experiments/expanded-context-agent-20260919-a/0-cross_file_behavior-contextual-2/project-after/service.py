from formatter import display_name
def render_users(users):
    return '\n'.join(display_name(u) for u in users)
