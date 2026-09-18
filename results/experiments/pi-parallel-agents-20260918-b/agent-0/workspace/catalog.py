import json


def clean_names(names):
    result = []
    seen = set()
    for name in names:
        trimmed = name.strip()
        if trimmed and trimmed not in seen:
            result.append(trimmed)
            seen.add(trimmed)
    return result


if __name__ == '__main__':
    print(json.dumps(clean_names([' Ada ', '', 'Ada', ' Bob']), ensure_ascii=False))
