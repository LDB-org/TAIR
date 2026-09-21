"""Explicit fixture workflow checks, separate from output artifact correctness."""
from pathlib import Path
import shlex


def validate_workflow(job, events, project):
    requirements=job.get('workflow',{})
    checks={}
    expected=requirements.get('first_command')
    if expected is not None:
        first=next((event for event in events if event.get('type')=='tool_execution_start'),{})
        args=first.get('args') or {}
        steps=args.get('steps') or []
        step=steps[0] if first.get('toolName')=='plan' and steps else dict(name=first.get('toolName'),arguments=args)
        command=step.get('arguments',{}).get('command','')
        try:tokens=shlex.split(command)
        except (ValueError,TypeError):tokens=[]
        cwd_matches=True
        if len(tokens)>=3 and tokens[0]=='cd' and tokens[2]=='&&':
            cwd_matches=(project/tokens[1]).resolve()==project.resolve()
            tokens=tokens[3:]
        if tokens[:2]==['command','--']:tokens=tokens[2:]
        checks['requested_command_first']=step.get('name')=='bash' and cwd_matches and tokens==expected
    for name in requirements.get('unchanged_files',[]):
        path=project/name
        try:unchanged=path.resolve().is_relative_to(project.resolve()) and path.read_bytes()==job['files'][name].encode()
        except (OSError,KeyError):unchanged=False
        checks['unchanged:'+name]=unchanged
    return dict(passed=all(checks.values()),checks=checks)


def apply_workflow_result(row, validation):
    row['artifact_passed']=row['validation']['passed']
    row['workflow_validation']=validation
    row['passed']=row['passed'] and validation['passed']
