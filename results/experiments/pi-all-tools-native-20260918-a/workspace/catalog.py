import json


def clean_names(names):
    result = []
    seen = set()
    for name in names:
        cleaned = name.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


if __name__ == '__main__':
    print(json.dumps(clean_names([' Ada ', '', 'Ada', ' Bob']), ensure_ascii=False))
