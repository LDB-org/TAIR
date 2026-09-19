from formatter import display_name
def render_users(users):
    names = [display_name(u) for u in users]
    ordered = sorted(range(len(names)), key=lambda i: names[i].casefold())
    return '\n'.join(names[i] for i in ordered)
