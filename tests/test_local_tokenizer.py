import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
import local_tokenizer


@pytest.fixture
def snapshot(tmp_path):
    tokenizers = pytest.importorskip('tokenizers')
    tokenizer = tokenizers.Tokenizer(tokenizers.models.WordLevel({'hello': 0, '[UNK]': 1}, unk_token='[UNK]'))
    tokenizer.save(str(tmp_path / 'tokenizer.json'))
    (tmp_path / 'encoding.py').write_text('def encode_messages(messages, **kwargs):\n    return messages[0]["content"]\n')
    manifest = {'format': 'tair-deepseek-v4-text-v1', 'client_tokenizers_version': tokenizers.__version__,
                'files': {n: hashlib.sha256((tmp_path / n).read_bytes()).hexdigest()
                          for n in ('tokenizer.json', 'encoding.py')}}
    raw = json.dumps(manifest).encode()
    (tmp_path / 'manifest.json').write_bytes(raw)
    return str(tmp_path), hashlib.sha256(raw).hexdigest()


def test_local_text_and_raw_labels(snapshot):
    payload = {'model': '/model', 'messages': [{'role': 'user', 'content': 'hello'}],
               'add_generation_prompt': True, 'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}}
    assert local_tokenizer.encode(payload, *snapshot) == [0]
    assert local_tokenizer.encode({'prompt': 'hello', 'add_special_tokens': False}, *snapshot) == [0]


@pytest.mark.parametrize('filename', ['encoding.py', 'tokenizer.json', 'manifest.json'])
def test_modified_snapshot_rejected_before_execution(snapshot, filename):
    directory, revision = snapshot
    path = Path(directory) / filename
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='mismatch'):
        local_tokenizer.encode({'prompt': 'hello', 'add_special_tokens': False}, directory, revision)


def test_unsupported_messages_use_remote_without_loading_snapshot():
    payload = {'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'x'}}]}],
               'add_generation_prompt': True, 'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}}
    assert local_tokenizer.encode(payload, '/does-not-exist', 'revision') is None
    payload['messages'] = [{'role': 'user', 'content': 'hello'}]
    payload['chat_template_kwargs']['thinking'] = True
    assert local_tokenizer.encode(payload, '/does-not-exist', 'revision') is None


def test_revision_required():
    with pytest.raises(ValueError, match='requires'):
        local_tokenizer.encode({'prompt': 'hello', 'add_special_tokens': False}, '/does-not-exist', None)
