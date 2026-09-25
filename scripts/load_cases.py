"""Validate declared load pairing. Metadata consistency is not a rule approval."""
import math

def validate_case(c):
    for key in ['condition','basis','combination_mode','inside_kind']:
        if not isinstance(c.get(key),str)or not c[key].strip():raise ValueError('Load case needs '+key)
    for key in ['inside_kpa','outside_kpa']:
        v=c.get(key)
        if isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)or v<0:raise ValueError('Invalid '+key)
    if c['inside_kind']not in ['case_value','envelope']:raise ValueError('inside_kind must be case_value or envelope')
    if c['combination_mode']=='no_counterpressure':
        if c['outside_kpa']!=0:raise ValueError('no_counterpressure requires outside_kpa=0')
        return
    if c['combination_mode']!='coincident':raise ValueError('Use no_counterpressure or coincident')
    if c['inside_kind']!='case_value':raise ValueError('Cannot subtract a wave value from an independent internal envelope')
    for key in ['inside_state','outside_state']:
        state=c.get(key,{})
        for name in ['case_id','point_id','phase_id']:
            if not isinstance(state.get(name),str)or not state[name].strip():raise ValueError(f'{key} needs {name}')
        for name in ['draft_m','z_m']:
            v=state.get(name)
            if isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v):raise ValueError(f'{key} needs numeric {name}')
    a,b=c['inside_state'],c['outside_state']
    for key in ['case_id','point_id','phase_id','draft_m','z_m']:
        if a[key]!=b[key]:raise ValueError('Pressure pair mismatch: '+key)
    if not c.get('combination_basis'):raise ValueError('Need source/derivation for simultaneous pressure pairing')
