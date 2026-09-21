"""Author deterministic disjoint toy splits; no external evaluation records."""
import hashlib
import json
from pathlib import Path

TEMPLATES = {
 'train': {
  'reply_user':['Reply to the user with exactly: {text}', 'Send this literal message to the user: {text}', 'Tell the user precisely this text: {text}'],
  'search_docs':['Search documentation for exactly: {text}', 'Look up this literal query in the docs: {text}', 'Find documentation using precisely this query: {text}']},
 'validation': {
  'reply_user':['The required reply text is: {text}'],
  'search_docs':['The required documentation search query is: {text}']},
 'test': {
  'reply_user':['Deliver the following characters verbatim as your response: {text}', 'Respond with the literal text after the arrow → {text}'],
  'search_docs':['Consult the reference manual; use only the following search string: {text}', 'Query the documentation index for the literal text after the arrow → {text}']}}


def payloads(split):
    if split == 'train':
        return [pattern.format(n=n) for n in range(3) for pattern in [
          'Backup job {n} finished.', 'cache eviction mode {n}', 'Status "green" at node {n}.',
          'folder C:\\data\\batch{n}', '任务{n}已经完成。',
          '{{"name":"search_docs","batch":{n}}}', 'Urgent: this is quoted payload {n}.',
          'First line {n}.\nSecond line.']]
    if split == 'validation':
        return ['Worker nineteen paused.', 'path D:\\archive\\draft', '已恢复连接。', '{"name":"reply_user","ok":true}']
    return ['The violet queue is empty!', 'certificate renewal interval',
            'She said "wait", then left.', 'E:\\staging\\résumé.txt',
            '请保留这一行：测试通过。', '{"name":"search_docs","arguments":{"content":"urgent"}}',
            'Urgent: search_docs is merely quoted text here.', 'Alpha\nBeta\tGamma']


def build():
    splits = {}
    for split in TEMPLATES:
        rows = []
        for index,text in enumerate(payloads(split)):
            for name in ['reply_user','search_docs']:
                for priority in ['normal','urgent']:
                    templates=TEMPLATES[split][name]
                    request=templates[index%len(templates)].format(text=text)
                    if priority=='urgent': request='Urgent: '+request
                    rows.append(dict(id=f'{split}-{len(rows)+1:03}',request=request,name=name,priority=priority,content=text))
        splits[split]=rows
    for left,right in [('train','validation'),('train','test'),('validation','test')]:
        assert not {r['request'] for r in splits[left]} & {r['request'] for r in splits[right]}
        assert not {r['content'] for r in splits[left]} & {r['content'] for r in splits[right]}
    return splits


def main():
    root=Path('benchmarks/data')
    manifest={}
    for split,rows in build().items():
        path=root/f'protocol-sft-v1-{split}.jsonl'
        with path.open('x') as f:
            for row in rows: f.write(json.dumps(row,ensure_ascii=False)+'\n')
        manifest[path.name]={'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    with (root/'protocol-sft-v1-manifest.json').open('x') as f:
        json.dump({'splits':manifest,'rules':['Disjoint request templates and payloads across splits',
            'All four tool/priority combinations for each payload',
            'Priority refers to outer request, not urgency words inside literal payload',
            'Fixed final 2-epoch checkpoint; test opened for scoring only after training',
            'Joint SFT on three hybrid stages and full JSON for every training case',
            'Synthetic routing/copy task only, not general tool-use evaluation']},f,indent=2)
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()
