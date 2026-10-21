"""Owner-maintained SQLite catalogue of matrix, filler, electrode, and structure options."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import math
import sqlite3
from .config import ROOT

DEFAULT_DB = ROOT / 'data/catalog/options.sqlite3'
ROLES = ('matrix', 'filler', 'electrode', 'structure')
COMMON_TEXT = ('option_id', 'name', 'role', 'evidence_kind', 'source', 'conditions', 'compatibility_group')
ROLE_NUMBERS = {
    'matrix': ('relative_permittivity', 'compression_modulus_kpa', 'cost_per_cm3', 'max_total_filler_fraction'),
    'filler': ('relative_permittivity', 'compression_modulus_kpa', 'cost_per_cm3', 'max_volume_fraction'),
    'electrode': ('cost_per_cm2',),  # Cost of the pair, not a single electrode.
    'structure': ('modulus_factor', 'permittivity_factor', 'cost_per_cm2'),
}


def validate_options(options: list[dict]) -> list[dict]:
    if not isinstance(options, list) or not options:
        raise ValueError('Catalogue must be a nonempty JSON list of options.')
    normalized, identifiers = [], set()
    for row in options:
        if not isinstance(row, dict):
            raise ValueError('Each option must be an object.')
        item = {}
        for field in COMMON_TEXT:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Each option needs nonempty {field}.')
            item[field] = value.strip()
        if item['option_id'] in identifiers:
            raise ValueError('Duplicate option_id: ' + item['option_id'])
        identifiers.add(item['option_id'])
        if item['role'] not in ROLES:
            raise ValueError('Unknown option role: ' + item['role'])
        if item['evidence_kind'] not in ('demonstration', 'measured', 'literature'):
            raise ValueError('evidence_kind must be demonstration, measured, or literature.')
        for field in (*ROLE_NUMBERS[item['role']], 'max_pressure_kpa', 'max_strain'):
            if isinstance(row.get(field), bool):
                raise ValueError(f'{field} must be numeric, not boolean.')
            try:
                value = float(row[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f'{field} is required and must be numeric.') from exc
            if not math.isfinite(value) or value < 0 or (not field.startswith('cost_') and value == 0):
                raise ValueError(f'{field} must be finite and positive (cost may be zero).')
            item[field] = value
        if item['max_strain'] > .1:
            raise ValueError('This linear compression model requires max_strain ≤ 0.1.')
        if item['role'] in ('matrix', 'filler') and item['relative_permittivity'] < 1:
            raise ValueError('The quasistatic dielectric model requires relative_permittivity ≥ 1.')
        if item['role'] in ('matrix', 'filler'):
            field = 'max_total_filler_fraction' if item['role'] == 'matrix' else 'max_volume_fraction'
            if item[field] > .1:
                raise ValueError('This dilute-mixture screening model restricts filler fractions to ≤ 0.1.')
        if item['role'] == 'filler':
            if not isinstance(row.get('insulating_spherical'), bool):
                raise ValueError('Each filler needs an explicit insulating_spherical boolean.')
            item['insulating_spherical'] = row['insulating_spherical']
        for field in ('incompatible_with', 'allowed_matrices'):
            values = row.get(field, [])
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                raise ValueError(f'{field} must be a list of option IDs.')
            item[field] = sorted(set(values))
        if item['role'] != 'matrix' and not item['allowed_matrices']:
            raise ValueError('Every filler, electrode, and structure needs owner-approved allowed_matrices.')
        normalized.append(item)
    roles = {item['option_id']: item['role'] for item in normalized}
    for item in normalized:
        if set(item['incompatible_with']) - identifiers or item['option_id'] in item['incompatible_with']:
            raise ValueError('Incompatibility rules must reference other existing options.')
        if any(roles.get(value) != 'matrix' for value in item['allowed_matrices']):
            raise ValueError('allowed_matrices must reference existing matrix options.')
    return sorted(normalized, key=lambda row: row['option_id'])


def fingerprint(options: list[dict]) -> str:
    return sha256(json.dumps(validate_options(options), sort_keys=True).encode()).hexdigest()


def write_catalog(options: list[dict], path: Path = DEFAULT_DB) -> None:
    normalized = validate_options(options)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS options (option_id TEXT PRIMARY KEY, record_json TEXT NOT NULL)')
        connection.execute('DELETE FROM options')
        connection.executemany('INSERT INTO options VALUES (?, ?)',
                               [(item['option_id'], json.dumps(item, sort_keys=True)) for item in normalized])


def read_catalog(path: Path = DEFAULT_DB) -> list[dict]:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('The catalogue is not installed. The project owner must run scripts/manage_catalog.py first.')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        records = connection.execute('SELECT record_json FROM options ORDER BY option_id').fetchall()
    return validate_options([json.loads(record[0]) for record in records])
