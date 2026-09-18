"""Guard split isolation and teacher-forced prompt fidelity."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import build_protocol_sft_data as data
from train_toolcall_protocol import TeacherSession, encode


def test_frozen_splits_reproduce_and_do_not_overlap():
    splits=data.build()
    for name,rows in splits.items():
        frozen=[json.loads(line) for line in (ROOT/f'benchmarks/data/protocol-sft-v1-{name}.jsonl').read_text().splitlines()]
        assert rows==frozen
    assert [len(splits[k]) for k in ['train','validation','test']]==[96,16,32]


def test_teacher_selection_only_targets_decision_and_preserves_prefix():
    class Tokenizer:
        eos_token='<|im_end|>'
        def apply_chat_template(self,messages,**kwargs):
            return ''.join(m['content'] for m in messages)+'ASSISTANT:'
    TeacherSession.case={'name':'search_docs','priority':'normal'}
    TeacherSession.samples=[]
    s=TeacherSession(None,Tokenizer()); messages=[{'role':'user','content':'Evidence'}]
    assert s.choose(messages,['reply','search'])=='search'
    prompt,target=TeacherSession.samples[0]
    assert target=='B'
    assert s.transcript==prompt+'B<|im_end|>\n'
    messages.append({'role':'user','content':'priority'})
    assert s.choose(messages,['normal','urgent'])=='normal'
    assert TeacherSession.samples[1][0].startswith(s.trace[0]['prompt']+'B<|im_end|>\n')


def test_target_mask_and_boundary():
    class Tokenizer:
        def encode(self,text,**kwargs): return list(text.encode())
    ids,labels=encode(Tokenizer(),'prompt','answer')
    assert labels[:6]==[-100]*6
    assert labels[6:]==ids[6:]==list(b'answer')


def test_v2_diversity_balance_and_frozen_splits():
    from collections import Counter
    import build_protocol_sft_v2_data as v2
    splits=v2.build()
    assert [len(splits[k]) for k in ['train','validation','test']]==[256,32,64]
    allrows=[r for rows in splits.values() for r in rows]
    assert len({r['content'] for r in allrows})==len(allrows)
    for split,rows in splits.items():
        frozen=[json.loads(line) for line in (ROOT/f'benchmarks/data/protocol-sft-v2-{split}.jsonl').read_text().splitlines()]
        assert rows==frozen
        counts=Counter((r['category'],r['name'],r['priority']) for r in rows)
        assert len(counts)==32
        assert set(counts.values())=={len(rows)//32}
    for left,right in [('train','validation'),('train','test'),('validation','test')]:
        for name in ['reply_user','search_docs']:
            assert not set(v2.TEMPLATES[left][name]) & set(v2.TEMPLATES[right][name])
