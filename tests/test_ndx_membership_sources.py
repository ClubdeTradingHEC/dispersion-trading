"""Manual, bounded source discovery; optional tables are not assumed interchangeable."""
from src.data.wrds_connection import get_wrds_connection


NDX_GVKEYX = '000208'
TEST_DATE = '2024-01-03'


# Keep the original diagnostic's display helper and explicit live entry point.
def print_df(df):
    if df is None or df.empty:
        print('No rows.')
    else:
        print(df.to_string(index=False))


# Return schema metadata so later probes cannot assume nonexistent vendor columns.
def describe(db, table):
    print(f'\nDESCRIBE comp.{table}')
    try:
        frame = db.describe_table(library='comp', table=table)
        print_df(frame)
        return frame
    except Exception as exc:
        print(f'UNAVAILABLE: comp.{table} ({type(exc).__name__})')
        return None


# Sampling stays bounded and does not change the financial membership resolver.
def sample(db, table):
    print(f'\nSAMPLE comp.{table}')
    try:
        frame = db.raw_sql(f'SELECT * FROM comp.{table} LIMIT 10')
        print_df(frame)
        return frame
    except Exception as exc:
        print(f'UNAVAILABLE: comp.{table} ({type(exc).__name__})')
        return None


# Only use an actual GVKEYX column as an index key; company GVKEY is not a substitute.
def main():
    db = get_wrds_connection()
    results = []
    try:
        for table in ['idxcst_his', 'names_ix_cst', 'spidx_cst', 'wrds_idx_cst_current']:
            metadata = describe(db, table)
            if metadata is None:
                results.append({'table': table, 'status': 'UNAVAILABLE'})
                continue
            sample(db, table)
            columns = set(metadata['name'].str.lower())
            if 'gvkeyx' not in columns:
                print(f'SKIP comp.{table}: no GVKEYX index identifier column.')
                results.append({'table': table, 'status': 'SKIP_NO_GVKEYX'})
                continue
            start = next((name for name in ['fromdate', 'from', 'startdate'] if name in columns), None)
            end = next((name for name in ['thrudate', 'thru', 'enddate'] if name in columns), None)
            # This is a bounded discovery probe, not certified complete historical membership.
            where = f"gvkeyx = '{NDX_GVKEYX}'"
            mode = 'BOUNDED_INDEX_SAMPLE'
            if start and end:
                where += f''' AND "{start}" <= '{TEST_DATE}' AND ("{end}" IS NULL OR "{end}" >= '{TEST_DATE}')'''
                mode = 'BOUNDED_DATED_INDEX_SAMPLE'
            try:
                frame = db.raw_sql(f'SELECT * FROM comp.{table} WHERE {where} LIMIT 200')
                print_df(frame)
                results.append({'table': table, 'status': 'PASS', 'mode': mode, 'rows': len(frame)})
            except Exception as exc:
                print(f'UNAVAILABLE: comp.{table} ({type(exc).__name__})')
                results.append({'table': table, 'status': 'UNAVAILABLE', 'error_type': type(exc).__name__})
        return results
    finally:
        db.close()


if __name__ == '__main__':
    main()
