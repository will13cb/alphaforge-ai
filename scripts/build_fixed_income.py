"""Build the dated Canada/U.S. catalogue for S3. Optional --extra CSV adds other sourced instruments."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dh import bond_rates


def write_csv(path, rows, fallback):
    columns = list(dict.fromkeys(k for row in rows for k in row)) or fallback
    with path.open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extra', type=Path, action='append', default=[])
    parser.add_argument('--out', type=Path, default=bond_rates.folder())
    args = parser.parse_args()
    reference = bond_rates.refresh()
    rows = reference.get('outstanding_bonds', [])
    for extra in args.extra:
        with extra.open(newline='') as source:
            rows += list(csv.DictReader(source))
    rows, issues = bond_rates.validate(rows)
    if not rows:
        raise SystemExit('No usable instruments downloaded; existing dataset was not replaced.')
    args.out.mkdir(parents=True, exist_ok=True)
    reference['outstanding_bonds'] = rows
    (args.out / 'reference_snapshot.json').write_text(json.dumps(reference, indent=2) + '\n')
    write_csv(args.out / 'instruments.csv', rows, ['instrument_id'])
    write_csv(args.out / 'quality_report.csv', issues, ['instrument_id','status','reason'])
    sources = {r['terms_source'] for r in rows}
    sources.update(r['quote_source'] for r in rows if r.get('quote_source'))
    sources.update(reference[k] for k in ('terms_source', 'yields_source') if reference.get(k))
    if reference.get('fx_usdcad'):
        sources.add(reference['fx_usdcad']['source'])
    write_csv(args.out / 'sources_metadata.csv', [dict(source=url, retrieved=reference.get('retrieved_at'),
              limitations='Bond terms and benchmark/auction references; not complete dealer inventory or executable quotes')
              for url in sorted(sources)], ['source'])
    print(f'{len(rows)} instruments written to {args.out}; {len(issues)} rejected')
    for note in reference.get('refresh_notes', []):
        print(note)


if __name__ == '__main__':
    main()
