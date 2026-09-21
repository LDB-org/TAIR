"""Small authored protocol SFT; checkpoints stay outside versioned evidence."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import time

import schema_toolcall as base


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TeacherSession:
    """Capture exact append-only inference prompts under teacher forcing."""
    case = None
    samples = []

    def __init__(self, model, tokenizer):
        self.tokenizer = tokenizer
        self.transcript = ''
        self.trace = []
        self.forward_calls = self.input_tokens = 0
        self.stage = 0

    def prompt(self, messages):
        text = self.transcript + self.tokenizer.apply_chat_template(
            messages if not self.transcript else [messages[-1]], tokenize=False,
            add_generation_prompt=True, enable_thinking=False)
        self.trace.append({'prompt': text})
        return text

    def choose(self, messages, values):
        messages[-1]['content'] += '\nSelect one value. Reply with its letter only.\n' + '\n'.join(
            f'{letter}: {value}' for letter, value in zip('ABCDEFGHIJKLMNOP', values))
        text = self.prompt(messages)
        index = int(self.case['name'] == 'search_docs') if self.stage == 0 else int(self.case['priority'] == 'urgent')
        label = 'AB'[index]
        # Selection has one decision token; engine supplies the turn terminator.
        self.samples.append((text, label))
        self.transcript = text + label + self.tokenizer.eos_token + '\n'
        messages.append({'role': 'assistant', 'content': label})
        self.stage += 1
        return values[index]

    def generate(self, messages, limit):
        target = self.case['content'] if self.stage else json.dumps({
            'name': self.case['name'], 'arguments': {
                'priority': self.case['priority'], 'content': self.case['content']}}, ensure_ascii=False)
        self.samples.append((self.prompt(messages), target + self.tokenizer.eos_token))
        return target, len(self.tokenizer.encode(target)), True


def examples(tokenizer, cases):
    old = base.Session
    base.Session = TeacherSession
    TeacherSession.samples = []
    try:
        for case in cases:
            TeacherSession.case = case
            for mode in ['hybrid_fields', 'json']:
                base.run(None, tokenizer, case, mode, 128)
        return list(TeacherSession.samples)
    finally:
        base.Session = old


def encode(tokenizer, prompt, target):
    prefix = tokenizer.encode(prompt, add_special_tokens=False)
    ids = tokenizer.encode(prompt + target, add_special_tokens=False)
    if ids[:len(prefix)] != prefix or len(ids) == len(prefix):
        raise ValueError('Training target changed the prompt token boundary')
    return ids, [-100] * len(prefix) + ids[len(prefix):]


def main():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--train', type=Path, required=True)
    p.add_argument('--validation', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--epochs', type=int, default=2)
    args = p.parse_args()
    if args.output.exists() or args.report.exists() or args.epochs < 1:
        p.error('Use new output paths and positive epochs')
    torch.manual_seed(731)
    random.seed(731)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    data = {}
    for split, path in [('train', args.train), ('validation', args.validation)]:
        cases = [json.loads(line) for line in path.read_text().splitlines()]
        data[split] = [encode(tokenizer, *sample) for sample in examples(tokenizer, cases)]
    if max(len(ids) for rows in data.values() for ids, _ in rows) > 1024:
        raise ValueError('Do not truncate protocol examples')
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16,
        local_files_only=True, attn_implementation='sdpa').to('cuda')
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0,
        target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=2e-4)
    def loss(row):
        ids, labels = row
        # Only target-position logits are needed; avoids full-vocabulary prompt logits.
        start = next(i for i, label in enumerate(labels) if label != -100)
        positions = torch.arange(start-1, len(ids)-1, device='cuda')
        logits = model(input_ids=torch.tensor([ids], device='cuda'),
                       logits_to_keep=positions, use_cache=False).logits
        return torch.nn.functional.cross_entropy(logits[0].float(),
                    torch.tensor(ids[start:], device='cuda'))
    def validate():
        model.eval()
        with torch.no_grad():
            values = [float(loss(row)) for row in data['validation']]
        model.train()
        return sum(values) / len(values)
    before = validate()
    print(json.dumps({'validation_before': before, 'examples': {k:len(v) for k,v in data.items()}}), flush=True)
    history = []
    started = time.perf_counter()
    model.train()
    for epoch in range(args.epochs):
        order = list(data['train']); random.shuffle(order)
        optimizer.zero_grad(set_to_none=True)
        running = []
        for i,row in enumerate(order):
            value = loss(row); (value / 4).backward(); running.append(float(value.detach()))
            if (i+1)%4 == 0 or i+1 == len(order):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step(); optimizer.zero_grad(set_to_none=True)
            if (i+1)%32 == 0:
                event = {'epoch':epoch+1,'example':i+1,'loss':sum(running[-32:])/32,
                         'seconds':time.perf_counter()-started}
                history.append(event); print(json.dumps(event),flush=True)
    after = validate()
    args.output.mkdir(parents=True)
    model.save_pretrained(args.output/'adapter')
    model = model.merge_and_unload()
    model.config.use_cache = True
    model.save_pretrained(args.output/'merged')
    tokenizer.save_pretrained(args.output/'merged')
    report = {'base_model':args.model,'revision':args.revision,'seed':731,'epochs':args.epochs,
        'learning_rate':2e-4,'gradient_accumulation':4,'lora_rank':16,'lora_alpha':32,
        'target_modules':['q_proj','v_proj'],'dtype':'bfloat16','selection':'fixed final epoch, no test-based selection',
        'training_sha256':digest(args.train),'validation_sha256':digest(args.validation),
        'runner_sha256':digest(__file__),'protocol_runner_sha256':digest(base.__file__),
        'versions':{k:importlib.metadata.version(k) for k in ['torch','transformers','peft']},
        'examples':{k:len(v) for k,v in data.items()},'validation_loss_before':before,
        'validation_loss_after':after,'seconds':time.perf_counter()-started,'history':history,
        'checkpoint_files':{str(p.relative_to(args.output)):digest(p) for p in args.output.rglob('*') if p.is_file()}}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    with args.report.open('x') as f: json.dump(report,f,indent=2)
    print(json.dumps({'validation_after':after,'report':str(args.report)}),flush=True)


if __name__ == '__main__':
    main()
