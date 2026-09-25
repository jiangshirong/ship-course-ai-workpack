"""Read-only final XLSX check: every formula must have a readable, fresh cache.
Uses the limited course engine, not Excel. Does not check engineering or layout.
"""
import argparse,json,math
from pathlib import Path
import openpyxl
from recalculate import load

def validate(path):
    formulas=openpyxl.load_workbook(path,data_only=False)
    cached=openpyxl.load_workbook(path,data_only=True)
    result={'ok':False,'formula_count':0,'cached_formula_count':0,'issues':[], 'engine':'course-scalar; not Excel validation'}
    try:
        book=load(path)
        for s in formulas:
            for row in s:
                for c in row:
                    if c.data_type=='e':result['issues'].append(f'{s.title}!{c.coordinate}: {c.value}')
                    if c.data_type!='f':continue
                    result['formula_count']+=1;v=cached[s.title][c.coordinate].value
                    if v is None:
                        result['issues'].append(f'{s.title}!{c.coordinate}: missing cached result');continue
                    result['cached_formula_count']+=1
                    try:expected=book.value(s.title,c.coordinate)
                    except Exception as exc:result['issues'].append(f'{s.title}!{c.coordinate}: {exc}');continue
                    if isinstance(v,bool) or isinstance(expected,bool):equal=type(v)==type(expected) and v==expected
                    elif isinstance(v,(int,float))and isinstance(expected,(int,float)):equal=math.isclose(v,expected,rel_tol=1e-9,abs_tol=1e-9)
                    else:equal=v==expected
                    if not equal:result['issues'].append(f'{s.title}!{c.coordinate}: cache {v!r} != recalculated {expected!r}')
        if not result['formula_count']:result['issues'].append('No formulas found; this is not a traceable calculation workbook')
    except Exception as exc:result['issues'].append(str(exc))
    finally:formulas.close();cached.close()
    result['ok']=not result['issues'];return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    if a.report and a.report.exists():p.error('Report already exists')
    result=validate(a.source)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        with a.report.open('x',encoding='utf-8')as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['ok']else 1)
if __name__=='__main__':main()
