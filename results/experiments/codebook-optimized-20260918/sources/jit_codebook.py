"""Small version-bound codebook for validated single-keyword edit templates."""
import copy
import hashlib
import json
import math
import re


def digest(source):
    return hashlib.sha256(source.encode()).hexdigest()


def integer_binding(task):
    values = re.findall(r'(?<![\w.])-?\d+(?!\w|\.\d)', task)
    return int(values[0]) if len(values) == 1 else None


class Codebook:
    def __init__(self):
        self.entries = []

    def admit(self, source, task, edits, validated):
        if not validated or len(edits) != 1:
            return False
        edit = edits[0]
        if not isinstance(edit, list) or len(edit) != 4 or edit[0] != 'kw':
            return False
        template = copy.deepcopy(edit)
        description = task
        value = edit[3]
        if type(value) is int and integer_binding(task) == value:
            template[3] = {'bind': 'task_integer'}
            description = re.sub(r'(?<![\w.])-?\d+(?!\w|\.\d)', '{task_integer}', task)
        elif not isinstance(value, (bool, str)) and value is not None:
            return False
        entry = {'source_sha256': digest(source), 'description': description, 'template': template,
                 'admission': 'passed benchmark task oracle and 17 regressions; not generally verified'}
        if any(e['source_sha256'] == entry['source_sha256'] and e['template'] == template for e in self.entries):
            return False
        entry['id'] = len(self.entries)
        self.entries.append(entry)
        return True

    def retrieve(self, source, task, targets):
        result = []
        for entry in self.entries:
            if entry['source_sha256'] != digest(source) or entry['template'][1] not in targets:
                continue
            edit = copy.deepcopy(entry['template'])
            if edit[3] == {'bind': 'task_integer'}:
                number = integer_binding(task)
                if number is None:
                    continue
                edit[3] = number
            result.append({'id': entry['id'], 'description': entry['description'], 'edits': [edit]})
        return result


def confidence(scores, selected):
    weights = [math.exp(v-max(scores)) for v in scores]
    probability = weights[selected]/sum(weights)
    other = max(v for i,v in enumerate(scores) if i != selected)
    return {'conditional_probability': probability, 'margin': scores[selected]-other,
            'candidate_mass': sum(math.exp(v) for v in scores)}


class ExactCodebook:
    """Learn typed edits for exact task/path/source replay, without model selection."""
    version = 1

    def __init__(self, entries=None):
        self.entries = entries or []

    def retrieve(self, source, task, path):
        matches = [e for e in self.entries if e.get('version') == self.version
                   and e.get('source_sha256') == digest(source)
                   and e.get('task') == task.strip() and e.get('path') == str(path)]
        return copy.deepcopy(matches[0]) if len(matches) == 1 else None

    def admit(self, source, task, path, edits, updated, validation):
        if not validation or source == updated or not edits or self.retrieve(source, task, path):
            return False
        self.entries.append({'version': self.version, 'source_sha256': digest(source),
                             'updated_sha256': digest(updated), 'task': task.strip(), 'path': str(path),
                             'edits': copy.deepcopy(edits), 'validation': validation})
        self.entries = self.entries[-256:]
        return True
