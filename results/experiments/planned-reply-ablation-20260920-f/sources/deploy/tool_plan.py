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
    old, new = previous.splitlines(), current.splitlines()
    lines = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for group in matcher.get_grouped_opcodes(1):
        lines.append('@@ changed requirements @@')
        for tag, i, j, k, end in group:
            if tag == 'equal':
                lines.extend(' ' + line for line in old[i:j])
            if tag in ('delete', 'replace'):
                lines.extend('-' + line for line in old[i:j])
            if tag in ('insert', 'replace'):
                lines.extend('+' + line for line in new[k:end])
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


def contract_changes(previous, current):
    """Highlight nearby edits for selection, never decide semantic eligibility."""
    old,new=previous.split(),current.split()
    matcher=difflib.SequenceMatcher(None,old,new,autojunk=False)
    if matcher.ratio()<0.6:
        return ''
    lines=[]
    for group in matcher.get_grouped_opcodes(2):
        for tag,i,j,k,end in group:
            if tag=='equal': lines.append(' '+' '.join(old[i:j]))
            if tag in ('delete','replace'): lines.append('-'+' '.join(old[i:j]))
            if tag in ('insert','replace'): lines.append('+'+' '.join(new[k:end]))
    text='\n'.join(lines)
    return text if len(text)<=1000 else text[:500]+'\n[changes omitted; read full current request]\n'+text[-500:]


def branches(tools, candidates, success_reply=False):
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
                            '\nHISTORICAL BEHAVIOR CONTRACT (old destination is not binding):\n'+entry['contract']+
                            '\nCONTENT:\n'+entry['source']+
                            '\nCURRENT REQUIREMENT CHANGES (full request takes precedence):\n'+entry.get('contract_changes','')+
                            '\nChanged code or extra operations must not be discarded. If incompatible, generate ordinary steps.', parameters=params))
    options.append(dict(name='plan', description='General continuation: generate a native action plan, or reply when finished or clarification is required.',
                        parameters=dict(anyOf=[schema(tools), obj(dict(content=dict(type='string')))])))
    for option in options[:-1]:
        option['parameters'] = dict(anyOf=[option['parameters'], obj(dict(content=dict(type='string')))])
    if success_reply:
        for option in options:
            properties = option['parameters']['anyOf'][0]['properties']
            key = 'steps' if 'steps' in properties else 'rest'
            sequence = copy.deepcopy(properties[key])
            properties[key] = sequence
            # The deployed per-tool budget accepts only first/rest or steps envelopes.
            reply = obj(dict(content=dict(type='string', maxLength=600)))
            reply['properties']['expected_outputs'] = dict(type='array', maxItems=8, items=obj(dict(
                step=dict(type='integer', minimum=0, maximum=7), text=dict(type='string', maxLength=600))))
            sequence['items']['anyOf'].append(obj(dict(name=dict(const='on_success_reply'), arguments=reply)))
    return options


def split_success_reply(arguments):
    arguments = copy.deepcopy(arguments)
    steps = arguments.get('steps', arguments.get('rest', []))
    replies = [index for index, step in enumerate(steps) if step['name']=='on_success_reply']
    if not replies:
        return arguments, None
    if replies != [len(steps)-1]:
        raise ValueError('Conditional reply must occur once at the end of a plan')
    reply = steps.pop()['arguments']
    return arguments, reply


def recovery_option(option):
    """A short action purpose precedes each repair, within the existing plan."""
    option=copy.deepcopy(option)
    for step in option['parameters']['anyOf'][0]['properties']['steps']['items']['anyOf']:
        step['properties']={'purpose':dict(type='string',maxLength=240), **step['properties']}
        step['required']=['purpose',*step['required']]
    return option


def decode(response, tools, candidates, options):
    from jsonschema import validate
    index = response['decision']['index']
    if not 0 <= index < len(options) or not response.get('same_engine_session') or response['finish_reason'] != 'stop':
        raise ValueError('Incomplete generic plan engine decision')
    if response['call']['name'] != 'plan' or response['classification_control_records'] != 1:
        raise ValueError('Expected one classified plan')
    arguments = response['call']['arguments']
    validate(arguments, options[index]['parameters'])
    if 'content' in arguments:
        return dict(name='reply_user', arguments=arguments), []
    arguments, _ = split_success_reply(arguments)
    if index == len(options)-1:
        clean=dict(steps=[dict(name=s['name'],arguments=s['arguments']) for s in arguments['steps']])
        validate(clean,schema(tools))
        return dict(name='plan', arguments=clean), []
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


def continuation(index, tools, candidates, option, success_reply=False):
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
        instruction = ('Continue the user task. If any actionable work remains, return steps containing actual native tool calls. '
                       'For an unresolved failed check, inspect or fix the cause and run the corrected check; do not merely promise to do so. '
                       'Once the corrected check succeeds and the requested work is complete, finish. '
                       'Return content only for a completed task, a conversational answer, necessary clarification, '
                       'or an honest blocker that cannot be resolved with the available tools. '
                       'A description of planned work is not execution. The schema below is a format, not answer content. ')
    if len(tools) <= index < len(tools)+len(candidates):
        instruction += ('Compare the CURRENT request changes against the stored content BEFORE reusing. '
                        'A template covers only its listed steps: append any new required operations, '
                        'or generate a new plan. Never omit additions just because the old plan passed.\n'
                        + candidates[index-len(tools)].get('request_delta', '') + '\n')
    instruction = ('Re-evaluate the latest execution results before acting. The classification is a proposal, not an obligation to execute. '
                   'If the requested work and relevant checks are already complete, return content with a concise final answer. '
                   'Do not rerun successful checks without a changed file or unresolved requirement. '
                   'If blocked or clarification is necessary, explain it in content. Otherwise: ')+instruction
    instruction += 'Each individual subtool argument object has a budget of 2048 tokens; the whole plan may use up to eight such calls. '
    if success_reply:
        instruction += ('Every action plan MUST end with exactly one completion decision: '
                        '{"name":"on_success_reply","arguments":{"content":"..."}} as the LAST item in rest or steps. '
                        'Use an EMPTY content string when another model turn is needed after execution. '
                        'When this plan contains ALL remaining work and checks, fill content with the concise final answer. '
                        'The executor withholds this answer until all operations succeed and there is no new output to interpret. '
                        'This is conditional completion, not an early success claim. '
                        'For read/search or unresolved results use empty content. '
                        'Respect the user\'s explicit operation order, including checks requested before inspection or editing. '
                        'If a bash check will print a KNOWN fixed success receipt, include expected_outputs in the completion arguments: '
                        '[{"step": zero-based executed step index, "text": exact expected combined output including newlines}]. '
                        'Only declare outputs known before execution, never guess unseen data. The executor compares exact text '
                        'and returns any mismatch to the model. No regex or substring matching. '
                        'Do not omit checks or suppress command output to qualify. ')
    return instruction+'Return ONLY JSON matching this schema: '+json.dumps(option['parameters'],ensure_ascii=False)
