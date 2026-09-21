import os, sys
sys.path.insert(0, os.getcwd())
from intervals_base import merge_intervals
items=[[8,9],[3,5],[1,3]];original=[x[:] for x in items]
result=merge_intervals(items);assert result==[[1, 5], [8, 9]],result
assert items==original;result[0][0]=999;assert items==original
assert merge_intervals([])==[]
assert merge_intervals([[2,6],[1,4]])==[[1,6]]
assert merge_intervals([[3,3]])==[[3,3]]
