## Scientific scope

SensorForge searches an owner-curated catalogue for capacitive pressure-sensor compositions and architectures that satisfy user-defined pressure, sensitivity, baseline-capacitance, nonlinearity, and cost requirements. The current application uses **no fitted model and no training step**. Its scientific contribution is a reproducible constrained search with explicit physical assumptions, mechanical scenario checks, and an audit of search optimality.

A defensible description is: “A physics-based evolutionary inverse-design framework uses curated constituent properties and compatibility rules to screen dielectric compositions and sensor architectures against user-defined performance requirements.” The phrase “learns from experimental responses” does not describe this implementation. That would require an additional fitting and independent validation workflow.

## Design variables

Each recipe contains one matrix, zero or more fillers, one electrode pair, and one architecture. Users can restrict each category to a subset of the database. The constituent-count limit includes the matrix and fillers; electrodes and architecture are separate choices. All-filler mode uses every allowed filler with one allowed matrix at a time. Each ingredient appears once.

The optimizer searches a discrete list of total filler volume fractions. For a recipe with m fillers and total filler fraction φ, each filler occupies φ/m and the matrix occupies 1−φ. Fractions are **volume fractions**, not mass fractions. Equal filler shares are a deliberate first-version restriction; unequal ratios and continuous geometry optimization are not implemented.

Catalogue entries carry provenance, measurement conditions, a common compatibility/measurement group, allowable matrix pairings, optional explicit exclusions, and operating limits. These are owner-curated claims, not compatibility discovered by the optimizer. Individual approved pairings do not establish multi-filler chemical compatibility. In particular, dispersion, adhesion, and multi-filler interactions still require experiments.

## Forward calculation

For dilute, electrically insulating spherical fillers in a matrix of relative permittivity εm, define

$$a=\sum_i\phi_i\frac{\epsilon_i-\epsilon_m}{\epsilon_i+2\epsilon_m},\qquad
\epsilon_{mix}=\epsilon_m\frac{1+2a}{1-a}.$$

This is a multicomponent Maxwell–Garnett screening approximation. The implementation caps total filler volume at 10%, and respects any stricter catalogue limit. This cap is a practical domain restriction, **not a theorem guaranteeing validity**. Conductive and nonspherical fillers are excluded. Clustering, interfacial polarization, dielectric loss, percolation, and pressure-dependent permittivity are not resolved. See [Markel, Maxwell Garnett approximation in random media](https://doi.org/10.1364/JOSAA.450850) for the approximation and its limitations.

For supplied scalar compression moduli Ki and phase fractions vi, the mechanical scenarios are

$$K_{soft}=\left(\sum_i v_i/K_i\right)^{-1},\qquad
K_{stiff}=\sum_i v_i K_i,\qquad
K_{mid}=\sqrt{K_{soft}K_{stiff}}.$$

These represent scalar uniform-stress and uniform-strain idealizations and an intermediate scenario. They are **not rigorous tensor-elastic bounds for arbitrary microstructures, measured uncertainty bounds, or statistical confidence intervals**. Catalogue architecture factors multiply the modulus and baseline permittivity; transferring those factors to an unseen composition is an explicit modeling assumption. Large-strain, contact-area, buckling, and pore-collapse effects are outside this model.

Using constant area A, zero-pressure dielectric thickness d₀, and one scenario modulus K,

$$d(P)=d_0(1-P/K),\qquad
C(P)=\frac{\epsilon_0\epsilon_{eff}A}{d_0(1-P/K)},\qquad
\frac{\Delta C}{C_0}=\frac{P}{K-P}.$$

Every design must stay within all catalogue pressure limits and the strictest permitted strain, never exceeding 10%, even in the soft scenario. Geometry is supplied by the user; catalogue factors must be applicable to that geometry and the stated measurement conditions. Electrode options affect compatibility and estimated cost. They are ideal equipotential surfaces in this model and do not create an invented sensitivity gain.

**Constant permittivity cancels from ΔC/C₀.** Raising ε alone increases baseline and absolute capacitance but does not improve normalized sensitivity in this model. A filler that stiffens a matrix can reduce normalized sensitivity. The application deliberately exposes this trade-off; it does not invent synergistic improvements from adding ingredients. Real microstructured sensors can change both area and permittivity under pressure, as investigated in [this experimental composite-dielectric study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8880179/); those mechanisms would require a more detailed validated evaluator.

## Metrics and feasibility

Sensitivity is the secant slope of ΔC/C₀ over the entire requested interval [Pmin, Pmax], in kPa⁻¹, not a cherry-picked local peak. The baseline is always at zero pressure, even when Pmin > 0.

Nonlinearity is the maximum deviation from the endpoint chord, divided by the full-scale response span and expressed as a percentage. Its maximum is evaluated analytically, rather than estimated from a sparse grid. It is not an R² statistic. Cost is the volume-weighted constituent cost plus electrode-pair and architecture costs. All costs must use the same currency or catalogue unit; the demonstration uses arbitrary units. It omits manufacturing costs not included in those entries.

A candidate is feasible only if its **minimum scenario sensitivity**, baseline capacitance, **maximum scenario nonlinearity**, and cost satisfy all user thresholds, and all compatibility/domain checks pass. This means robustness to the three stated scenarios, not robustness to every possible real material behavior. No hysteresis, lifetime, response-time, or breakdown predictions are made from missing data.

Among feasible designs, the minimized objective is

$$L=\frac{w_S[S_{target}/(S_{min}+S_{target})]+w_N[N_{max}/N_{limit}]+w_C[c/c_{budget}]}{w_S+w_N+w_C}.$$

Scales come from fixed user targets, not the range of sampled candidates. Weights express user preferences and do not change feasibility. The Pareto comparison uses maximum sensitivity, minimum nonlinearity, and minimum cost among all feasible designs actually evaluated. A weighted objective may select only some Pareto solutions; this is a single-objective GA with a post-search Pareto archive, **not NSGA-II**.

## Search and verification

The GA uses a material-subset chromosome, cardinality repair, tournament selection, uniform crossover, mutation, elitism, random immigrants, and deterministic seeded restarts. For every visited material subset containing exactly one matrix, the evaluator enumerates the allowed electrodes, architectures, and loading levels. Invalid role combinations cannot become recommendations.

Feasible candidates outrank infeasible candidates. Infeasible candidates are ordered by normalized constraint violations plus domain-rejection counts; feasible ones are ordered by weighted loss. This follows the [feasibility-first principle](https://pymoo.org/constraints/feas_first.html). Restarts use consecutive seeds and share an evaluation archive. Their convergence curves are diagnostic, not independent statistical trials.

Small spaces can be fully enumerated after the GA. The report then gives the absolute weighted-loss gap between the GA result and the exact result. A “global optimum” claim is restricted to the selected **discrete** catalogue, loading grid, fixed geometry, model assumptions, and objective. For larger spaces, results are explicitly “best found”; finding no feasible design does not prove infeasibility. The Pareto frontier is global only when the corresponding search is exhaustive.

The reported material-subset space includes invalid multi-matrix subsets used by the encoding. The report separately counts structurally valid material sets and full design settings. Search has a resource budget; expanding a catalogue can require narrower filters. A result export records the catalogue hash, chosen option IDs, full recipe/provenance for each feasible design, targets, grid, model version, seed, search settings, rejection counts, and convergence.

## Evidence and research validation

The bundled catalogue contains **synthetic demonstration descriptors**, deliberately not named after real materials. It demonstrates computation, not sensor performance. Public curve samples retained under `data/examples` are not automatically converted into constituent properties: whole-device ΔC curves cannot determine independent permittivity, modulus, compatibility, or composition.

An untested recipe remains a model hypothesis even when every constituent has a literature source. A database absence is not proof of literature novelty. To support scientific claims, populate the catalogue with documented, matched-condition measurements; compare calculated and measured responses on combinations not used to choose the assumptions; and fabricate independent replicates of proposed designs. Report curve errors, sensitivity errors, target-achievement rates, and scenario-envelope failures. Compare GA versus exact search on small spaces and random search at equal evaluation budgets on larger spaces. These experimental and algorithm benchmarks are proposed research work, not completed validation claims.
