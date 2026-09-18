import json


def clean_names(names):
    cleaned = []
    seen = set()
    for name in names:
        trimmed = name.strip()
        if trimmed and trimmed not in seen:
            cleaned.append(trimmed)
            seen.add(trimmed)
    return cleaned


if __name__ == '__main__':
    print(json.dumps(clean_names([' Ada ', '', 'Ada', ' Bob']), ensure_ascii=False))
