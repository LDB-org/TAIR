"""Additional authored tasks frozen before testing the general continuation branch."""
import copy
import json
from expanded_reuse_cases import SUFFIX


def cases():
    return [dict(
        id='repair_failure', group='repair', phase='new', primary_file='calc.py',
        workflow=dict(first_command=['python3','check_calc.py'],unchanged_files=['check_calc.py']),
        files={'calc.py': 'def mean(values):\n    return sum(values) // len(values)\n',
               'check_calc.py': 'from calc import mean\nassert mean([1, 2]) == 1.5\nassert mean([]) is None\nassert mean([-2, 1]) == -0.5\n'},
        prompt='Run python3 check_calc.py first. Fix calc.py so mean returns the arithmetic mean as a float for nonempty input and None for empty input. Preserve the input. Do not modify check_calc.py. Run the check again after fixing.'+SUFFIX,
        check='from calc import mean\na=[1,2]\nassert mean(a)==1.5 and a==[1,2]\nassert mean([]) is None\nassert mean([-2,1])==-0.5\nassert isinstance(mean([2]),float)\n'),
      dict(id='csv_totals',group='csv',phase='new',primary_file='csv_totals.py',
        files={'csv_totals.py':''},
        prompt='Create csv_totals.py with totals(text). Parse CSV with header category,amount. Sum integer amounts per category and return a dict. Support quoted commas in category names, negative numbers and Unicode. Empty text or header-only input returns {}. An invalid amount raises ValueError. No import-time I/O.'+SUFFIX,
        check='from csv_totals import totals\nassert totals(\'category,amount\\n"a,b",2\\n中文,4\\n"a,b",-3\\n\')=={"a,b":-1,"中文":4}\nassert totals("")=={}\nassert totals("category,amount\\n")=={}\ntry: totals("category,amount\\nx,no\\n")\nexcept ValueError: pass\nelse: raise AssertionError("invalid amount")\n'),
      dict(id='normalize_labels',group='unicode',phase='new',primary_file='labels.py',
        files={'labels.py':''},
        prompt='Create labels.py with unique_labels(values). Input is a list of strings. Deduplicate using Unicode casefold, after stripping leading and trailing whitespace; discard empty normalized keys. Return the original unmodified string for the first occurrence of each key, preserving order. Do not mutate input. No import-time I/O.'+SUFFIX,
        check='from labels import unique_labels\na=[" Straße ","STRASSE"," "," A","a ","中文","中文"]\nassert unique_labels(a)==[" Straße "," A","中文"]\nassert a==[" Straße ","STRASSE"," "," A","a ","中文","中文"]\nassert unique_labels([])==[]\n')]+mutation_cases()


def mutation_cases():
    jobs=[]
    for phase in ('base','repeat','changed'):
        source=dict(service=dict(port=8080,label='现有配置',features=['a','b']),other=dict(port=9000),enabled=True)
        if phase=='changed':
            source['service'].update(label='另一台机器',features=['b','新增'])
            source.update(other=dict(port=9100),enabled=False,retention=dict(days=17))
        expected=copy.deepcopy(source);expected['service']['port']=8443
        jobs.append(dict(id='edit_state_'+phase,group='edit_state',phase=phase,primary_file='service.json',
            files={'service.json':json.dumps(source,ensure_ascii=False)},
            prompt='Read service.json and change ONLY service.port to 8443. Preserve every other value, including unknown fields, Unicode strings, arrays and booleans. Do not create other deliverable files. Validate the resulting JSON.'+SUFFIX,
            check='from pathlib import Path\nimport json\nassert json.loads(Path("service.json").read_text())=='+repr(expected)+'\n'))
    return jobs
