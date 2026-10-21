"""Owner CLI: validate a JSON catalogue, or transactionally install it into SQLite."""
import argparse
import json
from pathlib import Path
from sensorforge.catalog import DEFAULT_DB, fingerprint, validate_options, write_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='JSON list of matrix, filler, electrode, and structure options')
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    parser.add_argument('--check', action='store_true', help='Validate without modifying the database')
    args = parser.parse_args()
    options = validate_options(json.loads(args.source.read_text()))
    if not args.check:
        write_catalog(options, args.database)
    print(json.dumps({'options': len(options), 'fingerprint': fingerprint(options),
                      'action': 'validated' if args.check else 'installed', 'database': str(args.database)}, indent=2))


if __name__ == '__main__':
    main()
