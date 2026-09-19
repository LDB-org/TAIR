"""Experimental native tool-calling planner; compact edit reuse remains a separate tool."""
import hashlib
import json
import uuid


def text_content(content):
    if isinstance(content, str):
        return content
    return '\n'.join(block['text'] for block in content or []
                     if isinstance(block, dict) and block.get('type') == 'text')


def messages_for(context, policy=''):
    system = context.get('systemPrompt', '')
    if policy:
        system += '\n' + policy
    messages = [{'role': 'system', 'content': system}]
    for source in context['messages']:
        role = source['role']
        text = text_content(source.get('content'))
        if role == 'toolResult':
            messages.append({'role': 'tool', 'tool_call_id': source['toolCallId'], 'content': text})
        elif role in ('user', 'assistant'):
            message = {'role': role, 'content': text}
            calls = [{'id': block['id'], 'type': 'function', 'function': {
                'name': block['name'], 'arguments': json.dumps(block['arguments'], ensure_ascii=False)}}
                for block in source.get('content', []) if isinstance(block, dict) and block.get('type') == 'toolCall']
            if calls and role == 'assistant':
                message['tool_calls'] = calls
            messages.append(message)
    return messages


def chat(payload, post, model, policy='', workspace_cache=False, cache_namespace=''):
    context = payload['context']
    tools = [{key: t[key] for key in ('name', 'description', 'parameters')} for t in context.get('tools', [])]
    identity = json.dumps([payload.get('cwd'), model, cache_namespace])
    salt = hashlib.sha256(identity.encode()).hexdigest() if workspace_cache and payload.get('cwd') else uuid.uuid4().hex
    response = post('/v1/chat/completions', {
        'model': model, 'messages': messages_for(context, policy),
        'tools': [{'type': 'function', 'function': tool} for tool in tools],
        'temperature': 0, 'max_tokens': 2048, 'parallel_tool_calls': True,
        'cache_salt': salt,
        'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})
    choice = response['choices'][0]
    if choice['finish_reason'] not in ('stop', 'tool_calls'):
        raise ValueError('Native planner did not finish: ' + str(choice['finish_reason']))
    message, usage = choice['message'], response['usage']
    calls = []
    for item in message.get('tool_calls') or []:
        function = item['function']
        name, arguments = function['name'], json.loads(function['arguments'])
        # Pi validates names and arguments during execution, preserving ordinary
        # tool-error recovery instead of aborting the provider response here.
        calls.append({'name': name, 'arguments': arguments})
    result = {'request_id': response['id'], 'input_tokens': usage['prompt_tokens'],
              'generated_argument_tokens': usage['completion_tokens'], 'classification_control_records': 0}
    if calls:
        return {**result, 'call': calls[0], 'calls': calls}
    if not message.get('content'):
        raise ValueError('Native planner returned neither tools nor an answer')
    return {**result, 'call': {'name': 'reply_user', 'arguments': {'content': message['content']}}}
