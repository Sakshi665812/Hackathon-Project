"""Training-free subset search with cardinality repair and feasibility-first ranking."""
from __future__ import annotations
from dataclasses import dataclass, field
from itertools import combinations
from math import comb
from typing import Callable
import numpy as np


@dataclass
class Evaluation:
    metrics: dict[str, float]
    objectives: tuple[float, ...]  # All minimized, with fixed scales.
    loss: float
    violations: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    @property
    def feasible(self):
        return not self.reasons and all(v <= 1e-10 for v in self.violations.values())

    @property
    def key(self):
        return (0 if self.feasible else 1, sum(self.violations.values()) + len(self.reasons), self.loss)


@dataclass
class SearchResult:
    evaluations: dict[tuple[str, ...], Evaluation]
    history: list[dict]
    metadata: dict

    def feasible(self):
        return sorted(((ids, ev) for ids, ev in self.evaluations.items() if ev.feasible), key=lambda item: (item[1].loss, item[0]))


def space_size(n: int, minimum: int, maximum: int) -> int:
    if not 1 <= minimum <= maximum <= n:
        raise ValueError('Combination sizes must satisfy 1 ≤ minimum ≤ maximum ≤ selected options.')
    return sum(comb(n, r) for r in range(minimum, maximum + 1))


def pareto_indices(objectives: np.ndarray) -> set[int]:
    """Exact nondominance among the evaluated feasible candidates (including ties)."""
    if len(objectives) == 0:
        return set()
    if objectives.shape[1] == 3:
        # Lexicographic sweep + prefix-min tree: O(n log n), including duplicate ties.
        unique, inverse = np.unique(objectives, axis=0, return_inverse=True)
        y_values = np.unique(unique[:, 1])
        tree = np.full(len(y_values) + 1, np.inf)
        nondominated = np.zeros(len(unique), dtype=bool)
        for i, row in enumerate(unique):
            y = int(np.searchsorted(y_values, row[1])) + 1
            cursor, minimum_z = y, np.inf
            while cursor > 0:
                minimum_z = min(minimum_z, tree[cursor])
                cursor -= cursor & -cursor
            # Identical vectors were collapsed; any earlier <= vector is strictly better.
            nondominated[i] = minimum_z > row[2]
            cursor = y
            while cursor < len(tree):
                tree[cursor] = min(tree[cursor], row[2])
                cursor += cursor & -cursor
        return set(np.flatnonzero(nondominated[inverse]).tolist())
    frontier: list[int] = []
    for i in np.argsort(objectives[:, 0], kind='stable'):
        current = objectives[i]
        if frontier:
            prior = objectives[frontier]
            if np.any(np.all(prior <= current, axis=1) & np.any(prior < current, axis=1)):
                continue
            frontier = [j for j in frontier if not (np.all(current <= objectives[j]) and np.any(current < objectives[j]))]
        frontier.append(int(i))
    return set(frontier)


def search(option_ids: list[str], evaluate: Callable[[tuple[str, ...]], Evaluation], *,
           minimum=1, maximum=4, method='ga', seed=42, population=48,
           generations=60, restarts=3, verify_limit=2000, exact_limit=20000,
           evaluation_budget=20000) -> SearchResult:
    ids = sorted(option_ids)
    if len(ids) != len(set(ids)):
        raise ValueError('Option IDs must be unique.')
    total = space_size(len(ids), minimum, maximum)
    if method not in ('ga', 'exact'):
        raise ValueError('Unknown search method.')
    if not 4 <= population <= 256 or not 1 <= generations <= 300 or not 1 <= restarts <= 10:
        raise ValueError('Invalid GA population, generations, or restarts.')
    if not 1 <= evaluation_budget <= 100000 or not 0 <= verify_limit <= exact_limit <= 100000:
        raise ValueError('Invalid search limits.')
    if method == 'exact' and total > min(exact_limit, evaluation_budget):
        raise ValueError(f'Exact search needs {total:,} evaluations; narrow the search space or use GA.')
    cache: dict[tuple[str, ...], Evaluation] = {}
    history = []

    def score(chromosome):
        key = tuple(ids[i] for i in sorted(chromosome))
        if key not in cache:
            result = evaluate(key)
            numbers = [result.loss, *result.objectives, *result.violations.values(), *result.metrics.values()]
            if not np.isfinite(numbers).all() or any(v < 0 for v in result.violations.values()):
                raise ValueError('Evaluator returned invalid or nonfinite values.')
            cache[key] = result
        return cache[key]

    def exhaustive():
        for count in range(minimum, maximum + 1):
            for subset in combinations(range(len(ids)), count):
                score(subset)

    ga_best = None
    if method == 'exact':
        exhaustive()
    else:
        n = len(ids)
        for restart in range(restarts):
            rng = np.random.default_rng(seed + restart)

            def random_subset():
                return frozenset(rng.choice(n, size=int(rng.integers(minimum, maximum + 1)), replace=False).tolist())

            def repair(values):
                values = set(values)
                if len(values) > maximum:
                    values = set(rng.choice(sorted(values), size=maximum, replace=False).tolist())
                if len(values) < minimum:
                    available = sorted(set(range(n)) - values)
                    values.update(rng.choice(available, size=minimum-len(values), replace=False).tolist())
                return frozenset(values)

            members = [random_subset() for _ in range(population)]
            for generation in range(generations + 1):
                evaluated_members = []
                for member in members:
                    key = tuple(ids[i] for i in sorted(member))
                    if key not in cache and len(cache) >= evaluation_budget:
                        continue
                    score(member)
                    evaluated_members.append(member)
                if not evaluated_members:
                    break
                members = sorted(evaluated_members, key=lambda m: (score(m).key, tuple(sorted(m))))
                best = min(cache.values(), key=lambda ev: ev.key)
                history.append({'restart': restart + 1, 'generation': generation,
                                'evaluated': len(cache), 'feasible_found': sum(e.feasible for e in cache.values()),
                                'best_feasible_loss': best.loss if best.feasible else None,
                                'best_constraint_violation': best.key[1]})
                if len(cache) >= min(total, evaluation_budget) or generation == generations:
                    break

                def tournament():
                    contestants = [members[int(i)] for i in rng.integers(0, len(members), size=3)]
                    return min(contestants, key=lambda m: (score(m).key, tuple(sorted(m))))

                # Elitism + uniform crossover + mutation + random immigrants.
                children = members[:max(1, population // 10)]
                while len(children) < population:
                    if rng.random() < .15:
                        children.append(random_subset())
                        continue
                    left, right = tournament(), tournament()
                    child = {i for i in sorted(left | right) if (i in left and i in right) or rng.random() < .5}
                    if rng.random() < .8:
                        gene = int(rng.integers(n))
                        child.symmetric_difference_update({gene})
                        # Swap mutation explores fixed-cardinality spaces efficiently.
                        if minimum == maximum and child:
                            child.symmetric_difference_update({int(rng.integers(n))})
                    children.append(repair(child))
                members = children
            if len(cache) >= min(total, evaluation_budget):
                break
        feasible_losses = [ev.loss for ev in cache.values() if ev.feasible]
        ga_best = min(feasible_losses) if feasible_losses else None
    ga_evaluated = len(cache) if method == 'ga' else 0
    if method == 'ga' and total <= min(verify_limit, evaluation_budget) and len(cache) < total:
        exhaustive()
    feasible_losses = [ev.loss for ev in cache.values() if ev.feasible]
    best = min(feasible_losses) if feasible_losses else None
    certified = len(cache) == total
    return SearchResult(cache, history, {
        'method': method, 'seed': seed, 'population': population, 'generations': generations,
        'restarts': restarts, 'minimum': minimum, 'maximum': maximum, 'option_ids': ids,
        'space_size': total, 'evaluated': len(cache), 'ga_evaluated': ga_evaluated,
        'evaluation_budget': evaluation_budget, 'budget_reached': len(cache) >= evaluation_budget,
        'globally_verified': certified, 'ga_best_loss': ga_best, 'best_loss': best,
        'ga_absolute_optimality_gap': ga_best-best if certified and ga_best is not None and best is not None else None,
        'feasible_count': len(feasible_losses),
        'claim': 'Global optimum for this catalogue, model, and objective.' if certified and best is not None else
                 ('No feasible combination exists within this catalogue and model.' if certified else
                  'Best found among evaluated combinations; global optimality is not established.'),
    })
