# Setup and operation

## Environment

Use Python 3.11 or newer and run commands from the repository root. The supported workflow is an **editable source-checkout installation**: the code resolves `data/` and `docs/` relative to the checkout. A standalone wheel without those assets is not a supported deployment format.

Runtime dependencies are NumPy, pandas, Streamlit, and Plotly. SQLite is part of Python. The `test` extra installs pytest; the `data` extra installs openpyxl for inspecting Excel reference data. CatBoost, scikit-learn, PyTorch, GPUs, API keys, and external accounts are not required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,data]'
```

If `venv` reports that `ensurepip` is unavailable, the machine needs its Python venv support installed by its administrator, or pip bootstrapped using an existing pip installation. Do not copy another project's virtual environment: it contains environment-specific paths. For a partially created environment and an existing working pip interpreter, pip supports:

```bash
/path/to/working/python -m pip --python .venv/bin/python install pip -e '.[test,data]'
```

## Initialize the catalogue

```bash
python scripts/manage_catalog.py data/catalog/demo_options.json --check
python scripts/manage_catalog.py data/catalog/demo_options.json
```

The first command validates without writing. The second replaces the operational catalogue at `data/catalog/options.sqlite3` inside a transaction. Use it for an intentional first setup or reset. For real data, substitute your reviewed JSON file; back up an existing real database before replacing it.

Database files are ignored by Git. The portable data source is the reviewed JSON. The app does not silently create a demo database when a real database is absent.

## Run and stop

```bash
python -m streamlit run app.py
```

Open http://localhost:8501. Stop with Ctrl+C. If port 8501 is occupied, use `--server.port 8502`.

On a remote machine, the browser needs access to the server's port; use your normal SSH forwarding arrangement, for example `ssh -L 8501:localhost:8501 user@host`. The app is a local research tool without an authentication layer; public multiuser hosting would require additional deployment work.

## Verify

```bash
python -m pytest -q
python -m pip check
python scripts/manage_catalog.py data/catalog/demo_options.json --check
```

Tests use bundled fixtures and temporary catalogues rather than modifying the owner's operational data. Temporary pytest files go into `.tmp/pytest` in this checkout.

## Reproduce dependency versions

`requirements-lock.txt` records the exact installed distributions from the validated clean environment. It is a version snapshot, not a cross-platform hash-locked resolver file. For the same Python/platform family:

```bash
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

After deliberately updating dependencies, rerun tests and refresh the snapshot. Do not copy the original project's lockfile: it includes legacy training packages that this application no longer uses.

## Common problems

| Symptom | Action |
|---|---|
| `No module named sensorforge` | Activate this checkout's environment and run `python -m pip install -e .` |
| Missing catalogue | Install a reviewed JSON catalogue using `manage_catalog.py` |
| Only demonstration entries appear | Real entries have not yet been installed; the literature workbook is not automatically imported |
| No feasible designs | Read rejection diagnostics, inspect model-domain limits, and review targets or selections |
| All options disappear after evidence filtering | The catalogue contains only demonstration entries |
| Exact search exceeds limits | Narrow the allowed options/loading grid or use GA |
| Results disappear after changing selections | Run optimization again; stale results are intentionally hidden |
| Excel workbook does not populate options | It is reference data with a different schema; follow the data preparation guide |
