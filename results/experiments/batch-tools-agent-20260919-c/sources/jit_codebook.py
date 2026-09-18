"""Version-bound learned edits, with typed bindings and exact-task fallback."""
import ast
import copy
import hashlib
import json
import math
import re


def digest(source):
    return hashlib.sha256(source.encode()).hexdigest()


def syntax_digest(source):
    try:
        return digest(ast.dump(ast.parse(source, type_comments=True), include_attributes=False))
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return None


def same_edits(left, right):
    try:
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        return False


def integer_binding(task):
    values = re.findall(r'(?<![\w.])-?\d+(?!\w|\.\d)', task)
    return int(values[0]) if len(values) == 1 else None


class Codebook:
    def __init__(self):
        self.entries = []

    def admit(self, source, task, edits, validated, bound=None, exact_task=False):
        lengths = {'kw': 4, 'arg': 3, 'return_if': 4, 'raise_if': 5, 'catch': 4}
        if (not validated or not isinstance(edits, list) or not 1 <= len(edits) <= 8
                or any(not isinstance(e, list) or not e or not isinstance(e[0], str)
                       or len(e) != lengths.get(e[0]) or not isinstance(e[1], str) for e in edits)):
            return False
        if exact_task:
            return self._append(source, {'edits': copy.deepcopy(edits), 'task': task.strip(),
                                         'description': task, 'kind': 'exact_task'})
        if bound is not None and len(edits) == 1 and same_edits(edits, bound):
            template = copy.deepcopy(edits[0])
            kind = type(template[-1]).__name__
            if template[0] not in ('kw', 'arg') or kind not in ('int', 'float', 'str', 'bool'):
                return False
            template[-1] = {'bind': 'task_value', 'type': kind}
            entry = {'template': template, 'description': task, 'binding_version': 1,
                     'source_ast_sha256': syntax_digest(source)}
            return self._append(source, entry)
        if len(edits) != 1 or edits[0][0] != 'kw' or type(edits[0][-1]) is float:
            return self._append(source, {'edits': copy.deepcopy(edits), 'task': task.strip(),
                                         'description': task, 'kind': 'exact_task'})
        edit = edits[0]
        template = copy.deepcopy(edit)
        description = task
        value = edit[3]
        if type(value) is int and integer_binding(task) == value:
            template[3] = {'bind': 'task_integer'}
            description = re.sub(r'(?<![\w.])-?\d+(?!\w|\.\d)', '{task_integer}', task)
        elif not isinstance(value, (bool, str)) and value is not None:
            return self._append(source, {'edits': copy.deepcopy(edits), 'task': task.strip(),
                                         'description': task, 'kind': 'exact_task'})
        return self._append(source, {'description': description, 'template': template})

    def _append(self, source, entry):
        try:
            json.dumps(entry, allow_nan=False)
        except (ValueError, TypeError):
            return False
        entry.update(source_sha256=digest(source), admission='caller validation; inspect recorded provenance')
        identity = lambda e: json.dumps([e['source_sha256'], e.get('template'), e.get('edits'), e.get('task')], sort_keys=True)
        if any(identity(e) == identity(entry) for e in self.entries):
            return False
        entry['id'] = max((e['id'] for e in self.entries), default=-1) + 1
        self.entries.append(entry)
        return True

    def retrieve(self, source, task, targets, bound=None):
        result = []
        source_hash = digest(source)
        ast_hash = syntax_digest(source) if bound is not None else None
        seen = set()
        for entry in self.entries:
            exact_source = entry['source_sha256'] == source_hash
            equivalent_source = (ast_hash is not None and entry.get('binding_version') == 1
                                 and entry.get('source_ast_sha256') == ast_hash)
            if not exact_source and not equivalent_source:
                continue
            if entry.get('kind') == 'exact_task':
                if entry['task'] != task.strip() or not exact_source:
                    continue
                edits = copy.deepcopy(entry['edits'])
                candidate = {'id': entry['id'], 'description': entry['description'], 'edits': edits,
                             'exact_task': entry['task'], 'source_sha256': source_hash}
            else:
                candidate = self._bind(entry, task, bound)
                if candidate is None:
                    continue
            if any(edit[1] not in targets for edit in candidate['edits']):
                continue
            key = json.dumps(candidate['edits'], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            candidate['source_match'] = 'exact' if exact_source else 'ast_equivalent'
            result.append(candidate)
        return result

    @staticmethod
    def _bind(entry, task, bound):
        edit = copy.deepcopy(entry['template'])
        if entry.get('binding_version') == 1:
            if (not isinstance(edit[-1], dict) or edit[-1].get('bind') != 'task_value'
                    or bound is None or len(bound) != 1 or edit[:-1] != bound[0][:-1]
                    or type(bound[0][-1]).__name__ != edit[-1]['type']):
                return None
            edit[-1] = copy.deepcopy(bound[0][-1])
        elif edit[3] == {'bind': 'task_integer'}:
            number = integer_binding(task)
            if number is None:
                return None
            edit[3] = number
        return {'id': entry['id'], 'description': entry['description'], 'edits': [edit]}


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
