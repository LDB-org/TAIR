"""Install or roll back a source-hash-guarded experiment in one vLLM container."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main(a):
    import vllm
    root = Path(vllm.__file__).parent
    if a.rollback:
        manifest = json.loads((a.backup/'manifest.json').read_text())
        for rel, hashes in manifest.items():
            target = root/rel
            if hashlib.sha256(target.read_bytes()).hexdigest() != hashes['patched']:
                raise RuntimeError('Refusing to overwrite changed file: '+rel)
        for rel in manifest:
            shutil.copyfile(a.backup/rel, root/rel)
        return
    assert vllm.__version__ == '0.28.1rc1.dev137+g5ab628dd1'
    changes = {
        'v1/worker/gpu_model_runner.py': [('        # Sample the next token and get logprobs if needed.\n',
            '        from vllm.openjev_direct_tools import classify\n'
            '        direct = classify(self, logits, spec_decode_metadata)\n'
            '        if direct is not None:\n            return direct\n'
            '        # Sample the next token and get logprobs if needed.\n')],
        'v1/request.py': [('    max_tokens: int\n    arrival_time: float\n',
            '    max_tokens: int\n    structured_output_request: object\n    arrival_time: float\n'),
            ('            max_tokens=request.max_tokens,\n',
             '            max_tokens=request.max_tokens,\n            structured_output_request=request.structured_output_request,\n')],
        'v1/core/sched/scheduler.py': [('        session.status = RequestStatus.WAITING\n',
            '        session.status = RequestStatus.WAITING\n'
            '        from vllm.openjev_direct_tools import resumed\n'
            '        resumed(self, session, update)\n')],
        'entrypoints/launchers/api_server/routers.py': [('        register_generate_api_routers(app)\n',
            '        register_generate_api_routers(app)\n'
            '        from vllm.openjev_direct_tools import attach_router\n'
            '        attach_router(app)\n')],
    }
    if a.v2_only:
        changes = {'v1/worker/gpu/sample/sampler.py': [
            ('        self.sampling_states.add_request(req_idx, sampling_params)\n',
             '        if not hasattr(self, "_openjev_candidates"):\n'
             '            self._openjev_candidates = {}\n'
             '        self._openjev_candidates.pop(req_idx, None)\n'
             '        if (sampling_params.extra_args or {}).get("openjev_direct_classify"):\n'
             '            self._openjev_candidates[req_idx] = sampling_params.logprob_token_ids\n'
             '        self.sampling_states.add_request(req_idx, sampling_params)\n'),
            ('        processed_logits = self.apply_sampling_params(\n',
             '        from vllm.openjev_direct_tools import classify_v2\n'
             '        direct = classify_v2(self, logits, expanded_idx_mapping, idx_mapping,\n'
             '            idx_mapping_np, pos, input_ids, expanded_local_pos, return_logprobs)\n'
             '        if direct is not None:\n            return direct\n'
             '        processed_logits = self.apply_sampling_params(\n')
        ]}
    if a.streaming_slots_only:
        changes = {'v1/core/sched/scheduler.py': [
            ('        if request.streaming_queue:\n',
             '        from vllm.openjev_direct_tools import paused\n'
             '        paused(self, request)\n'
             '        if request.streaming_queue:\n')
        ]}
    prepared = {}
    for rel, replacements in changes.items():
        original = (root/rel).read_text()
        modified = original
        for old, new in replacements:
            assert modified.count(old) == 1, (rel, old)
            modified = modified.replace(old, new)
        compile(modified, rel, 'exec')
        prepared[rel] = (original, modified)
    compile(a.module.read_text(), str(a.module), 'exec')
    a.backup.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for rel, (original, modified) in prepared.items():
        target = a.backup/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(original)
        manifest[rel] = {'original': hashlib.sha256(original.encode()).hexdigest(),
                         'patched': hashlib.sha256(modified.encode()).hexdigest()}
    (a.backup/'manifest.json').write_text(json.dumps(manifest, indent=2))
    shutil.copyfile(a.module, root/'openjev_direct_tools.py')
    for rel, (_, modified) in prepared.items():
        (root/rel).write_text(modified)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup', required=True, type=Path)
    p.add_argument('--module', type=Path)
    p.add_argument('--rollback', action='store_true')
    p.add_argument('--v2-only', action='store_true')
    p.add_argument('--streaming-slots-only', action='store_true')
    main(p.parse_args())
