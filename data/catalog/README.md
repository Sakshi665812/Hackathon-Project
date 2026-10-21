# Owner-maintained design catalogue

The app reads `options.sqlite3` in read-only mode. Users supply desired properties and choose allowed entries; they do not upload data or train models.

To supply real entries, copy `demo_options.json` to a JSON file in this project, replace its synthetic records with characterized options, and run from the project root:

```bash
.venv/bin/python scripts/manage_catalog.py data/catalog/my_options.json --check
.venv/bin/python scripts/manage_catalog.py data/catalog/my_options.json
```

The second command transactionally **replaces the current catalogue** with the validated records. Back up an existing real catalogue before intentionally replacing it. A failed validation leaves the database unchanged. The app rereads the database on rerun and invalidates displayed results when the catalogue changes. To load the bundled demonstration intentionally:

```bash
.venv/bin/python scripts/manage_catalog.py data/catalog/demo_options.json
```

Every record needs `option_id`, `name`, `role`, `evidence_kind`, `source`, `conditions`, `compatibility_group`, `max_pressure_kpa`, and `max_strain`. IDs are unique. Role is `matrix`, `filler`, `electrode`, or `structure`. Evidence kind is `demonstration`, `measured`, or `literature`. Supply actual source references and conditions, not just a material name. Entries in a recipe must share a compatibility group; groups should encode compatible measurement conditions, fabrication context, and approved geometry assumptions.

| Role | Additional required properties | Units / meaning |
|---|---|---|
| matrix | `relative_permittivity`, `compression_modulus_kpa`, `cost_per_cm3`, `max_total_filler_fraction` | Dimensionless εr; scalar compression modulus in kPa; common cost unit per cm³; volume fraction ≤0.1 |
| filler | `relative_permittivity`, `compression_modulus_kpa`, `cost_per_cm3`, `max_volume_fraction`, `insulating_spherical` | Same units; `insulating_spherical` must be explicit true/false; false entries are not supported by this evaluator |
| electrode | `cost_per_cm2` | Cost of **both electrodes** per cm² of active area; ideal electrodes in the calculation |
| structure | `modulus_factor`, `permittivity_factor`, `cost_per_cm2` | Positive dimensionless factors and incremental fabrication cost per cm²; must have documented applicability |

Every non-matrix record needs a nonempty `allowed_matrices` list of existing matrix IDs. This is an owner-approved pairing rule, not a chemical compatibility prediction. `incompatible_with` optionally lists other IDs; exclusion in either direction is sufficient. All IDs must exist in the import. `max_strain` is a fraction in (0, 0.1]; positive pressure limits are kPa. Numerical fields must be finite; cost may be zero. Moduli must be compression moduli appropriate to the assumed boundary conditions, not blindly substituted tensile Young's moduli. Missing required properties prevent import rather than being guessed.

The catalogue should use a consistent temperature, measurement frequency, unit system, and cost basis. Owner verification of source interpretation and transferability remains necessary. A source text alone does not establish that a record is experimentally verified.

`demo_options.json` contains 3 matrices, 5 insulating fillers, 2 electrode pairs, and 2 architectures, all **invented for software testing**. It is not based on the public literature curves supplied earlier. Do not relabel these numbers as real material measurements.
