"""Rebuild inputs after altering future observations; current controls must not move."""
import json
import numpy as np
import pandas as pd
from rolling_window import HERE, Inputs, BY_NAME, PRIMARY_NAMES, prequential_scores, choose_week, base


def main():
    inputs=Inputs()
    scores,quantiles=prequential_scores(inputs)
    tests=[]
    for day in (31,151,333):
        load,pv=inputs.load.copy(),inputs.pv.copy()
        load[day:]=load[day:]*1.6+120
        pv[day:]=pv[day:]*.3+100
        changed=Inputs(load,pv)
        other_scores,other_quantiles=prequential_scores(changed)
        selected,last,_=choose_week(day,scores)
        selected_other,last_other,_=choose_week(day,other_scores)
        scenario,w,idx=inputs.scenario_data(day,BY_NAME[selected])
        scenario_other,w_other,idx_other=changed.scenario_data(day,BY_NAME[selected_other])
        a,_,_=inputs.solve_day(day,8550.,BY_NAME[selected])
        b,_,_=changed.solve_day(day,8550.,BY_NAME[selected_other])
        changes=dict(point=float(abs(inputs.point[day]-changed.point[day]).max()),
                     next_day_point=float(abs(inputs.tomorrow[day]-changed.tomorrow[day]).max()),
                     scenario=float(abs(scenario-scenario_other).max()),
                     weights=float(abs(w-w_other).max()),
                     historical_scores=float(np.nanmax(abs(scores[:day]-other_scores[:day]))),
                     current_quantiles=float(abs(quantiles[day]-other_quantiles[day]).max()),
                     decisions=max(float(abs(a[k]-b[k]).max()) for k in ('g','c','d','E')))
        tests.append(dict(day=day,selected=selected,last_observed_day=last,
                          selected_unchanged=selected==selected_other and last==last_other,
                          max_changes=changes,pass_check=selected==selected_other and last==last_other
                          and np.array_equal(idx,idx_other) and max(changes.values())<1e-7))
    # A changing score later in a week may not alter the choice made at its start.
    late_day=35
    edited=scores.copy();edited[31:late_day]=1e12
    frozen=choose_week(late_day,scores)[0]==choose_week(late_day,edited)[0]
    unit=[]
    for weights,expected in [(np.array([.85,.1,.05]),34200.),(np.array([.55,.2,.25]),57600.)]:
        scenario=np.repeat(np.array([100.,200.,400.])[:,None],144,axis=1)
        r=base.solve_horizon(np.full(144,150.),scenario,weights,np.ones(144),6000.,6000.)
        z=r['g']+r['d']-r['c']
        value=float(r['g'].sum()+5*np.sum(weights[:,None]*np.maximum(scenario-z,0)))
        unit.append(dict(weights=weights.tolist(),expected=expected,actual=value,pass_check=abs(value-expected)<1e-6))
    # Paired marginal-distribution identity explains why correlation is not the gain here.
    identity_x=np.array([-20.,0.,13.]);identity_z=np.array([1.,3.,7.])
    err=identity_x-identity_z
    equality=float(abs(identity_z+5*np.maximum(err,0)-identity_x-5*np.where(err>=0,.8*err,-.2*err)).max())
    result=dict(future_perturbations=tests,weekly_choice_locked=bool(frozen),analytical_lp_tests=unit,
                pinball_identity_max_error=equality,
                pass_check=bool(all(r['pass_check'] for r in tests) and frozen and all(r['pass_check'] for r in unit) and equality<1e-10))
    (HERE/'information_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['pass_check']:raise SystemExit(1)


if __name__=='__main__':main()
