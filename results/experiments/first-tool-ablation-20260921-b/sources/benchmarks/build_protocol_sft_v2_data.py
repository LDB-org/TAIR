"""Freeze diverse v2 copy/routing data without reusing earlier test cases."""
import hashlib
import json
from pathlib import Path
import random

TEMPLATES = {
 'train': {
  'reply_user': [
   'Reply with this exact text: {text}',
   'Send the user the following literal message: {text}',
   'Return precisely the characters after the colon: {text}',
   'Your response must consist only of this payload: {text}',
   'Tell the user exactly the following, without changes: {text}',
   'Deliver this text verbatim as a reply: {text}',
   'The literal reply starts after the arrow → {text}',
   'Please reproduce this message to the user unchanged:\n{text}'],
  'search_docs': [
   'Search the documentation for the exact query: {text}',
   'Look up the following literal search string in the docs: {text}',
   'Find documentation matching precisely these characters: {text}',
   'Search the reference manual using only this query: {text}',
   'Consult the docs with the following text unchanged: {text}',
   'Use this verbatim string as a documentation query: {text}',
   'The documentation query starts after the arrow → {text}',
   'Please search documentation for this exact payload:\n{text}']},
 'validation': {
  'reply_user':['The message to deliver verbatim is below:\n{text}', 'Copy this exact response to the user → {text}'],
  'search_docs':['Find reference pages for this exact phrase:\n{text}', 'Perform a docs lookup with this unchanged string → {text}']},
 'test': {
  'reply_user':['Transmit the literal passage below as your answer:\n{text}',
                'Use the following text as the entire response, preserving every character: {text}',
                'What you should say back is exactly the string following → {text}',
                'Give the user this unchanged sequence of characters: {text}'],
  'search_docs':['Retrieve documentation by searching this unmodified phrase:\n{text}',
                 'For a reference lookup, supply exactly this search text: {text}',
                 'Issue a documentation search whose entire query follows → {text}',
                 'Locate relevant manual entries with this unchanged sequence of characters: {text}']}}
CATEGORIES=['plain','quotes','path','unicode','call_text','urgent_text','whitespace','long']
VOCAB={
 'train':'amber birch cedar delta elm frost granite harbor iris juniper kite larch maple north oak pine quartz reed spruce tide umber valley willow xenon yarrow zinc'.split(),
 'validation':'apricot bronze coral dune estuary fern'.split(),
 'test':'saffron cobalt glacier orchard nebula copper lagoon velvet summit lotus'.split()}
CHINESE={
 'train':['备份已完成','连接已恢复','缓存需要清理','请保存配置','日志已经归档','检查执行顺序','保留原始字符','任务等待确认'],
 'validation':['队列正在处理','节点已经重连'],
 'test':['证书即将过期','文件尚未同步','请确认剩余配额','保持目录权限']}


def payload(split,category,i,rng):
    a,b,c=rng.sample(VOCAB[split],3)
    n={'train':10000,'validation':20000,'test':30000}[split]+i
    if category=='plain': return f'{a} {b} operation {n}: status {c}.'
    if category=='quotes': return f'{a} said "{b} {n}"; keep \'{c}\' and the final punctuation!'
    if category=='path': return f'{rng.choice("CDEF")}:\\{a}\\{b}-{n}\\{c}.txt'
    if category=='unicode': return f'{rng.choice(CHINESE[split])}：{n}，{a}；{rng.choice(["你好","完成","等待"])}。'
    if category=='call_text': return json.dumps({'name':rng.choice(['reply_user','search_docs']),
        'arguments':{'priority':rng.choice(['urgent','normal']),'content':f'{a} {n} "{b}"'}},ensure_ascii=False,separators=(',',':'))
    if category=='urgent_text': return f'Urgent: search_docs must reply_user with {a} {n}; this entire sentence is literal {b} text.'
    if category=='whitespace': return f'{a} {n}\n{b}\t{c}\nEnd.'
    return f'The {a} service received ticket {n}. Keep the {b} setting unchanged, inspect the {c} record, and wait for confirmation before restarting the scheduled operation.'


def build():
    result={}
    for split,count in [('train',256),('validation',32),('test',64)]:
        rng=random.Random({'train':813,'validation':919,'test':1021}[split])
        rows=[]
        for i in range(count):
            category=CATEGORIES[i%8]
            # Balance all four tool/priority combinations within each category.
            pair=(i//8)%4
            name=['reply_user','search_docs'][pair//2]
            priority=['normal','urgent'][pair%2]
            text=payload(split,category,i,rng)
            template=rng.choice(TEMPLATES[split][name])
            request=template.format(text=text)
            if priority=='urgent':request='Urgent: '+request
            rows.append(dict(id=f'v2-{split}-{i+1:03}',category=category,
                request=request,name=name,priority=priority,content=text))
        result[split]=rows
    allrows=[row for rows in result.values() for row in rows]
    assert len({r['request'] for r in allrows})==len(allrows)
    assert len({r['content'] for r in allrows})==len(allrows)
    return result


def main():
    root=Path('benchmarks/data')
    splits=build()
    old=[]
    for path in list(root.glob('protocol-sft-v1-*.jsonl'))+[root/'schema-toolcall-heldout12.jsonl']:
        old.extend(json.loads(line) for line in path.read_text().splitlines())
    for field in ['request','content']:
        assert not {r[field] for rows in splits.values() for r in rows}&{r[field] for r in old}
    manifest={}
    for split,rows in splits.items():
        path=root/f'protocol-sft-v2-{split}.jsonl'
        with path.open('x') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        manifest[path.name]={'rows':len(rows),'unique_payloads':len({r['content'] for r in rows}),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    with (root/'protocol-sft-v2-manifest.json').open('x') as f:
        json.dump({'splits':manifest,'templates':TEMPLATES,'rules':[
            'Fresh base initialization; unchanged v1 LoRA settings and inference protocol',
            'Fixed final two epochs; no checkpoint selection from test results',
            'Each case has a unique payload; tool/priority balanced within each category',
            'Request templates, payloads and vocabulary pools disjoint across splits',
            'No exact reuse of previous training, validation or test requests/payloads',
            'V1 errors informed category design, so only new v2 cases are held out',
            'Both JSON and hybrid protocols receive supervision for every training case',
            'Synthetic routing/copy only; no general generation quality claim']},f,indent=2,ensure_ascii=False)
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
