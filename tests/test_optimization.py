"""Analytical and search oracles for the training-free optimizer."""
from copy import deepcopy
from dataclasses import replace
from itertools import combinations
import json
import numpy as np
import pytest
from sensorforge.catalog import DEFAULT_DB, fingerprint, read_catalog, validate_options, write_catalog
from sensorforge.composite_physics import EPSILON_0, Targets, evaluate_design, mixture, response_curve, response_metrics
from sensorforge.inverse_design import optimize
from sensorforge.optimization import Evaluation, pareto_indices, search


@pytest.fixture
def options():
    # Read bundled fixtures, never the owner's live database.
    return validate_options(json.loads((DEFAULT_DB.parent/'demo_options.json').read_text()))


def parts(options):
    return tuple(next(row for row in options if row['role']==role) for role in ('matrix','filler','electrode','structure'))


def test_catalog_roundtrip_and_failed_import_preserves_database(options,tmp_path):
    path=tmp_path/'catalog.sqlite3'
    write_catalog(options,path)
    original=fingerprint(read_catalog(path))
    broken=deepcopy(options)
    broken[0]['max_strain']=.5
    with pytest.raises(ValueError):
        write_catalog(broken,path)
    assert fingerprint(read_catalog(path))==original==fingerprint(options)
    broken=deepcopy(options)
    broken[0]['incompatible_with']=['missing']
    with pytest.raises(ValueError):
        validate_options(broken)


def test_unfilled_analytic_capacitance_sensitivity_and_nonlinearity(options):
    matrix,_,electrode,structure=parts(options)
    t=Targets()
    ev=evaluate_design(matrix,[],electrode,structure,0.,t)
    assert ev.feasible
    modulus=matrix['compression_modulus_kpa']*structure['modulus_factor']
    epsilon=matrix['relative_permittivity']*structure['permittivity_factor']
    expected_c0=EPSILON_0*epsilon*(t.area_cm2*1e-4)/(t.thickness_um*1e-6)*1e12
    assert ev.metrics['baseline_capacitance_pf']==pytest.approx(expected_c0)
    assert ev.metrics['sensitivity_min_per_kpa']==pytest.approx(1/(modulus-t.pressure_max_kpa))
    p=np.linspace(t.pressure_min_kpa,t.pressure_max_kpa,200001)
    response=p/(modulus-p)
    chord=np.linspace(response[0],response[-1],len(p))
    numerical=100*np.max(chord-response)/(response[-1]-response[0])
    assert ev.metrics['nonlinearity_max_pct']==pytest.approx(numerical,rel=1e-8)
    curve=response_curve(ev.metrics,t)
    assert curve['response_low'][0]==0
    assert np.allclose(curve['response_low'],curve['response_high'])


def test_nonzero_interval_and_stiff_limit_are_stable():
    t=Targets(pressure_min_kpa=5,pressure_max_kpa=10)
    sensitivity,nonlinearity=response_metrics(300,t)
    expected=((10/290)-(5/295))/5
    assert sensitivity==pytest.approx(expected)
    assert nonlinearity>0
    assert np.isfinite(response_metrics(1e20,t)).all()


def test_permittivity_alone_does_not_create_normalized_sensitivity(options):
    matrix,_,electrode,structure=parts(options)
    a=evaluate_design(matrix,[],electrode,structure,0.,Targets())
    b=evaluate_design(matrix|{'relative_permittivity':2*matrix['relative_permittivity']},[],electrode,structure,0.,Targets())
    assert a.metrics['sensitivity_min_per_kpa']==b.metrics['sensitivity_min_per_kpa']
    assert b.metrics['baseline_capacitance_pf']==pytest.approx(2*a.metrics['baseline_capacitance_pf'])


def test_mixture_endpoints_and_filler_permutation(options):
    matrix,filler,_,structure=parts(options)
    eps,moduli=mixture(matrix,[],0.,structure)
    assert eps==matrix['relative_permittivity']*structure['permittivity_factor']
    assert moduli[0]==pytest.approx(moduli[2])
    identical=matrix|{'option_id':'identical'}
    eps2,moduli2=mixture(matrix,[identical],.1,structure)
    assert eps2==pytest.approx(eps)
    assert moduli2==pytest.approx(moduli)
    filler2=next(row for row in options if row['role']=='filler' and row['option_id']!=filler['option_id'])
    a=mixture(matrix,[filler,filler2],.1,structure)
    b=mixture(matrix,[filler2,filler],.1,structure)
    assert a[0]==pytest.approx(b[0])
    assert a[1]==pytest.approx(b[1])


def test_domain_compatibility_and_targets_are_hard_constraints(options):
    m,f,e,s=parts(options)
    t=Targets()
    assert not evaluate_design(m,[f|{'insulating_spherical':False}],e,s,.05,t).feasible
    assert not evaluate_design(m,[f],e,s,.05,replace(t,pressure_max_kpa=100)).feasible
    assert not evaluate_design(m,[f],e|{'allowed_matrices':[]},s,.05,t).feasible
    assert not evaluate_design(m,[f],e,s|{'incompatible_with':[f['option_id']]},.05,t).feasible
    ev=evaluate_design(m,[f],e,s,.05,replace(t,min_sensitivity_per_kpa=1))
    assert not ev.feasible and 'sensitivity_below_minimum' in ev.violations
    assert not evaluate_design(m,[f],e,s,.05,replace(t,max_cost=.01)).feasible
    with pytest.raises(ValueError):
        replace(t,sensitivity_weight=0,linearity_weight=0,cost_weight=0).validate()


def oracle(ids):
    # Known exact unique optimum at {b,d}; b is mandatory for feasibility.
    loss=float(len(set(ids)^{'b','d'}))
    return Evaluation({'cost':loss},(loss,),loss,{} if 'b' in ids else {'missing_b':1.})


def test_exact_search_against_independent_exhaustive_oracle():
    ids=list('abcdef')
    r=search(ids,oracle,minimum=2,maximum=3,method='exact')
    expected=[(subset,oracle(subset)) for k in (2,3) for subset in combinations(ids,k)]
    assert len(r.evaluations)==len(expected)==35
    assert r.feasible()[0][0]==('b','d')
    assert r.metadata['globally_verified']


def test_ga_cardinality_reproducibility_and_exact_certificate():
    kw=dict(minimum=2,maximum=3,seed=17,population=12,generations=5,restarts=2,verify_limit=100)
    a=search(list('abcdef'),oracle,**kw)
    b=search(list('abcdef'),oracle,**kw)
    assert a.metadata==b.metadata
    assert a.history==b.history
    assert all(2<=len(key)<=3 for key in a.evaluations)
    assert a.feasible()[0][0]==('b','d')
    assert a.metadata['ga_absolute_optimality_gap'] is not None
    assert a.metadata['globally_verified']


def test_ga_does_not_claim_exhaustive_without_coverage():
    r=search(list('abcdefghijklmnop'),oracle,minimum=4,maximum=8,population=8,generations=1,restarts=1,verify_limit=0)
    assert not r.metadata['globally_verified']
    assert r.metadata['ga_absolute_optimality_gap'] is None
    assert 'not established' in r.metadata['claim']


def test_single_possible_subset_and_pareto_ties():
    r=search(['a'],lambda _:Evaluation({},(1.,),1.),minimum=1,maximum=1)
    assert r.metadata['evaluated']==1
    assert r.metadata['globally_verified']
    values=np.array([[1,2],[1,2],[2,3],[2,1],[3,1]])
    assert pareto_indices(values)=={0,1,3}


def test_end_to_end_exact_recipe_grid_and_owner_subset(options):
    m,f,e,s=parts(options)
    selected=[row['option_id'] for row in (m,f,e,s)]
    result=optimize(options,selected,Targets(),minimum=2,maximum=2,method='exact',loadings=(.02,.05))
    assert result.report['possible_design_settings']==2
    assert result.report['evaluated_design_settings']==2
    assert not result.table.empty
    assert result.report['globally_verified']
    for design in result.designs.values():
        assert sum(design['volume_fractions'].values())==pytest.approx(1.)
        assert set(c['option_id'] for c in design['components'])<=set(selected)
    assert all(result.table.sensitivity_min_per_kpa>=Targets().min_sensitivity_per_kpa)
    assert all(result.table.nonlinearity_max_pct<=Targets().max_nonlinearity_pct)


def test_infeasible_request_is_not_returned_as_recommendation(options):
    result=optimize(options,[row['option_id'] for row in options],Targets(min_sensitivity_per_kpa=10),minimum=2,maximum=2,method='exact')
    assert result.table.empty
    assert result.report['globally_verified']
    assert 'No feasible' in result.report['claim']
    assert result.report['rejection_counts']['sensitivity_below_minimum']>0


def test_three_objective_frontier_matches_pairwise_oracle_with_ties():
    rng=np.random.default_rng(17)
    values=rng.integers(0,10,size=(200,3)).astype(float)
    expected={i for i,row in enumerate(values)
              if not np.any(np.all(values<=row,axis=1)&np.any(values<row,axis=1))}
    assert pareto_indices(values)==expected


def test_all_fillers_mode_keeps_one_matrix_and_every_allowed_filler(options):
    fillers={row['option_id'] for row in options if row['role']=='filler'}
    count=len(fillers)+1
    result=optimize(options,[row['option_id'] for row in options],Targets(),
                    minimum=count,maximum=count,method='exact')
    assert not result.table.empty
    assert result.report['possible_design_settings']==36
    for design in result.designs.values():
        assert set(design['filler_ids'])==fillers
        assert len(design['volume_fractions'])==count
