"""Check five independently specified arithmetic answers; not a design approval."""
from pathlib import Path
import json,math
from course_formula import Workbook
from select_profiles import combined_section

def verify():
    data=json.loads((Path(__file__).resolve().parents[1]/'examples/known_answers.json').read_text('utf-8'));errors=[]
    for c in data['cases']:
        b=Workbook({'Case':c['cells']})
        for a,expected in c['expected'].items():
            actual=b.value('Case',a)
            if not math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-10):errors.append(f'{c["id"]}!{a}: {actual} != {expected}')
        if c['id']=='combined_rectangles':
            result=combined_section({'h':100,'A':10,'y':5,'I':1000/12},100,10)
            if not math.isclose(result['W_cm3'],c['expected']['B3'],rel_tol=1e-10):errors.append('Production combined_section fails exact rectangle example')
    return errors

if __name__=='__main__':
    failures=verify();print('\n'.join(failures)if failures else 'Five arithmetic examples passed. Not course/rule applicability certification.');raise SystemExit(bool(failures))
