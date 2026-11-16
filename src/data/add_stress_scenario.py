"""Compatibility command: export observed costs without legacy fixed stress."""
import argparse
import csv
from pathlib import Path

from src.backtest.transaction_costs import OPTION_COSTS_2019

LEGACY_INPUT = Path('data/transaction_costs/top30_2019/simulator_costs_final.csv')


def export_option_costs(input_path=LEGACY_INPUT, output_path=OPTION_COSTS_2019):
    """Drop only fixed_stress columns, preserving every retained cell as text."""
    source, target = Path(input_path), Path(output_path)
    if source.resolve() == target.resolve():
        raise ValueError('The original cost file must be preserved')
    with source.open(newline='', encoding='utf-8') as handle:
        reader = csv.reader(handle)
        header = next(reader)
        keep = [i for i, name in enumerate(header) if not name.startswith('fixed_stress')]
        rows = list(reader)
    if any(len(row) != len(header) for row in rows):
        raise ValueError('Malformed cost CSV')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow([header[i] for i in keep])
        writer.writerows([row[i] for i in keep] for row in rows)
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=LEGACY_INPUT)
    parser.add_argument('--output', type=Path, default=OPTION_COSTS_2019)
    args = parser.parse_args(argv)
    rows = export_option_costs(args.input, args.output)
    print(f'Exported {rows} rows to {args.output}')


if __name__ == '__main__':
    main()
