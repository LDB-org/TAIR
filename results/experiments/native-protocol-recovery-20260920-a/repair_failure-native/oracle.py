import os, sys
sys.path.insert(0, os.getcwd())
from calc import mean
a=[1,2]
assert mean(a)==1.5 and a==[1,2]
assert mean([]) is None
assert mean([-2,1])==-0.5
assert isinstance(mean([2]),float)
