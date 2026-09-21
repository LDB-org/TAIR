"""Fresh authored requirement-change cases, frozen before this evaluation."""
from expanded_reuse_cases import SUFFIX


def cases():
    jobs=[]
    for changed in [False,True]:
        phase='changed' if changed else 'base';name=f'chunks_{phase}.py'
        prompt=(f'Create {name} defining chunks(values, size). Input values is a list and size is an integer. '
                'Return consecutive chunks as fresh lists in a fresh outer list, in original order, without mutating values. '
                'Return [] for empty values. Raise ValueError for size <= 0, including empty values. '+
                ('Pad the last nonempty chunk with None until it has exactly size elements.' if changed else
                 'The last chunk may be shorter than size; never add padding.'))
        check=f'''from {name[:-3]} import chunks
x=[1,2,3,4,5]
assert chunks(x,2)=={[[1,2],[3,4],[5,None]] if changed else [[1,2],[3,4],[5]]!r}
assert x==[1,2,3,4,5]
assert chunks([],3)==[]
assert chunks([1,2],2)==[[1,2]]
assert chunks([None],2)=={[[None,None]] if changed else [[None]]!r}
r=chunks(x,10);r[0][0]=99;assert x[0]==1
for n in [0,-1]:
 for v in [[],[1]]:
  try: chunks(v,n)
  except ValueError: pass
  else: raise AssertionError('invalid size')
'''
        jobs.append(dict(id='chunks_'+phase,group='chunks_fresh',phase='fresh',primary_file=name,files={name:''},prompt=prompt+SUFFIX,check=check))
    for changed in [False,True]:
        phase='changed' if changed else 'base';name=f'nullable_{phase}.sql'
        prompt=(f'Create {name} containing only one SQLite SELECT query, no Markdown. '
                'Table readings has columns station TEXT and value INTEGER (nullable). Return station and total, '
                'where total is SUM(value) with all-NULL sums converted to 0. Group by station and order by station ascending. '+
                ('Exclude groups having no non-NULL values. Keep groups whose non-NULL values sum to zero or a negative number.' if changed else
                 'Include all stations, even if all their values are NULL.'))
        expected=[('a',0),('b',-2),('d',0),('e',7)] if changed else [('a',0),('b',-2),('c',0),('d',0),('e',7)]
        check=f'''import sqlite3
from pathlib import Path
c=sqlite3.connect(':memory:');c.execute('CREATE TABLE readings(station TEXT,value INTEGER)')
c.executemany('INSERT INTO readings VALUES (?,?)',[('a',1),('a',-1),('b',-2),('b',None),('c',None),('d',0),('e',7),('e',None)])
sql=Path({name!r}).read_text();assert c.execute(sql).fetchall()=={expected!r}
c.execute('DELETE FROM readings');assert c.execute(sql).fetchall()==[]
'''
        jobs.append(dict(id='nullable_'+phase,group='nullable_fresh',phase='fresh',primary_file=name,files={name:''},prompt=prompt+SUFFIX,check=check))
    return jobs
