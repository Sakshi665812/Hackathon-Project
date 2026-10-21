# End-to-end workflow

## 1. Owner prepares the database

The owner reviews sources and creates catalogue JSON records. The CLI checks required fields, finite numerical values, units represented by field names, role definitions, loading/strain limits, IDs, and compatibility references. Successful import transactionally installs the records in SQLite.

The app reads the database without writing to it. Source references are visible, but a successful schema check does not verify the scientific correctness of a paper extraction.

## 2. User defines the search space

On **Design optimizer**, the user optionally limits matrices, fillers, electrode pairs, and architectures using multiselect dropdowns. Selecting t entries restricts search to those entries from the k stored options. At least one matrix, electrode, and architecture must be allowed. Fillers can be omitted for an unfilled-matrix search.

A candidate includes one matrix, a filler subset, one electrode pair, and one architecture. Example: exactly three constituents means one matrix plus two fillers. Electrodes and architecture are not counted as material constituents. “Use all allowed fillers” uses every chosen filler with one matrix at a time, even when several matrices are available.

## 3. User supplies properties and limits

| Input | Meaning |
|---|---|
| Minimum / maximum pressure | Required compression interval in kPa |
| Minimum sensitivity | Required interval-average slope of ΔC/C₀, in kPa⁻¹ |
| Minimum baseline capacitance | C₀ at zero pressure, in pF |
| Maximum nonlinearity | Maximum endpoint-chord deviation as % of full-scale response |
| Maximum cost | Budget in the catalogue's consistent cost unit |
| Area and thickness | Fixed active area in cm² and dielectric thickness in µm |
| Constituent count | Exact count, permitted count range, or all allowed fillers |
| Filler loading grid | Permitted total filler volume percentages, up to 10% |

A total 5 vol% loading with two fillers means 2.5 vol% of each filler and 95 vol% matrix. It does not mean 5% of each. Weight fractions cannot be substituted for these volume fractions.

## 4. User selects search preferences

Sensitivity, linearity, and cost weights determine ranking **after** hard constraints are satisfied. Setting a weight to zero does not turn off the corresponding hard limit. At least one weight must be positive.

The default GA has a seed, population, generation count, and restart count. Equal seeds and inputs reproduce the computation in the same software environment. Larger search settings can explore more candidates but cannot guarantee the global optimum without exhaustive coverage.

Exact enumeration is available within resource limits. The optional small-space verifier enumerates up to 2,000 material subsets after the GA, subject to the evaluation budget. Electrodes, architectures, and loading levels are enumerated for each visited valid material subset.

## 5. Calculation and rejection

The evaluator checks pairing approvals, common conditions/compatibility groups, excluded pairs, filler type and loading, characterized pressure limits, and small-strain validity. It then computes mixture permittivity and three compression scenarios. Every reported design must meet targets across the stated scenarios.

Unsupported designs are rejected instead of being extrapolated through invalid equations. For example, conductive fillers are not treated as insulating spheres just to produce a number.

## 6. Read the output

- **Ranked feasible designs:** recipe identities, filler fraction, scenario-minimum sensitivity, C₀, scenario-maximum nonlinearity, cost, weighted loss, and Pareto status.
- **Pareto alternatives:** designs for which no evaluated feasible design is at least as good in all three ranking properties and strictly better in one. This is a three-property comparison even though the scatter plot shows only sensitivity and cost.
- **Response curves:** nominal ΔC/C₀ and a band spanning the specified mechanical scenarios. The band is not a confidence interval.
- **Recipe and evidence:** actual constituent volume fractions, fixed geometry, chosen electrode/architecture, and each option's provenance.
- **Search diagnostics:** convergence, evaluation counts, rejection counts, and the exact-verification status. Rejection counts overlap when a design violates several conditions.

“Global optimum” means an optimum of the discrete selected problem and its modeling assumptions, not the best possible sensor in nature. For sampled spaces, “no feasible design found” does not prove that none exists.

## 7. Export and validate experimentally

The CSV download contains all feasible evaluated designs, although the on-screen table shows only the top 200. The inspection dropdown contains the top 100. A selected curve can be downloaded separately.

The JSON report includes the catalogue snapshot and hash, chosen IDs, targets, loading grid, software/model versions, seed and GA settings, search diagnostics, results, and feasible recipe details. Save it with the associated experimental plan.

The next scientific step is to fabricate selected candidates and an unfilled control, characterize independent replicates under matched conditions, and compare measurements against the calculations. The application does not automatically perform that validation.
