import os, sys
sys.path.insert(0, os.getcwd())
from labels import unique_labels
a=[" Straße ","STRASSE"," "," A","a ","中文","中文"]
assert unique_labels(a)==[" Straße "," A","中文"]
assert a==[" Straße ","STRASSE"," "," A","a ","中文","中文"]
assert unique_labels([])==[]
