"""Explicit dilute dielectric mixing and scalar compression scenarios, without training."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import numpy as np
from .optimization import Evaluation

EPSILON_0 = 8.8541878128e-12  # F/m
MODEL_VERSION = 'dilute-composite-scenarios-v1'


@dataclass(frozen=True)
class Targets:
    pressure_min_kpa: float = 0.
    pressure_max_kpa: float = 10.
    area_cm2: float = 1.
    thickness_um: float = 100.
    min_sensitivity_per_kpa: float = .001
    min_capacitance_pf: float = 1.
    max_nonlinearity_pct: float = 5.
    max_cost: float = 20.
    sensitivity_weight: float = 1.
    linearity_weight: float = 1.
    cost_weight: float = 1.

    def validate(self):
        values = list(asdict(self).values())
        if not np.isfinite(values).all() or min(values) < 0:
            raise ValueError('Targets must be finite and nonnegative.')
        if self.pressure_max_kpa <= self.pressure_min_kpa:
            raise ValueError('Maximum pressure must exceed minimum pressure.')
        if min(self.area_cm2, self.thickness_um, self.min_sensitivity_per_kpa,
               self.min_capacitance_pf, self.max_nonlinearity_pct, self.max_cost) <= 0:
            raise ValueError('Geometry, property thresholds, and budgets must be positive.')
        if self.sensitivity_weight + self.linearity_weight + self.cost_weight <= 0:
            raise ValueError('At least one objective weight must be positive.')


def mixture(matrix: dict, fillers: list[dict], fraction: float, structure: dict):
    """Equal shares of total filler volume. Mechanical scenarios are not confidence bounds."""
    if not 0 <= fraction <= .1 or (not fillers and fraction != 0) or (fillers and fraction <= 0):
        raise ValueError('Invalid total filler volume fraction.')
    share = fraction / len(fillers) if fillers else 0.
    host = matrix['relative_permittivity']
    alpha = sum(share * (f['relative_permittivity']-host) / (f['relative_permittivity']+2*host) for f in fillers)
    epsilon = host * (1 + 2*alpha) / (1-alpha) * structure['permittivity_factor']
    fractions = np.array([1-fraction] + [share]*len(fillers))
    moduli = np.array([matrix['compression_modulus_kpa']] + [f['compression_modulus_kpa'] for f in fillers])
    soft = float(1 / np.sum(fractions / moduli) * structure['modulus_factor'])
    stiff = float(np.dot(fractions, moduli) * structure['modulus_factor'])
    return epsilon, (soft, float(np.sqrt(soft * stiff)), stiff)


def response_metrics(modulus: float, targets: Targets):
    lo, hi = targets.pressure_min_kpa, targets.pressure_max_kpa
    a, b = 1 - lo/modulus, 1 - hi/modulus
    sensitivity = 1 / (modulus * a * b)
    # Analytic maximum chord deviation / full-scale span, in a stable closed form.
    nonlinearity = float(100 * ((hi-lo)/modulus) / (np.sqrt(a)+np.sqrt(b))**2)
    return sensitivity, nonlinearity


def evaluate_design(matrix: dict, fillers: list[dict], electrode: dict, structure: dict,
                    fraction: float, targets: Targets) -> Evaluation:
    targets.validate()
    options = [matrix, *fillers, electrode, structure]
    ids = {row['option_id'] for row in options}
    reasons = []
    if len({row['compatibility_group'] for row in options}) != 1:
        reasons.append('Measurement/compatibility groups differ.')
    for row in options:
        if ids.intersection(row['incompatible_with']):
            reasons.append('Curated incompatibility: ' + row['option_id'])
        if row['role'] != 'matrix' and matrix['option_id'] not in row['allowed_matrices']:
            reasons.append('Matrix pairing is not approved: ' + row['option_id'])
    if any(not row['insulating_spherical'] for row in fillers):
        reasons.append('Conductive or nonspherical fillers are outside the mixing model.')
    if fraction > matrix['max_total_filler_fraction'] + 1e-10:
        reasons.append('Total filler volume exceeds the matrix limit.')
    if fillers and any(fraction/len(fillers) > row['max_volume_fraction'] + 1e-10 for row in fillers):
        reasons.append('Individual filler volume exceeds its catalogue limit.')
    if reasons:
        return Evaluation({}, (1., 1., 1.), 1., {}, tuple(reasons))
    epsilon, moduli = mixture(matrix, fillers, fraction, structure)
    pressure_limit = min(row['max_pressure_kpa'] for row in options)
    strain_limit = min(row['max_strain'] for row in options)
    violations = {}
    if targets.pressure_max_kpa > pressure_limit:
        violations['pressure_outside_characterized_range'] = targets.pressure_max_kpa/pressure_limit - 1
    strain = targets.pressure_max_kpa / min(moduli)
    if strain > strain_limit:
        violations['small_strain_domain_exceeded'] = strain/strain_limit - 1
    if epsilon < 1:
        reasons.append('Effective permittivity falls outside the dielectric model.')
    if violations or reasons:
        return Evaluation({}, (1., 1., 1.), 1., violations, tuple(reasons))
    scenario_metrics = [response_metrics(modulus, targets) for modulus in moduli]
    sensitivities, nonlinearities = zip(*scenario_metrics)
    sensitivity, nonlinearity = min(sensitivities), max(nonlinearities)
    c0 = EPSILON_0 * epsilon * targets.area_cm2*1e-4 / (targets.thickness_um*1e-6) * 1e12
    volume = targets.area_cm2 * targets.thickness_um * 1e-4  # cm³
    material_cost = volume * ((1-fraction)*matrix['cost_per_cm3'] +
                            sum(fraction/len(fillers)*f['cost_per_cm3'] for f in fillers))
    cost = material_cost + targets.area_cm2*(electrode['cost_per_cm2'] + structure['cost_per_cm2'])
    metrics = {'sensitivity_min_per_kpa': sensitivity, 'sensitivity_nominal_per_kpa': sensitivities[1],
               'sensitivity_max_per_kpa': max(sensitivities), 'nonlinearity_max_pct': nonlinearity,
               'baseline_capacitance_pf': c0, 'cost': cost, 'relative_permittivity': epsilon,
               'modulus_soft_kpa': moduli[0], 'modulus_nominal_kpa': moduli[1], 'modulus_stiff_kpa': moduli[2],
               'max_scenario_strain': strain}
    checks = {
        'sensitivity_below_minimum': (targets.min_sensitivity_per_kpa-sensitivity) / targets.min_sensitivity_per_kpa,
        'capacitance_below_minimum': (targets.min_capacitance_pf-c0) / targets.min_capacitance_pf,
        'nonlinearity_above_maximum': (nonlinearity-targets.max_nonlinearity_pct) / targets.max_nonlinearity_pct,
        'cost_above_budget': (cost-targets.max_cost) / targets.max_cost,
    }
    violations = {name: value for name, value in checks.items() if value > 1e-10}
    objectives = (targets.min_sensitivity_per_kpa/(sensitivity+targets.min_sensitivity_per_kpa),
                  nonlinearity/targets.max_nonlinearity_pct, cost/targets.max_cost)
    weights = np.array([targets.sensitivity_weight, targets.linearity_weight, targets.cost_weight])
    return Evaluation(metrics, objectives, float(np.dot(objectives, weights)/weights.sum()), violations)


def response_curve(metrics: dict, targets: Targets, points=101):
    p = np.linspace(targets.pressure_min_kpa, targets.pressure_max_kpa, points)
    result = {'pressure_kpa': p}
    for name, field in [('low', 'modulus_stiff_kpa'), ('nominal', 'modulus_nominal_kpa'), ('high', 'modulus_soft_kpa')]:
        modulus = metrics[field]
        result[f'response_{name}'] = p/(modulus-p)
    result['capacitance_nominal_pf'] = metrics['baseline_capacitance_pf'] * (1+result['response_nominal'])
    return result
