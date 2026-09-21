"""Controlled transient-check failure cases, not a general workload benchmark."""
from expanded_reuse_cases import cases as original_cases


def cases():
    jobs=[]
    for original in original_cases():
        if original['id'] not in ('jsonl_base','jsonl_repeat','jsonl_changed'):
            continue
        checker=('from pathlib import Path\n'
                 'marker=Path(".check-attempts")\n'
                 'previous=marker.read_text() if marker.exists() else ""\n'
                 'marker.write_text(previous+"attempt\\n")\n'
                 'if not previous: raise SystemExit("SIMULATED_TRANSIENT_SETUP_FAILURE: rerun the same check once")\n'
                 +original['check'])
        prompt=(original['prompt']+' For this controlled recovery test, after writing the module run exactly '
                '`python3 check_output.py`. Put that initial write and check in the same batch/plan when supported. '
                'The checker deliberately fails its first invocation to simulate transient setup failure; '
                'on SIMULATED_TRANSIENT_SETUP_FAILURE rerun the same command in a NEW tool call without rewriting '
                'the correct module. Do not combine the first check and retry in one shell command or suppress errors. '
                'Do not edit check_output.py or .check-attempts; only the checker may write the marker. '
                'The supplied checker is sufficient; no additional checks are requested.')
        check=(original['check']+'\nfrom pathlib import Path\n'
               +f'assert Path("check_output.py").read_text()=={checker!r}\n'
               +'assert Path(".check-attempts").read_text()=="attempt\\nattempt\\n"\n')
        jobs.append(dict(original,id='recovery_'+original['id'],group='controlled_recovery',prompt=prompt,
                         files={**original['files'],'check_output.py':checker},check=check))
    return jobs
