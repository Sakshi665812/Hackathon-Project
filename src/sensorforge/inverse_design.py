"""Nested architecture/loading enumeration with GA search over material subsets."""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
from math import comb
import json
import platform
import numpy as np
import pandas as pd
from .catalog import fingerprint, validate_options
from .composite_physics import MODEL_VERSION, Targets, evaluate_design
from .optimization import Evaluation, pareto_indices, search


@dataclass
class DesignResult:
    table: pd.DataFrame
    history: pd.DataFrame
    report: dict
    designs: dict


def optimize(options: list[dict], selected_ids: list[str], targets: Targets, *,
             minimum=2, maximum=4, loadings=(.02, .05, .1), method='ga', seed=42,
             population=48, generations=50, restarts=3, verify_limit=2000) -> DesignResult:
    options = validate_options(options)
    targets.validate()
    lookup = {row['option_id']: row for row in options}
    if len(selected_ids) != len(set(selected_ids)) or set(selected_ids) - lookup.keys():
        raise ValueError('Selected IDs must be unique options from the catalogue.')
    chosen = [lookup[key] for key in sorted(selected_ids)]
    roles = {role: [row for row in chosen if row['role'] == role] for role in ('matrix','filler','electrode','structure')}
    if any(not roles[role] for role in ('matrix', 'electrode', 'structure')):
        raise ValueError('Select at least one matrix, electrode, and architecture.')
    if not 1 <= minimum <= maximum <= len(roles['filler']) + 1:
        raise ValueError('Constituent count includes one matrix plus the selected fillers.')
    loadings = tuple(sorted(set(float(x) for x in loadings)))
    if not loadings or not np.isfinite(loadings).all() or min(loadings) <= 0 or max(loadings) > .1 or len(loadings) > 10:
        raise ValueError('Choose 1–10 positive filler volume fractions, each at most 0.1.')
    contexts = len(roles['electrode']) * len(roles['structure']) * len(loadings)
    if contexts > 100:
        raise ValueError('Narrow electrode, architecture, or loading selections to at most 100 settings per material set.')
    records, designs, rejected = [], {}, Counter()
    evaluated_designs = 0

    def evaluate_subset(ids):
        nonlocal evaluated_designs
        material_options = [lookup[key] for key in ids]
        matrices = [row for row in material_options if row['role'] == 'matrix']
        if len(matrices) != 1:
            return Evaluation({}, (1.,1.,1.), 1., {}, ('A recipe requires exactly one matrix.',))
        matrix = matrices[0]
        fillers = [row for row in material_options if row['role'] == 'filler']
        best = None
        for electrode, structure, fraction in product(roles['electrode'], roles['structure'], loadings if fillers else (0.,)):
            evaluation = evaluate_design(matrix, fillers, electrode, structure, fraction, targets)
            evaluated_designs += 1
            if best is None or evaluation.key < best.key:
                best = evaluation
            if not evaluation.feasible:
                rejected.update(evaluation.reasons)
                rejected.update(evaluation.violations.keys())
                continue
            recipe = {'matrix_id': matrix['option_id'], 'filler_ids': [f['option_id'] for f in fillers],
                      'electrode_id': electrode['option_id'], 'structure_id': structure['option_id'],
                      'total_filler_volume_fraction': fraction,
                      'volume_fractions': {matrix['option_id']: 1-fraction} | {f['option_id']: fraction/len(fillers) for f in fillers}}
            identifier = sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
            components = [matrix, *fillers, electrode, structure]
            row = {'design_id': identifier, 'matrix': matrix['name'],
                   'fillers': ' + '.join(f['name'] for f in fillers) or 'Unfilled',
                   'electrode': electrode['name'], 'architecture': structure['name'],
                   'constituents': len(ids), 'filler_volume_pct': 100*fraction,
                   'loss': evaluation.loss, **evaluation.metrics,
                   'evidence': 'DEMONSTRATION' if any(c['evidence_kind']=='demonstration' for c in components) else 'Model hypothesis; not combination-validated',
                   'sensitivity_objective': evaluation.objectives[0], 'linearity_objective': evaluation.objectives[1],
                   'cost_objective': evaluation.objectives[2]}
            records.append(row)
            designs[identifier] = recipe | {'components': components, 'metrics': evaluation.metrics}
        return best

    material_ids = [row['option_id'] for row in chosen if row['role'] in ('matrix','filler')]
    result = search(material_ids, evaluate_subset, minimum=minimum, maximum=maximum,
                    method=method, seed=seed, population=population, generations=generations,
                    restarts=restarts, verify_limit=verify_limit,
                    evaluation_budget=min(20000, 100000//contexts))
    table = pd.DataFrame(records)
    if not table.empty:
        table = table.sort_values(['loss','design_id']).reset_index(drop=True)
        front = pareto_indices(table[['sensitivity_objective','linearity_objective','cost_objective']].to_numpy())
        table['pareto'] = [i in front for i in table.index]
        table.insert(0, 'rank', np.arange(1,len(table)+1))
    valid_sets = len(roles['matrix']) * sum(comb(len(roles['filler']),r-1) for r in range(minimum,maximum+1))
    setting_count = len(roles['matrix']) * len(roles['electrode']) * len(roles['structure']) * sum(
        comb(len(roles['filler']),r-1)*(1 if r==1 else len(loadings)) for r in range(minimum,maximum+1))
    report = result.metadata | {'model_version': MODEL_VERSION, 'catalogue_sha256': fingerprint(options),
        'targets': asdict(targets), 'selected_ids': sorted(selected_ids), 'loadings': list(loadings),
        'catalogue_snapshot': options, 'python_version': platform.python_version(), 'numpy_version': np.__version__,
        'valid_material_sets_before_physical_checks': valid_sets,
        'possible_design_settings': setting_count, 'evaluated_design_settings': evaluated_designs,
        'feasible_design_settings': len(records), 'rejection_counts': dict(rejected),
        'evidence_status': 'Contains synthetic demonstration data' if any(o['evidence_kind']=='demonstration' for o in chosen) else 'Constituent provenance only; combinations require experiments',
        'assumptions': ['Dilute insulating spherical fillers; total volume fraction ≤ 10%.',
            'Equal filler shares within each total loading; no continuous ratio optimization.',
            'Scalar harmonic/geometric/arithmetic compression scenarios are not statistical confidence bounds.',
            'Constant effective permittivity and electrode area; ≤10% strain and catalogue-specific limits.',
            'Architecture factors are supplied by the catalogue owner and assumed transferable only within approved pairings.',
            'Electrodes affect cost and compatibility; this ideal model has no electrode-induced sensitivity gain.',
            'All targets pass all three specified mechanical scenarios, not every possible real material behavior.'],
        'software': 'SensorForge catalogue optimization v1'}
    return DesignResult(table, pd.DataFrame(result.history), report, designs)
