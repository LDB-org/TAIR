"""Generic Pi tool plans: classify a first action or content reuse, then generate.

The existing fused endpoint returns a single plan. All tools execute in Pi, not
in vLLM. Content admission records successful execution, not semantic verification.
"""
import copy
import difflib
import json
import re
import plan_template
from plan_book import PlanBook


class ToolContentBook(PlanBook):
    """Separate database of reusable text, without Python or task restrictions."""
    def candidates(self, task, contracts, limit=15):
        if not 0 <= limit <= 15:
            raise ValueError('At most fifteen candidates supported')
        unique = {}
        for entry in super().candidates(task, contracts, limit=15 if limit else 0):
            unique.setdefault(entry['source'], entry)
        return list(unique.values())[:limit]

    @staticmethod
    def validate_source(source):
        if not isinstance(source, str):
            raise ValueError('Reusable content must be text')


def compatible_payload(entry, task):
    """Conservative eligibility, not semantic validation of natural-language tasks.

    If fenced content is supplied, reuse only identical content. Example-only
    fences can cause safe misses; never guess that a changed literal is optional.
    """
    blocks = re.findall(r'^```[^\n]*\n(.*?)^```[ \t]*$', task, re.MULTILINE | re.DOTALL)
    if not blocks:
        return True
    content = json.loads(entry['source'])['content'] if entry.get('plan_template') else entry['source']
    return content in blocks


def request_delta(previous, current):
    """Expose changed requirements without asking another model to summarize them."""
    lines = difflib.unified_diff(previous.splitlines(), current.splitlines(),
                                 fromfile='historical request', tofile='CURRENT request', n=1)
    delta = '\n'.join(lines)
    if len(delta) > 6000:
        delta = delta[:3000] + '\n[diff middle omitted; use the full current request]\n' + delta[-3000:]
    return delta or '(same request text)'


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def step_schema(tool):
    return obj(dict(name=dict(const=tool['name']), arguments=tool['parameters']))


def schema(tools):
    return obj(dict(steps=dict(type='array', minItems=1, maxItems=8,
                               items=dict(anyOf=[step_schema(tool) for tool in tools]))))


def decoder_schema(value):
    # Deployed xgrammar escape bug with minLength; validate original schema later.
    if isinstance(value, dict):
        return {k:decoder_schema(v) for k,v in value.items() if k != 'minLength'}
    if isinstance(value, list):
        return [decoder_schema(v) for v in value]
    return value


def branches(tools, candidates):
    if len(tools) + len(candidates) + 1 > 16:
        raise ValueError('Too many classification branches')
    rest = dict(type='array', minItems=0, maxItems=7, items=schema(tools)['properties']['steps']['items'])
    options = []
    for tool in tools:
        options.append(dict(name='plan', description='First action '+tool['name']+': '+tool['description'],
                            parameters=obj(dict(first=tool['parameters'], rest=rest))))
    for entry in candidates:
        # Full generation remains legal if rechecking the chosen entry rejects it.
        reuse_name = 'reuse_plan' if entry.get('plan_template') else 'reuse_write'
        reuse = obj(dict(name=dict(const=reuse_name), arguments=obj(dict(path=dict(type='string')))))
        params = copy.deepcopy(schema(tools))
        params['properties']['steps']['items']['anyOf'].append(reuse)
        description = ('Replay stored write + python3 -m py_compile as ONE template. Bind the current destination. '
                       'The compile check is already included and executes again. Do not add a duplicate check. '
                       if entry.get('plan_template') else 'Write the following stored content to the destination requested NOW. ')
        options.append(dict(name='plan', description=description +
                            'The destination is a parameter, not part of the stored content. '
                            'Choose this when the source satisfies the requested behavior and constraints; '
                            'new filenames do not require new source. Checks can follow in the same plan. '
                            '\nHISTORICAL BEHAVIOR CONTRACT (old destination is not binding):\n'+entry['contract']+'\nCONTENT:\n'+entry['source']+'\nChanged code or extra operations must not be discarded. If incompatible, generate ordinary steps.', parameters=params))
    options.append(dict(name='plan', description='Reply or ask clarification; no tool action needed now.',
                        parameters=obj(dict(content=dict(type='string')))))
    return options


def decode(response, tools, candidates, options):
    from jsonschema import validate
    index = response['decision']['index']
    if not 0 <= index < len(options) or not response.get('same_engine_session') or response['finish_reason'] != 'stop':
        raise ValueError('Incomplete generic plan engine decision')
    if response['call']['name'] != 'plan' or response['classification_control_records'] != 1:
        raise ValueError('Expected one classified plan')
    arguments = response['call']['arguments']
    validate(arguments, options[index]['parameters'])
    if index == len(options)-1:
        return dict(name='reply_user', arguments=arguments), []
    reused = []
    if index < len(tools):
        steps = [dict(name=tools[index]['name'], arguments=arguments['first']), *arguments['rest']]
    else:
        steps = copy.deepcopy(arguments['steps'])
        entry = candidates[index-len(tools)]
        expanded = []
        for step in steps:
            if step['name'] == 'reuse_plan':
                expanded.extend(plan_template.bind(entry['source'], step['arguments']['path']))
                reused.append(entry['id'])
                continue
            if step['name'] == 'reuse_write':
                step['name'] = 'write'
                step['arguments']['content'] = entry['source']
                reused.append(entry['id'])
            expanded.append(step)
        steps = expanded
    validate(dict(steps=steps), schema(tools))
    return dict(name='plan', arguments=dict(steps=steps)), reused


def continuation(index, tools, candidates, option):
    import json
    if index < len(tools):
        instruction = ('Selected FIRST action is '+tools[index]['name']+'. Put its arguments in first. '
                       'Put all other currently determined native tool calls in rest, or [] when results are needed first. ')
    elif index < len(tools)+len(candidates):
        entry = candidates[index-len(tools)]
        instruction = ('Selected content entry '+entry['id']+'. Recheck its bytes against the current request. '
                       'If applicable, emit name=reuse_write with arguments={path: destination}; '
                       'the runtime supplies the entire stored content. Do NOT regenerate matching content using write. '
                       'Other steps such as bash checks use their normal names and arguments. '
                       'If the selected content is incompatible, abandon reuse and emit ordinary steps instead. ')
        if entry.get('plan_template'):
            instruction = ('Selected plan template '+entry['id']+'. Recheck ALL current constraints. '
                           'If applicable emit one reuse_plan step with arguments={path: destination}. '
                           'It expands to BOTH write and python3 -m py_compile, so do not repeat either. '
                           'If incompatible emit ordinary steps with new source and checks instead. ')
    else:
        instruction = 'Reply to the user based on the actual execution results, or ask for missing information. '
    if len(tools) <= index < len(tools)+len(candidates):
        instruction += ('Compare the CURRENT request changes against the stored content BEFORE reusing. '
                        'A template covers only its listed steps: append any new required operations, '
                        'or generate a new plan. Never omit additions just because the old plan passed.\n'
                        + candidates[index-len(tools)].get('request_delta', '') + '\n')
    instruction += 'Each individual subtool argument object has a budget of 2048 tokens; the whole plan may use up to eight such calls. '
    return instruction+'Return ONLY JSON matching this schema: '+json.dumps(option['parameters'],ensure_ascii=False)
