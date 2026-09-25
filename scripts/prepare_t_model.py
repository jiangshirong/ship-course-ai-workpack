"""Build a parameterized T workbook SPEC for further design, not a finished assignment.
Historical workbooks remain unchanged. See docs/T型参数化.md for scope/units.
"""
import argparse,json,math
from pathlib import Path
from course_formula import Workbook
from check_geometry import check
from load_cases import validate_case

ROOT=Path(__file__).resolve().parents[1]
DESIGN_INPUTS={'tank_length_m':'B26','density_t_m3':'B28','airpipe_height_m':'B29','valve_pressure_kpa':'B30',
    'service_years':'B31','corrosion_start_year':'B32','yield_mpa':'B33','eta':'B34','ax':'B36','avax':'B37',
    'gravity_m_s2':'B38','midship_coefficient':'B39','floor_k1':'B51','floor_k2':'B52'}

def prepare(config):
    if config.get('schema_version')!=3:raise ValueError('Use schema_version 3; migrate with docs/输入字段契约.md')
    g=config['given'];m=config['layout']
    assumptions=config.get('design_inputs',{})
    for k in [*DESIGN_INPUTS,'cl_web_min_mm']:
        item=assumptions.get(k,{})
        if not isinstance(item,dict)or not item.get('basis'):raise ValueError('Explicit design_inputs value/basis required: '+k)
        v=item.get('value')
        if isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)or v<0:raise ValueError('Invalid design_inputs: '+k)
    for k in ['tank_length_m','density_t_m3','eta','yield_mpa','gravity_m_s2','cl_web_min_mm']:
        if assumptions[k]['value']<=0:raise ValueError(k+' must be positive')
    if assumptions['service_years']['value']<assumptions['corrosion_start_year']['value']:raise ValueError('Corrosion start exceeds service life')
    if not 0<assumptions['midship_coefficient']['value']<=1:raise ValueError('Invalid midship coefficient')
    for tag in [f'CL-F{i}'for i in range(1,5)]:
        if tag not in config['profiles']:raise ValueError('Missing additional profile identity: '+tag)
    if len(m['longitudinals']['deck']['x_from_center_m'])>14 or len(m['wing_x_from_shell_m'])!=2:
        raise ValueError('Reference supports at most 14 deck pairs and exactly 2 wing pairs; extend model explicitly')
    # Avoid silently substituting model geometry for the given dimensions.
    for k in ['B','D']:
        if abs(g[k]-m[k])>1e-9:raise ValueError('Given/layout mismatch: '+k)
    for xs in [m['wing_x_from_shell_m']]:
        if xs!=sorted(set(xs)) or any(not 0<x<m['side_width'] for x in xs):raise ValueError('Invalid wing coordinates')
    report=check(m)
    if not report['ok']:raise ValueError('; '.join(report['errors']))
    for key,n in [('flat_bands_m',7),('arc_bands_m',2),('side_bands_m',9),('inner_bands_m',7)]:
        if len(m[key])!=n:raise ValueError(f'{key} must have {n} bands for this reference topology')
    spec=json.loads((ROOT/'templates/T/workbook.json').read_text('utf-8'))
    index={s['name']:{c['address']:c for c in s['cells']} for s in spec['sheets']}
    def put(sn,a,v):
        if a not in index[sn]:
            c={'address':a,'value':v,'number_format':'General'}
            next(s for s in spec['sheets']if s['name']==sn)['cells'].append(c);index[sn][a]=c
        index[sn][a]['value']=v
    sn='Параметры модели'
    spec['sheets'].append({'name':sn,'cells':[],'merged_ranges':[],'column_widths':{'A':24,'B':24,'C':24,'D':24,'E':65,'F':24}});index[sn]={}
    put(sn,'A1','ЧЕРНОВИК: пересчитать нагрузки и подобрать профили; пример не является заданием')
    base='Исходные данные';eq='Эквивалентный брус'
    ref=lambda a:f"'{sn}'!{a}"
    for a,k in [('B8','L'),('B9','B'),('B10','D'),('B11','draft'),('B12','Cb'),('B13','speed_kn')]:put(base,a,g[k])
    for k,a in DESIGN_INPUTS.items():put(base,a,assumptions[k]['value'])
    for r,(k,v)in enumerate(assumptions.items(),200):
        put(sn,f'A{r}',k);put(sn,f'B{r}',v['value']);put(sn,f'E{r}',v['basis'])
    for col,label in [('A','Параметр'),('B','Значение (ед. в имени)'),('E','Обоснование')]:put(sn,col+'199',label)
    put(sn,'A9','Минимальная стенка CL-F, мм');put(sn,'B9',assumptions['cl_web_min_mm']['value']);put(sn,'E9',assumptions['cl_web_min_mm']['basis'])
    for a,k in [('B14','double_bottom'),('B15','side_width'),('B16','R'),('B17','camber'),('B18','frame_spacing_m'),('B19','frames_per_support')]:put(base,a,m[k])
    if len(m['platforms_m'])!=3:raise ValueError('Reference topology requires 3 platforms')
    if not m['double_bottom']<m['platforms_m'][0]<m['platforms_m'][1]<m['platforms_m'][2]<m['D']:raise ValueError('Platforms outside side')
    for a,v in zip(['B23','B24','B25'],m['platforms_m']):put(base,a,v)
    put(base,'B21',len(m['longitudinals']['deck']['x_from_center_m'])+1)
    put(base,'B22',max(v['calculation_spacing_m']for v in m['longitudinals'].values()))
    put(sn,'A3','z внутреннего борта, м');put(sn,'B3',f"='{base}'!B10+'{base}'!B17*'{base}'!B15/('{base}'!B9/2)")
    put('Балластные случаи','B9','='+ref('B3'))
    # Positive geometric partitions replace fixed 2000-mm residuals. Ratios
    # describe a chosen seam layout, not a regulation or an optimal width.
    for key,rows,total in [
        ('flat_bands_m',range(12,19),f"('{base}'!B9/2-'{base}'!B16)*1000"),
        ('arc_bands_m',range(19,21),f"PI()/2*'{base}'!B16*1000"),
        ('side_bands_m',range(21,30),f"('{base}'!B10-'{base}'!B16)*1000"),
        ('inner_bands_m',range(33,40),f"({ref('B3')}-'{base}'!B14)*1000")]:
        widths=m[key]
        for row,width in zip(rows,widths):put(eq,f'D{row}',f'=({total})*{width/sum(widths):.17g}')
    # Keep explicit chosen seam widths visible, with the dynamic height closure.
    # Existing centroid/arc-inertia formulas derive from D12:D39.
    for row,key in [(12,'bottom'),(13,'inner_bottom'),(22,'deck')]:
        put('Балки',f'C{row}',m['longitudinals'][key]['calculation_spacing_m'])
    wing=m['wing_x_from_shell_m'];winggaps=[wing[0],wing[1]-wing[0],m['side_width']-wing[1]]
    put('Балки','C23',max(winggaps))
    # Separate pressure envelopes. Each row contains ONE same-condition pair.
    for r,(key,target) in enumerate([('cargo','E22'),('wing','E23')],6):
        cases=config['deck_cases'][key]
        if not cases:raise ValueError('Missing deck load cases: '+key)
        start=20 if key=='cargo' else 60
        for col,label in zip('ABCDEF',['Состояние','p внутри, кПа','p снаружи, кПа','|Δp|, кПа','Источник/вывод','Условия сочетания']):put(sn,f'{col}{start-1}',label)
        if len(cases)>30:raise ValueError('At most 30 cases per zone in this reference')
        put(sn,f'A{r}',key+' pнетто, кПа')
        for j,c in enumerate(cases,start):
            validate_case(c)
            if not c.get('basis') or not c.get('condition'):raise ValueError('Case needs condition and source/basis')
            for k in ['inside_kpa','outside_kpa']:
                if not isinstance(c[k],(int,float))or not math.isfinite(c[k])or c[k]<0:raise ValueError('Invalid case pressure')
            for col,key2 in [('A','condition'),('B','inside_kpa'),('C','outside_kpa'),('E','basis')]:put(sn,f'{col}{j}',c[key2])
            put(sn,f'D{j}',f'=ABS(B{j}-C{j})')
            put(sn,f'F{j}',json.dumps({k:v for k,v in c.items()if k not in ['inside_kpa','outside_kpa','basis','condition']},ensure_ascii=False,sort_keys=True))
        put(sn,f'B{r}',f'=MAX(D{start}:D{start+len(cases)-1})')
        put('Балки',target,'='+ref(f'B{r}'))
    # Bind section properties and beam selection by identity, never old row offsets.
    catalog={p['name']:p for p in json.loads((ROOT/'data/hp_catalog.json').read_text('utf-8'))['profiles']}
    tags=['B-L','IB-L','OF1','OF2','OF3','OF4','IF1','IF2','IF3','IF4','D-L','D-W']
    for i,tag in enumerate(tags):
        p=catalog[config['profiles'][tag]];r=11+i
        put('Балки',f'B{63+i}',p['name'])
        for col,k,scale in [('C','h',.1),('D','s',.1),('E','A',1),('F','y',1)]:put('Сечения',f'{col}{r}',p[k]*scale)
        put('Сечения',f'B{28+i}',p['I'])
    # CL columns use the same declared identity and properties as the drawing,
    # instead of the historical HP row numbers in the additional-member sheet.
    extra='Дополнительные связи'
    for col,label in zip('ABCDEFG',['Марка','Профиль','h, см','s, см','A, см²','y0, см','I, см⁴']):put(sn,col+'169',label)
    for i in range(4):
        r=37+i;q=48+i;row=170+i;p=catalog[config['profiles'][f'CL-F{i+1}']]
        put(sn,f'A{row}',f'CL-F{i+1}');put(sn,f'B{row}',p['name'])
        for col,k,scale in [('C','h',.1),('D','s',.1),('E','A',1),('F','y',1),('G','I',1)]:put(sn,f'{col}{row}',p[k]*scale)
        put(extra,f'E{r}','='+ref(f'B{row}'))
        area=ref(f'E{row}');height=ref(f'C{row}');y=ref(f'F{row}');inertia=ref(f'G{row}')
        put(extra,f'D{q}',f'={area}*({y}+$B$13/20)/({area}+C{q})')
        put(extra,f'E{q}',f'={inertia}+B{q}*($B$13/10)^3/12+{area}*({y}+$B$13/20-D{q})^2+C{q}*D{q}^2')
        put(extra,f'F{q}',f'=MIN(E{q}/({height}+$B$13/20-D{q}),E{q}/(D{q}+$B$13/20))')
    for r,section,coord in [(42,11,None),(43,12,None)]+[(r,22,m['wing_x_from_shell_m'][r-44])for r in range(44,46)]+[(r,21,None)for r in range(46,60)]:
        inertia=r+54;put(eq,f'B{inertia}',f"='Сечения'!E{section}");put(eq,f'C{inertia}',f"='Сечения'!B{section+17}")
        put(eq,f'E{r}',f"='Сечения'!D{section}*10")
        if r==42:
            put(eq,f'C{r}',m['longitudinals']['bottom']['full_count']);z=f"'Сечения'!F{section}"
        elif r==43:
            put(eq,f'C{r}',m['longitudinals']['inner_bottom']['full_count']);z=f"'{base}'!B14*100-'Сечения'!F{section}"
        else:
            if r>=46:
                xs=m['longitudinals']['deck']['x_from_center_m'];i=r-46
                coord=m['B']/2-(xs[i]if i<len(xs) else 0)
                put(eq,f'C{r}',2 if i<len(xs)else 0)
            else:put(eq,f'C{r}',2)
            put(sn,f'B{100+r}',coord)
            z=f"('{base}'!B10+'{base}'!B17*{ref(f'B{100+r}')}/('{base}'!B9/2))*100-'Сечения'!F{section}"
        put(eq,f'F{r}','='+z)
    spec['role']='PARAMETERIZED_DRAFT_REQUIRES_DESIGN_REVIEW'
    spec['cached_values_are_historical']=False
    spec['parameterization']={'source':'templates/T/workbook.json','geometry_check':report,'config':config,
        'limits':'Fixed reference topology; loads, plate selection, supports and all engineering checks still require review. Profile data copied from the declared catalog; rerun after changing selection.'}
    # Drop every stale cache, including dependent and apparently unaffected cells.
    for sheet in spec['sheets']:
        for c in sheet['cells']:c.pop('cached',None)
    return spec

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('config',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    if a.output.exists():p.error('Output already exists')
    spec=prepare(json.loads(a.config.read_text('utf-8')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(spec,f,ensure_ascii=False,indent=2,allow_nan=False)
    print('Parameterized DRAFT saved. Not a completed assignment; review loads, plating and profiles.')
if __name__=='__main__':main()
