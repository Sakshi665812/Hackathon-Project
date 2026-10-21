# Project explanation

## The problem

Capacitive pressure-sensor design involves choosing dielectric materials, fillers and their quantities, electrodes, and structural architecture. A user may want sensitivity over a specific pressure interval rather than the highest sensitivity at a single point. Feasible choices also depend on baseline capacitance, nonlinearity, cost, and the conditions under which the materials are characterized.

Searching combinations manually becomes difficult as the catalogue expands. Merely adding a GA does not solve the scientific problem: the search still needs a defensible function that evaluates each proposed recipe.

## What this implementation does

SensorForge is a **catalogue-driven, physics-based evolutionary inverse-design tool**. It turns target properties into candidate compositions using a database maintained by the project owner. A user supplies requirements and can limit the set of database options considered. No dataset upload or model training is required from the user.

The search returns candidate formulations with explicit volume fractions, electrode and architecture choices, modeled pressure responses, scenario-dependent performance, cost estimates, and evidence references. It also reports why designs were rejected and whether the search was exhaustively verified.

## Research question

Within a documented physical model and a characterized catalogue, can constrained evolutionary search efficiently identify discrete sensor designs that meet specified pressure-range and sensitivity requirements while exposing trade-offs in nonlinearity and cost?

A second, distinct question is whether those physical estimates agree with actual fabricated devices. The software addresses the first computational task; the second requires experimental data and validation that have not yet been completed.

## Technical contributions implemented

1. A validated catalogue schema separating matrices, fillers, electrodes, and structures, with provenance and compatibility constraints.
2. A training-free evaluator using explicit mixture and compression assumptions.
3. GA search over material subsets, with discrete loading/architecture enumeration inside each evaluation.
4. Feasibility checks across soft, intermediate, and stiff mechanical scenarios.
5. Fixed-scale weighted ranking and a three-objective Pareto archive.
6. Exhaustive checks on small spaces and honest best-found reporting on larger spaces.
7. Reproducible exports including the catalogue snapshot, hash, targets, seed, model version, and search settings.

These are implementation features, not claims of scientific novelty over existing research.

## Wording suitable for a presentation

> SensorForge is a physics-based evolutionary inverse-design framework for capacitive pressure sensors. It searches an owner-curated catalogue of materials and architectures to identify candidate recipes that satisfy user-defined pressure-range, sensitivity, capacitance, nonlinearity, and cost requirements under explicit modeling assumptions. It reports trade-offs, provenance, and search verification so that proposed designs can be selected for experimental testing.

Do not describe the present application as learning material interactions from experimental curves, as predicting every material family, or as experimentally proving a new combination's performance. Evolutionary optimization can be called evolutionary computation; it does not imply a trained predictor.

## Intended users and responsibilities

- **Catalogue owner/researcher:** gathers measurements and references, checks units, defines compatible conditions and pairings, and maintains the database.
- **Design user:** specifies targets, geometry, permissible ingredients, and trade-off preferences, then examines proposed experiments.
- **Experimental researcher:** fabricates candidates and controls, measures responses, and tests the model's claims.

The current demonstration data establish that the application runs. They do not establish that its recommendations will work in the laboratory.
