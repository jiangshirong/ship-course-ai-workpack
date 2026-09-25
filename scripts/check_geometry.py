"""Check declared section geometry, band closure, beam spacing and calculation bindings.
Input follows examples/t_layout.json. This checks the model, not the native DWG.
"""
import argparse,json,math
from pathlib import Path

def check(m):
    errors=[];stats={}
    def require(ok,msg):
        if not ok:errors.append(msg)
    def close(a,b,msg,tol=1e-7):require(abs(a-b)<=tol,f'{msg}: {a:g} vs {b:g}')
    B,D,R,b,h,f=(float(m[k])for k in ['B','D','R','side_width','double_bottom','camber'])
    require(all(math.isfinite(v) for v in (B,D,R,b,h,f)),'Nonfinite geometry')
    require(B>0 and D>0 and 0<R<min(D,B/2) and 0<b<B/2 and 0<h<D and f>=0,'Invalid section dimensions')
    if errors:return {'ok':False,'errors':errors,'measurements':stats}
    zi=D+f*b/(B/2)
    stats.update(inner_side_top_m=zi,deck_center_m=D+f,half_developed_m=B/2-R+math.pi*R/2+D-R)
    # Every segment must close independently; total closure alone hides misplaced seams.
    for key,target in [('flat_bands_m',B/2-R),('arc_bands_m',math.pi*R/2),('side_bands_m',D-R),('inner_bands_m',zi-h)]:
        widths=m[key]
        require(bool(widths) and all(isinstance(x,(float,int)) and math.isfinite(x) and x>0 for x in widths),key+': all widths must be positive')
        close(sum(widths),target,key)
    close(m['workbook_inner_side_top_m'],zi,'Workbook inner side height')
    close(m['cad_inner_side_top_m'],zi,'CAD inner side height')
    for key in ['deck','bottom','inner_bottom']:
        p=m['longitudinals'][key];xs=p['x_from_center_m'];end=B/2-b
        require(xs==sorted(set(xs)) and all(0<x<end for x in xs),key+': coordinates must be unique, ordered, inside compartment')
        gaps=[v-u for u,v in zip([0]+xs,xs+[end])]
        actual=max(gaps);stats[key+'_max_gap_m']=actual
        require(p['calculation_spacing_m']+1e-9>=actual,key+': calculation spacing smaller than an actual end/intermediate gap')
        require(p['full_count']==2*len(xs),key+': workbook count differs from coordinates')
        close(p['support_span_m'],m['frame_spacing_m']*m['frames_per_support'],key+' support span')
        close(p['calculation_span_m'],p['support_span_m'],key+' calculation span')
    for label,p in m.get('profile_bindings',{}).items():
        require(p['selected_name']==p['equivalent_name']==p['cad_name'],label+': profile names disagree')
        for k in ['area_cm2','inertia_cm4','centroid_cm']:
            close(p['selected'][k],p['equivalent'][k],label+': '+k)
    return {'ok':not errors,'errors':errors,'measurements':stats}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model',type=Path);p.add_argument('--report',type=Path)
    a=p.parse_args()
    if a.report and a.report.exists():p.error('Report already exists')
    try:result=check(json.loads(a.model.read_text('utf-8')))
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as e:result={'ok':False,'errors':['Incomplete/invalid model: '+str(e)]}
    txt=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        with a.report.open('x',encoding='utf-8') as f:f.write(txt)
    print(txt)
    raise SystemExit(0 if result['ok'] else 1)
if __name__=='__main__':main()
