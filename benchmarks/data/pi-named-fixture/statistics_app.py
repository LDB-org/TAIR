import json


def summarize_numbers(values):
    return {'count': len(values), 'total': 0, 'min': None, 'max': None}


if __name__ == '__main__':
    print(json.dumps(summarize_numbers([3, -1, 3, 0.5])))
