import os, sys
sys.path.insert(0, os.getcwd())
import sqlite3
from pathlib import Path
c=sqlite3.connect(':memory:');c.execute('CREATE TABLE events(user_id TEXT NOT NULL,amount INTEGER NOT NULL,status TEXT NOT NULL)')
c.executemany('INSERT INTO events VALUES (?,?,?)',[('b',0,'posted'),('a',5,'posted'),('a',-2,'posted'),('a',100,'pending'),('c',-2,'posted'),('d',90,'void')])
query=Path('totals_repeat.sql').read_text(); assert c.execute(query).fetchall()==[('a', 3), ('b', 0), ('c', -2)]
c.execute('DELETE FROM events');assert c.execute(query).fetchall()==[]
