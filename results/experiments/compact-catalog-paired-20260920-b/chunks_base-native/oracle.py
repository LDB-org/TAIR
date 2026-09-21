import os, sys
sys.path.insert(0, os.getcwd())
from chunks_base import chunks
x=[1,2,3,4,5]
assert chunks(x,2)==[[1, 2], [3, 4], [5]]
assert x==[1,2,3,4,5]
assert chunks([],3)==[]
assert chunks([1,2],2)==[[1,2]]
assert chunks([None],2)==[[None]]
r=chunks(x,10);r[0][0]=99;assert x[0]==1
for n in [0,-1]:
 for v in [[],[1]]:
  try: chunks(v,n)
  except ValueError: pass
  else: raise AssertionError('invalid size')
