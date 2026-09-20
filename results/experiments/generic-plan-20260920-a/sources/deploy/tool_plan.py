"""Generic Pi tool plans: classify a first action or content reuse, then generate.

The existing fused endpoint returns a single plan. All tools execute in Pi, not
in vLLM. Content admission records successful execution, not semantic verification.
"""
import copy
from plan_book import PlanBook


class ToolContentBook(PlanBook):
    """Separate database of reusable text, without Python or task restrictions."""
    @staticmethod
    def validate_source(source):
        if not isinstance(source, str):
            raise ValueError('Reusable content must be text')


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
        reuse = obj(dict(name=dict(const='reuse_write'), arguments=obj(dict(path=dict(type='string')))))
        params = copy.deepcopy(schema(tools))
        params['properties']['steps']['items']['anyOf'].append(reuse)
        options.append(dict(name='plan', description='Reuse immutable write content if fully applicable: '+entry['contract']+
                            '\nCONTENT:\n'+entry['source']+'\nOtherwise generate ordinary steps.', parameters=params))
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
        for step in steps:
            if step['name'] == 'reuse_write':
                step['name'] = 'write'
                step['arguments']['content'] = entry['source']
                reused.append(entry['id'])
    validate(dict(steps=steps), schema(tools))
    return dict(name='plan', arguments=dict(steps=steps)), reused
