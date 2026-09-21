"""Opt-in text tokenization from a pinned, trusted deployment snapshot."""
import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from threading import Lock

_lock = Lock()


@lru_cache(maxsize=2)
def _load(directory, revision):
    root = Path(directory)
    manifest_bytes = (root / 'manifest.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != revision:
        raise ValueError('Local tokenizer manifest revision mismatch')
    manifest = json.loads(manifest_bytes)
    if manifest['format'] != 'tair-deepseek-v4-text-v1':
        raise ValueError('Unsupported local tokenizer format')
    for name in ('tokenizer.json', 'encoding.py'):
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != manifest['files'][name]:
            raise ValueError('Local tokenizer file digest mismatch: ' + name)
    import tokenizers
    if tokenizers.__version__ != manifest['client_tokenizers_version']:
        raise ValueError('Local tokenizer library version mismatch')
    spec = importlib.util.spec_from_file_location('tair_deployment_encoding', root / 'encoding.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tokenizer = tokenizers.Tokenizer.from_file(str(root / 'tokenizer.json'))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer, module.encode_messages


def encode(payload, directory, revision):
    """Return None for unsupported payloads so the original server handles them."""
    if not revision:
        raise ValueError('Local tokenization requires PIJIT_TOKENIZER_REVISION')
    messages = payload.get('messages')
    if messages is not None:
        if (payload.get('add_generation_prompt') is not True
                or payload.get('chat_template_kwargs') != {'thinking': False, 'enable_thinking': False}
                or set(payload) - {'model', 'messages', 'add_generation_prompt', 'chat_template_kwargs'}):
            return None
        allowed = {'role', 'content', 'tool_calls', 'tool_call_id', 'name'}
        if any(set(m) - allowed or m.get('role') not in ('system', 'user', 'assistant', 'tool')
               or not isinstance(m.get('content', ''), (str, type(None))) for m in messages):
            return None
    elif (not isinstance(payload.get('prompt'), str) or payload.get('add_special_tokens') is not False
          or set(payload) - {'model', 'prompt', 'add_special_tokens'}):
        return None
    with _lock:
        tokenizer, render = _load(directory, revision)
    prompt = render(messages, thinking_mode='chat', drop_thinking=True, reasoning_effort=None) if messages is not None else payload['prompt']
    return tokenizer.encode(prompt, add_special_tokens=False).ids
