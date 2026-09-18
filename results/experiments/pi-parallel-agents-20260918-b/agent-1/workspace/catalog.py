import json


def clean_names(names):
    return [name.strip() for name in names]


if __name__ == '__main__':
    print(json.dumps(clean_names([' Ada ', '', 'Ada', ' Bob']), ensure_ascii=False))
