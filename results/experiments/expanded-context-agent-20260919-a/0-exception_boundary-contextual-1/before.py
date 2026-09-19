import json
def load_record(path):
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except Exception:
        return {}
