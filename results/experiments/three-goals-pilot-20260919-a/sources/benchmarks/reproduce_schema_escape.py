"""CPU-only check of the local schema compiler's JSON string acceptance."""
import argparse
import importlib.metadata
import json
from pathlib import Path

from schema_toolcall import SCHEMA


def main():
    import xgrammar as xgr
    from transformers import AutoTokenizer
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    compiler=xgr.GrammarCompiler(xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=151936))
    ctx=compiler.compile_json_schema(json.dumps(SCHEMA),any_whitespace=True)
    contents={'plain':'abc','escaped_tab':'a\\tb','literal_tab':'a\tb',
        'escaped_quote':'a\\"b','escaped_backslash':'a\\\\b','literal_newline':'a\nb'}
    rows=[]
    for name,content in contents.items():
        raw='{"name":"reply_user","arguments":{"priority":"normal","content":"'+content+'"}}'
        try:json.loads(raw);valid=True
        except json.JSONDecodeError:valid=False
        matcher=xgr.GrammarMatcher(ctx)
        accepted=matcher.accept_string(raw)
        tokenmatcher=xgr.GrammarMatcher(ctx)
        tokenaccepted=all(tokenmatcher.accept_token(t) for t in tokenizer.encode(raw,add_special_tokens=False))
        rows.append({'case':name,'raw':raw,'python_json_valid':valid,
            'grammar_string_accepted':accepted,'grammar_tokens_accepted':tokenaccepted,
            'grammar_string_completed':matcher.is_completed()})
    report={'model':args.model,'versions':{k:importlib.metadata.version(k) for k in ['xgrammar','vllm','transformers']},
            'schema':SCHEMA,'any_whitespace':True,'rows':rows,
            'limits':'Local installed compiler reproduction; no serving code changed; not a claim about all structured output implementations'}
    with args.output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
