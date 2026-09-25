"""Read-only T workbook checks, including all 16 ordinary member groups.
Not a full engineering approval; drawing, load completeness and stability remain separate.
"""
import argparse,json,math
from pathlib import Path
from recalculate import load
from select_profiles import combined_section
from load_cases import validate_case

ROOT=Path(__file__).resolve().parents[1]

def check(book):
    issues=[];checks=[]
    def compare(label,actual,required,where):
        ok=isinstance(actual,(int,float))and isinstance(required,(int,float))and math.isfinite(actual)and math.isfinite(required)and actual+1e-8>=required
        checks.append({'check':label,'actual':actual,'required':required,'ok':ok,'source':where})
        if not ok:issues.append(f'{label}: {actual:g} < {required:g} ({where})')
    def equal(label,a,b):
        if not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-8):issues.append(f'{label}: {a:g} != {b:g}')
    cat={p['name']:p for p in json.loads((ROOT/'data/hp_catalog.json').read_text('utf-8'))['profiles']}
    for i,tag in enumerate(['B-L','IB-L','OF1','OF2','OF3','OF4','IF1','IF2','IF3','IF4','D-L','D-W']):
        r=46+i;s=11+i
        if book.value('Балки',f'A{r}')!=tag:raise ValueError('Unrecognized row identity: '+tag)
        name=book.value('Балки',f'B{63+i}');p=cat[name]
        b=book.value('Балки',f'F{r}')*1000;t=book.value('Балки',f'E{r}')
        own=combined_section(p,b,t)['W_cm3'];table=book.value('Сечения',f'E{45+i}')
        equal(tag+' computed W vs selected identity',own,table)
        compare(tag+' W',table,book.value('Балки',f'C{r}'),f'Сечения!E{45+i} / Балки!C{r}')
        compare(tag+' web',p['s'],book.value('Балки',f'D{r}'),f'Балки!D{r}')
    extra='Дополнительные связи'
    for i,r in enumerate(range(37,41),1):
        tag=f'CL-F{i}'
        if book.value(extra,f'A{r}')!=tag:raise ValueError('Unrecognized CL identity')
        name=book.value(extra,f'E{r}');p=cat[name]
        own=combined_section(p,book.value(extra,f'B{r+11}')*10,book.value(extra,'B13'))['W_cm3']
        actual=book.value(extra,f'F{r+11}');req=book.value(extra,f'D{r}')
        equal(tag+' computed W vs selected identity',own,actual)
        compare(tag+' W',actual,req,f'{extra}!F{r+11} / D{r}')
        web=book.value('Параметры модели','B9')if 'Параметры модели'in book.sheets else None
        if web is None:issues.append(tag+': web minimum not explicitly declared')
        else:compare(tag+' web',p['s'],web,'Параметры модели!B9')
    for r in range(74,100):
        tag=book.value('Листы',f'A{r}')
        compare(str(tag)+' plate',book.value('Листы',f'D{r}'),max(book.value('Листы',f'B{r}'),book.value('Листы',f'C{r}')),f'Листы!D{r} vs B/C{r}')
    eq='Эквивалентный брус'
    for r,sec in [(42,11),(43,12),(44,22),(45,22)]+[(r,21)for r in range(46,60)]:
        for col,sc in [('B','E'),('C','B')]:
            sr=sec if sc=='E'else sec+17
            equal(f'{eq}!{col}{r+54} identity',book.value(eq,f'{col}{r+54}'),book.value('Сечения',f'{sc}{sr}'))
    for a,req in [('C181','B27'),('C182','B21'),('C179','B29')]:compare(eq+' '+a,book.value(eq,a),book.value('Изгиб корпуса',req),eq+'!'+a)
    for zone,start in [('cargo',20),('wing',60)]:
        count=0
        for r in range(start,start+30):
            if book.raw('Параметры модели',f'A{r}')is None:continue
            count+=1
            try:
                meta=json.loads(book.value('Параметры модели',f'F{r}')or '{}')
                validate_case(dict(meta,condition=book.value('Параметры модели',f'A{r}'),basis=book.value('Параметры модели',f'E{r}'),inside_kpa=book.value('Параметры модели',f'B{r}'),outside_kpa=book.value('Параметры модели',f'C{r}')))
            except Exception as exc:issues.append(f'{zone} load row {r}: {exc}')
        if not count:issues.append(zone+': no declared load cases')
    return {'ok':not issues,'checks':checks,'issues':issues,'scope':'16 member groups, plating, profile binding, global algebra and declared load pairing; not independent geometry or complete engineering approval'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    if a.report and a.report.exists():p.error('Report exists')
    try:result=check(load(a.source))
    except Exception as exc:result={'ok':False,'issues':[str(exc)]}
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        with a.report.open('x',encoding='utf-8')as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items()if k!='checks'},ensure_ascii=False,indent=2));raise SystemExit(0 if result['ok']else 1)
if __name__=='__main__':main()
