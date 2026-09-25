"""Enumerate declared HP catalog against current workbook requirements (T topology).
Writes a candidate report, never silently changes the workbook or CAD.
"""
import argparse,json,math
from pathlib import Path
from recalculate import load

def combined_section(p,width_mm,thickness_mm):
    if width_mm<=0 or thickness_mm<=0:raise ValueError('Attached plate dimensions must be positive')
    b,t=width_mm/10,thickness_mm/10
    ap=b*t;ah=p['A'];yh=p['y']+t/2
    # Origin at plate midplane; the plate centroid is zero, not t/2.
    neutral=ah*yh/(ap+ah)
    inertia=p['I']+b*t**3/12+ah*(yh-neutral)**2+ap*neutral**2
    distances=[neutral+t/2,p['h']/10+t/2-neutral]
    if min(distances)<=0:raise ValueError('Invalid neutral-axis geometry')
    return {'area_cm2':ap+ah,'neutral_cm':neutral,'inertia_cm4':inertia,'W_cm3':min(inertia/d for d in distances)}

def select(book,catalog):
    tags=['B-L','IB-L','OF1','OF2','OF3','OF4','IF1','IF2','IF3','IF4','D-L','D-W']
    result={}
    for r,tag in enumerate(tags,46):
        if book.value('Балки',f'A{r}')!=tag:raise ValueError(f'Template row/identity mismatch at {r}')
        req=book.value('Балки',f'C{r}');smin=book.value('Балки',f'D{r}')
        t=book.value('Балки',f'E{r}');b=book.value('Балки',f'F{r}')*1000
        if not all(isinstance(v,(int,float))and math.isfinite(v)and v>0 for v in [req,smin,t,b]):raise ValueError('Invalid requirements at '+tag)
        candidates=[]
        for p in catalog:
            section=combined_section(p,b,t)
            candidates.append({'name':p['name'],'mass_kg_m':p['mass'],'web_mm':p['s'],'W_cm3':section['W_cm3'],
                'pass':p['s']>=smin and section['W_cm3']>=req})
        candidates.sort(key=lambda v:(v['mass_kg_m'],v['name']))
        passing=[p for p in candidates if p['pass']]
        result[tag]={'W_required_cm3':req,'web_required_mm':smin,'plate_mm':t,'effective_width_mm':b,
            'selected':passing[0]['name'] if passing else None,'current':book.value('Балки',f'B{r+17}'),
            'candidates':candidates}
    # The additional bulkhead sheet is part of this T topology, not an optional
    # footnote to the 12 main groups. B11 there is PLATE minimum thickness: do
    # not silently use it as a stiffener web requirement.
    sn='Дополнительные связи'
    declared=book.raw('Параметры модели','B9') if 'Параметры модели' in book.sheets else None
    smin=book.value('Параметры модели','B9') if declared is not None else None
    if smin is not None and (not isinstance(smin,(int,float))or not math.isfinite(smin)or smin<=0):raise ValueError('Invalid declared CL web minimum')
    for i,r in enumerate(range(37,41),1):
        tag=f'CL-F{i}'
        if book.value(sn,f'A{r}')!=tag:raise ValueError('Additional member identity mismatch: '+tag)
        req=book.value(sn,f'D{r}');width=book.value(sn,f'B{r+11}')*10;t=book.value(sn,'B13')
        if not all(isinstance(v,(int,float))and math.isfinite(v)and v>0 for v in [req,width,t]):raise ValueError('Invalid requirements: '+tag)
        candidates=[]
        for p in catalog:
            wm=combined_section(p,width,t)['W_cm3']
            candidates.append({'name':p['name'],'mass_kg_m':p['mass'],'web_mm':p['s'],'W_cm3':wm,
                'strength_pass':wm>=req,'pass':smin is not None and p['s']>=smin and wm>=req})
        candidates.sort(key=lambda v:(v['mass_kg_m'],v['name']));passing=[p for p in candidates if p['pass']]
        result[tag]={'W_required_cm3':req,'web_required_mm':smin,'plate_mm':t,'effective_width_mm':width,
            'selected':passing[0]['name']if passing else None,'current':book.value(sn,f'E{r}'),
            'pending':None if smin is not None else 'Declare CL web minimum with basis; plate smin is not the web requirement', 'candidates':candidates}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--catalog',type=Path,default=Path(__file__).resolve().parents[1]/'data/hp_catalog.json');a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    data=json.loads(a.catalog.read_text('utf-8'));result=select(load(a.source),data['profiles'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8')as f:json.dump({'catalog_source':data['source'],'scope':'Lightest only within this catalog and the workbook requirements; not full buckling/shear/joint approval.','groups':result},f,ensure_ascii=False,indent=2)
    print('\n'.join(f"{tag}: {v['selected']} (previous {v['current']})"for tag,v in result.items()))
    raise SystemExit(0 if all(v['selected'] for v in result.values()) else 1)
if __name__=='__main__':main()
