import os, sys
sys.path.insert(0, os.getcwd())
import sqlite3
from pathlib import Path
c=sqlite3.connect(':memory:');c.execute('CREATE TABLE readings(station TEXT,value INTEGER)')
c.executemany('INSERT INTO readings VALUES (?,?)',[('a',1),('a',-1),('b',-2),('b',None),('c',None),('d',0),('e',7),('e',None)])
sql=Path('nullable_base.sql').read_text();assert c.execute(sql).fetchall()==[('a', 0), ('b', -2), ('c', 0), ('d', 0), ('e', 7)]
c.execute('DELETE FROM readings');assert c.execute(sql).fetchall()==[]
