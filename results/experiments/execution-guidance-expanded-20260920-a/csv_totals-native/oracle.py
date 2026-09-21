import os, sys
sys.path.insert(0, os.getcwd())
from csv_totals import totals
assert totals('category,amount\n"a,b",2\n中文,4\n"a,b",-3\n')=={"a,b":-1,"中文":4}
assert totals("")=={}
assert totals("category,amount\n")=={}
try: totals("category,amount\nx,no\n")
except ValueError: pass
else: raise AssertionError("invalid amount")
