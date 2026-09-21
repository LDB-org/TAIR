import sqlite3
conn = sqlite3.connect(':memory:')
conn.execute('CREATE TABLE events(user_id TEXT NOT NULL, amount INTEGER NOT NULL, status TEXT NOT NULL)')
rows = [('a',5,'posted'),('a',-3,'posted'),('a',10,'pending'),('b',0,'posted'),('c',-2,'posted'),('b',-1,'pending')]
conn.executemany('INSERT INTO events VALUES (?,?,?)', rows)
with open('totals_base.sql') as f:
    sql = f.read()
cur = conn.execute(sql)
print(cur.fetchall())
