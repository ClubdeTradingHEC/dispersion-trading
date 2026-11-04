from pathlib import Path
import argparse, json, subprocess, sys, xml.etree.ElementTree as ET
import pandas as pd
from .config import Config
from .store import DiskBundle, dump
from .pipeline import write_outputs
from .batching import compute_to_disk
from .reporting import research
from .errors import DataError

# Declare explicit commands; live acquisition and empirical fitting are opt-in.

def parser():
    """Declare explicit commands; live acquisition and empirical fitting are opt-in."""
    p = argparse.ArgumentParser(prog='dispersion', description='Auditable package-IV dispersion research')
    sub = p.add_subparsers(dest='command', required=True)
    t = sub.add_parser('test')
    t.add_argument('--output', default='data/validation/local/offline')
    v = sub.add_parser('verify')
    v.add_argument('--output', default='data/validation/local')
    v.add_argument('--live', action='store_true')
    v.add_argument('--extract', action='store_true')
    v.add_argument('--config', default='configs/local_pilot.json')
    for name in ('access', 'extract'):
        c = sub.add_parser(name)
        c.add_argument('--config', required=True)
        c.add_argument('--output', default='data/wrds')
        if name == 'extract':
            c.add_argument(
                '--provisional',
                action='store_true',
                help='Acquire explicitly labelled diagnostic inputs without certifying the rate convention'
            )
            c.add_argument('--bundle-name', choices=['bundle','raw'], default='bundle')
    member = sub.add_parser('membership', help='Explicit dated DJIA resolution through Kevin; live/cache access')
    member.add_argument('--config', required=True)
    member.add_argument('--output', default='important_data/sources/membership.csv')
    member.add_argument('--max-dates', type=int, default=5)
    st = sub.add_parser('stage', help='Offline: publish measured DJIA inputs for study prepare')
    st.add_argument('--measurements', required=True)
    st.add_argument('--config', default='configs/study.json')
    g = sub.add_parser('gaps', help='Offline: matched four-column exports and gap inference')
    g.add_argument('--measurements', required=True)
    g.add_argument('--config', required=True)
    g.add_argument('--output', required=True)
    g.add_argument('--basket', default='reference_option_feasible')
    g.add_argument('--years', default='5,7')
    m = sub.add_parser('measure')
    m.add_argument('--input', required=True)
    m.add_argument('--config', required=True)
    m.add_argument('--output', required=True)
    m.add_argument('--asof')
    m.add_argument(
        '--provisional',
        action='store_true',
        help='Run explicitly labelled diagnostics without certifying vendor rate conventions'
    )
    m.add_argument('--dates', help='Comma-separated entry dates for a scoped pilot')
    m.add_argument(
        '--batch-sessions',
        type=int,
        default=63,
        help='Bound measurement windows; default 63 entry sessions'
    )
    for name in ('analyze', 'subsets', 'report'):
        a = sub.add_parser(name)
        a.add_argument('--measurements', required=True)
        a.add_argument('--input', required=True)
        a.add_argument('--config', required=True)
        a.add_argument('--output', required=True)
    study = sub.add_parser('study', help='Local four-equation DJIA research; no WRDS access')
    study.add_argument('phase', choices=['check', 'prepare', 'fit', 'explore', 'report', 'verify'])
    study.add_argument('--config', default='configs/study.json')
    return p
# Run offline tests in a subprocess and persist actual pass/fail counts.

def offline_tests(output):
    """Run offline tests in a subprocess and persist actual pass/fail counts."""
    # A wheel/non-editable install lives in site-packages; its tests live in the checkout.
    root = Path.cwd()
    required = ['pyproject.toml', 'tests/unit', 'src/research/cli.py']
    if not all((root / name).exists() for name in required):
        root = Path(__file__).resolve().parents[2]
    if not all((root / name).exists() for name in required):
        raise DataError('SOURCE_CHECKOUT_REQUIRED', 'Run verification from the extracted repository root.')
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'pytest',
            str(root / 'tests' / 'unit'),
            '--junitxml=' + str(out / 'pytest.xml')
        ],
        cwd=root,
        text=True,
        capture_output=True
    )
    (out / 'pytest.log').write_text(proc.stdout + proc.stderr)
    counts = {}
    if (out / 'pytest.xml').exists():
        tree = ET.parse(out / 'pytest.xml')
        suites = list(tree.getroot().iter('testsuite'))
        counts = {k: sum((int(s.get(k, 0)) for s in suites)) for k in ('tests', 'failures', 'errors', 'skipped')}
    result = {
        'status': 'PASS' if proc.returncode == 0 else 'FAIL',
        'exit_code': proc.returncode,
        **counts,
        'live_wrds_integration': 'NOT_RUN',
        'independent_second_verification': 'NOT_RUN'
    }
    dump(result, out / 'test_summary.json')
    print(proc.stdout)
    return result
# Dispatch the selected command and return a meaningful process exit status.

def main(argv=None):
    """Dispatch the selected command and return a meaningful process exit status."""
    args = parser().parse_args(argv)
    try:
        if args.command == 'test':
            return 0 if offline_tests(args.output)['status'] == 'PASS' else 1
        if args.command == 'stage':
            from .reproduction import stage
            from .dataset import read_config
            print(json.dumps(stage(args.measurements, read_config(args.config))))
            return 0
        if args.command == 'gaps':
            from .reproduction import gaps
            print(json.dumps(gaps(args.measurements, Config.read(args.config), args.output,
                                  args.basket, tuple(int(y) for y in args.years.split(',')))))
            return 0
        if args.command == 'membership':
            from .reproduction import membership
            from .inputs import sessions
            from .wrds_client import connect, QueryCache
            cfg = Config.read(args.config)
            count = len(cfg.entry_grid(sessions(cfg.entry_start, cfg.entry_end)))
            if args.max_dates < count or args.max_dates < 1 or [s.name for s in cfg.specs()] != ['DJIA']:
                raise ValueError(f'MEMBERSHIP_DATE_BUDGET_OR_INDEX: {count} dates; --max-dates must explicitly cover them')
            db = connect()
            try:
                cached = QueryCache(db, Path(args.output).parent/'membership_cache')
                print(json.dumps(membership(cached.db, cfg, args.output, args.max_dates)))
            finally:
                db.close()
            return 0
        if args.command == 'study':
            from .workflow import run
            result = run(args.phase, args.config)
            print(json.dumps(result, default=str))
            return 0
        if args.command == 'verify':
            root = Path(args.output)
            if args.extract and (not args.live):
                raise DataError('EXTRACT_REQUIRES_LIVE_FLAG')

            def phase(call):
                """Record a bounded verification failure without exposing vendor exception secrets."""
                try:
                    return call()
                except Exception as e:
                    # Persist a useful failure receipt without logging connection
                    # strings or vendor exception text that could contain secrets.
                    return {
                        'status': 'FAIL',
                        'error_type': type(e).__name__,
                        'code': getattr(e, 'code', 'VERIFICATION_PHASE_ERROR')
                    }
            summary = {
                'offline_tests': phase(lambda: offline_tests(root / 'offline')),
                'live_wrds_integration': {'status': 'NOT_RUN'},
                'independent_second_verification': 'NOT_RUN'
            }
            if args.live:
                from .wrds_client import connect, verify_access, extract
                db = None
                try:
                    cfg = Config.read(args.config)
                    db = connect()
                    access = verify_access(db, cfg)
                    summary['live_wrds_integration'] = {'access': access, 'extraction': 'NOT_RUN'}
                    if args.extract and (not any((r.get('status') == 'FAIL' for r in access))):
                        b = extract(db, cfg, 'data/wrds_verification')
                        target = Path('data/reports/wrds_verification/measurements')
                        compute_to_disk(b, cfg, target, batch_sessions=63)
                        panel = pd.read_parquet(target / 'measurements.parquet')
                        summary['live_wrds_integration']['extraction'] = 'EXECUTED_REVIEW_COVERAGE'
                    elif args.extract:
                        summary['live_wrds_integration']['extraction'] = 'BLOCKED_BY_ACCESS_FAILURE'
                except Exception as e:
                    summary['live_wrds_integration'].update(
                        status='FAIL',
                        error_type=type(e).__name__,
                        code=getattr(e, 'code', 'LIVE_VERIFICATION_ERROR')
                    )
                finally:
                    if db is not None:
                        db.close()
            summary['status'] = 'PASS' if summary['offline_tests']['status'] == 'PASS' and summary['live_wrds_integration'].get('status') != 'FAIL' else 'FAIL'
            if args.live and any((r.get('status') == 'FAIL' for r in summary['live_wrds_integration'].get('access', []))):
                summary['status'] = 'FAIL'
            dump(summary, root / 'verification_summary.json')
            print(f"Verification {summary['status']}; independent second review NOT RUN")
            return int(summary['status'] != 'PASS')
        if args.command in ('access', 'extract'):
            from .wrds_client import connect, verify_access, extract
            cfg = Config.read(args.config)
            db = connect()
            try:
                if args.command == 'access':
                    r = verify_access(db, cfg)
                    dump(r, Path(args.output) / 'access.json')
                    return int(any((x.get('status') == 'FAIL' for x in r)))
                extract(db, cfg, args.output, provisional=args.provisional, bundle_name=args.bundle_name)
                return 0
            finally:
                db.close()
        cfg = Config.read(args.config)
        b = DiskBundle(args.input).validate()
        if args.command == 'measure':
            r = compute_to_disk(
                b,
                cfg,
                args.output,
                args.dates.split(',') if args.dates else None,
                args.asof,
                args.batch_sessions,
                provisional=args.provisional
            )
            print(f"Measurements: {r['row_counts']['measurements']}; exclusions: {r['row_counts']['exclusions']}")
            return 0
        panel = pd.read_parquet(args.measurements)
        if panel.empty:
            raise DataError('NO_ELIGIBLE_MEASUREMENTS', 'Review the exclusions before running research.')
        if args.command in ('analyze', 'report'):
            research(panel, b.calendar.date, cfg, args.output)
        elif args.command == 'subsets':
            from .subsets import assess
            scores, decisions = assess(panel, b.calendar.date, cfg)
            write_outputs({'basket_scores': scores, 'basket_decisions': decisions}, args.output)
        return 0
    except (DataError, ValueError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 2
if __name__ == '__main__':
    raise SystemExit(main())
