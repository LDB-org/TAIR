"""Authored, frozen-before-run behavior contracts; hidden checks stay outside workspace."""
import json

SUFFIX = (' Use only the standard library / built-in modules. Run small relevant checks before finishing. '
          'Do not install packages, use the network, or access files outside this workspace except your own temporary test files. '
          'Do not inspect external benchmark files. Finish with a short summary.')


def cases():
    jobs=[]
    for phase in ['base','repeat','changed']:
        filename=f'jsonl_{phase}.py'
        changed=phase=='changed'
        prompt=(f'Create {filename} providing parse_jsonl(text). Return a list of decoded JSON values, in line order. '
                'Skip whitespace-only lines. Handle Unicode, CRLF and a final line without a newline. '
                'Malformed nonblank JSON lines must raise ValueError. No import-time I/O. '+
                ('Reject duplicate object keys at any nesting depth with ValueError.' if changed else
                 'Duplicate object keys follow standard json.loads behavior: the last value wins.'))
        check=f'''from {filename[:-3]} import parse_jsonl
assert parse_jsonl('  \\r\\n{{"x":"中文"}}\\r\\n[1,null]\\ntrue')==[{{'x':'中文'}},[1,None],True]
assert parse_jsonl('')==[]
try:parse_jsonl('{{bad}}')
except ValueError:pass
else:raise AssertionError('malformed JSON accepted')
'''
        if changed:
            check+='''for text in ['{"x":1,"x":2}', '{"outer":{"x":1,"x":2}}']:
 try:parse_jsonl(text)
 except ValueError:pass
 else:raise AssertionError('duplicate keys accepted')
'''
        else:check+='assert parse_jsonl(\'{"x":1,"x":2}\')==[{"x":2}]\n'
        jobs.append(dict(id='jsonl_'+phase,group='jsonl',phase=phase,primary_file=filename,files={filename:''},prompt=prompt+SUFFIX,check=check))
    for phase in ['base','repeat','changed']:
        filename=f'unique_{phase}.mjs';changed=phase=='changed'
        prompt=(f'Create {filename} exporting named function uniqueStrings(values). Input is an array of strings. '
                'Return a new array retaining the first occurrence of each distinct string in original order, without mutating the input. '
                'Keep original spelling in output. Do not trim whitespace. '+
                ('Deduplicate using s.toLowerCase() as the key; ASCII case differences must be ignored.' if changed else
                 'Deduplication is case-sensitive; upper and lower case remain distinct.'))
        expected=['A','a',' B ','b','中文',''] if not changed else ['A',' B ','b','中文','']
        script=f'''import assert from 'node:assert/strict'; import {{uniqueStrings}} from './{filename}';
const input=['A','a','A',' B ','b','中文','中文','','']; const copy=[...input];
const result=uniqueStrings(input);assert.deepEqual(result,{json.dumps(expected,ensure_ascii=False)});
assert.deepEqual(input,copy);assert.notEqual(result,input);assert.deepEqual(uniqueStrings([]),[]);'''
        check='import subprocess\np=subprocess.run(["node","--input-type=module","-e",'+repr(script)+'],capture_output=True,text=True,timeout=5)\nassert p.returncode==0,p.stderr\n'
        jobs.append(dict(id='unique_'+phase,group='unique',phase=phase,primary_file=filename,files={filename:''},prompt=prompt+SUFFIX,check=check))
    for phase in ['base','repeat','changed']:
        filename=f'totals_{phase}.sql';changed=phase=='changed'
        prompt=(f'Write {filename} containing a single SQLite SELECT statement, without Markdown or schema changes. '
                'Table events(user_id TEXT NOT NULL, amount INTEGER NOT NULL, status TEXT NOT NULL). '
                'Return user_id and SUM(amount) AS total, considering only status=\'posted\', grouped by user_id and ordered by user_id ascending. '
                'Amounts can be negative or zero. '+('Return only groups whose total is strictly greater than zero.' if changed else
                'Include groups whose total is zero or negative.'))
        expected=[('a',3)] if changed else [('a',3),('b',0),('c',-2)]
        check=f'''import sqlite3
from pathlib import Path
c=sqlite3.connect(':memory:');c.execute('CREATE TABLE events(user_id TEXT NOT NULL,amount INTEGER NOT NULL,status TEXT NOT NULL)')
c.executemany('INSERT INTO events VALUES (?,?,?)',[('b',0,'posted'),('a',5,'posted'),('a',-2,'posted'),('a',100,'pending'),('c',-2,'posted'),('d',90,'void')])
query=Path({filename!r}).read_text(); assert c.execute(query).fetchall()=={expected!r}
c.execute('DELETE FROM events');assert c.execute(query).fetchall()==[]
'''
        jobs.append(dict(id='totals_'+phase,group='totals',phase=phase,primary_file=filename,files={filename:''},prompt=prompt+SUFFIX,check=check))
    for phase in ['base','repeat','changed']:
        filename=f'intervals_{phase}.py';changed=phase=='changed'
        prompt=(f'Create {filename} with merge_intervals(items). Input is a list of two-element lists [start,end] with integers and start<=end. '
                'Return a sorted list of merged two-element lists. Do not mutate any input list and do not share mutable sublists with it. '
                'Empty input returns []. '+('Merge only strictly overlapping intervals; endpoints that merely touch must remain separate. Zero-length intervals are allowed.' if changed else
                'Merge overlapping intervals and intervals whose endpoints touch.'))
        expected=[[1,3],[3,5],[8,9]] if changed else [[1,5],[8,9]]
        check=f'''from {filename[:-3]} import merge_intervals
items=[[8,9],[3,5],[1,3]];original=[x[:] for x in items]
result=merge_intervals(items);assert result=={expected!r},result
assert items==original;result[0][0]=999;assert items==original
assert merge_intervals([])==[]
assert merge_intervals([[2,6],[1,4]])==[[1,6]]
assert merge_intervals([[3,3]])==[[3,3]]
'''
        jobs.append(dict(id='intervals_'+phase,group='intervals',phase=phase,primary_file=filename,files={filename:''},prompt=prompt+SUFFIX,check=check))
    for n,port in enumerate([8443,9443],1):
        filename='service.json';data=dict(service=dict(port=8080,label='保留',features=['a','b']),other=dict(port=9000),enabled=True)
        expected=json.loads(json.dumps(data));expected['service']['port']=port
        prompt=f'Read service.json and change ONLY service.port to {port}. Preserve every other value, including other.port, Unicode label, arrays and booleans. Do not create other deliverable files. Validate the resulting JSON.'
        check=f'from pathlib import Path\nimport json\nassert json.loads(Path("service.json").read_text())=={expected!r}\n'
        jobs.append(dict(id=f'config_{n}',group='config',phase='edit',primary_file=filename,files={filename:json.dumps(data,ensure_ascii=False)},prompt=prompt+SUFFIX,check=check))
    return jobs
