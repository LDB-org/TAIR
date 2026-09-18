import ast
from pathlib import Path
assert ast.dump(ast.parse(Path("app.py").read_text())) == "Module(body=[Import(names=[alias(name='argparse')]), FunctionDef(name='build_parser', args=arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=[Assign(targets=[Name(id='p', ctx=Store())], value=Call(func=Attribute(value=Name(id='argparse', ctx=Load()), attr='ArgumentParser', ctx=Load()), args=[], keywords=[])), Expr(value=Call(func=Attribute(value=Name(id='p', ctx=Load()), attr='add_argument', ctx=Load()), args=[Constant(value='--workers')], keywords=[keyword(arg='type', value=Name(id='int', ctx=Load())), keyword(arg='default', value=Constant(value=6))])), Return(value=Name(id='p', ctx=Load()))], decorator_list=[], type_params=[])], type_ignores=[])"
import app
p=app.build_parser()
assert p.parse_args([]).workers == 6
assert p.parse_args(["--workers", "23"]).workers == 23
