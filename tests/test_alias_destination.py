"""Compact aliases must retain argparse Namespace fields, or fall back before writing."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
import compact_structural_protocol as compact
import schema_actions


@pytest.mark.parametrize('options,alias', [
    ('"-l", "--lines"', '--context-lines'),
    ('"-l", "--lines", dest=None', '--context-lines'),
    ('"-l"', '-C'),
    ('"-l"', '--lines'),
])
def test_alias_changing_implicit_destination_is_rejected(options, alias):
    source = f'import argparse\np=argparse.ArgumentParser()\np.add_argument({options}, type=int, default=3)\n'
    target = '-l'
    raw = json.dumps([['arg', target, alias]], separators=(',', ':'))
    with pytest.raises(ValueError, match='destination'):
        compact.typed_decode(source, compact.base.digest(source), raw, 'stop')
    if '--lines' in options:
        assert not schema_actions.can_route(source, f'Add alias {alias} to --lines.')


@pytest.mark.parametrize('options,alias', [
    ('"-l", "--lines"', '-C'),
    ('"-l", "--lines", dest="lines"', '--context-lines'),
])
def test_safe_alias_preserves_existing_and_new_cli_values(options, alias):
    source = f'import argparse\np=argparse.ArgumentParser()\np.add_argument({options}, type=int, default=3)\n'
    raw = json.dumps([['arg', '-l', alias]], separators=(',', ':'))
    result = compact.typed_decode(source, compact.base.digest(source), raw, 'stop')
    ns = {}; exec(result, ns)
    for option in ('-l', '--lines', alias):
        assert vars(ns['p'].parse_args([option, '7'])) == {'lines': 7}
    assert vars(ns['p'].parse_args([])) == {'lines': 3}
