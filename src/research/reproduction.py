"""Source-only checkout bridges; reuse financial engines and Kevin's resolver."""
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from scipy.stats import norm
from .inputs import sessions, sha256
from .store import DiskBundle, dump, _publish
from .inference import mean_test, hac_mean
from .statistics import holm


# Resolve each requested entry session through Kevin's unchanged dated resolver.
def membership(db, config, output, max_dates=5):
    from src.data.compustat_membership import get_compustat_index_constituents
    specs = config.specs()
    if len(specs) != 1 or specs[0].name != 'DJIA':
        raise ValueError('MEMBERSHIP_COMMAND_REQUIRES_DJIA')
    grid = config.entry_grid(sessions(config.entry_start, config.entry_end))
    if len(grid) > max_dates or max_dates < 1:
        raise ValueError(f'MEMBERSHIP_DATE_BUDGET: {len(grid)} dates; explicit --max-dates required')
    rows, coverage = [], []
    for date in grid:
        found = get_compustat_index_constituents(db, specs[0].benchmark, date, verbose=False)
        counts = found.attrs.get('membership_coverage', {})
        for permno in found.permno:
            # Single-session intervals preserve exactly what was resolved then.
            rows.append({'index':'DJIA', 'permno':int(permno), 'start':date, 'end':date})
        coverage.append({'date':date, 'found':len(found), 'expected':counts.get('expected'), 'missing':counts.get('missing')})
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=['index','permno','start','end']).to_csv(target,index=False,date_format='%Y-%m-%d')
    pd.DataFrame(coverage).to_csv(target.with_suffix('.coverage.csv'),index=False,date_format='%Y-%m-%d')
    return {'status':'PASS','dates':len(grid),'membership_sha256':sha256(target),
            'timing':'Dated resolution, not certified historical publication/revision vintage'}


# Publish the standard measurement outputs in the schema consumed by study prepare.
def stage(measurements, cfg):
    root = Path(measurements)
    raw = DiskBundle(cfg['raw_root']).validate()
    panel = pd.read_parquet(root/'measurements.parquet')
    panel = panel.loc[panel['index'].eq('DJIA') & panel.horizon.eq(30) & panel.basket.eq('full')].copy()
    if panel.empty or panel.date.duplicated().any():
        raise ValueError('INVALID_DJIA_MEASUREMENT_GRAIN')
    constituents = pd.read_parquet(root/'constituents.parquet')
    constituents = constituents.loc[constituents['index'].eq('DJIA') & constituents.horizon.eq(30) & constituents.basket.eq('full')]
    if constituents.duplicated(['date','permno']).any():
        raise ValueError('DUPLICATE_ENTRY_MEMBER')
    panel['official_member_count'] = 30
    panel['mapped_member_count'] = panel.n_original
    panel['mapped_membership_is_complete'] = panel.n_original.eq(30)
    panel['original_cap_coverage_scope'] = 'mapped_members_only; not proof of official index weight coverage'
    panel['unmapped_official_weight_mass_known'] = panel.n_original.eq(30) & panel.original_cap_coverage.notna()
    target = Path(cfg['measurements_root'])
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.stage-', dir=target) as folder:
        pending = Path(folder)
        panel.to_parquet(pending/'financial_panel.parquet',index=False)
        constituents[['date','horizon','basket','permno','weight','iv']].to_parquet(pending/'constituents.parquet',index=False)
        dump({'source_measurements_sha256':sha256(root/'measurements.parquet'),
              'raw_manifest_sha256':sha256(raw.root/'manifest.json'),
              'rows':len(panel),'new_WRDS_queries':0}, pending/'measurement_receipt.json')
        _publish(pending,target)
    return {'status':'PASS','rows':len(panel),'new_WRDS_queries':0}


# Recreate the exact four-column forward-matched exports and overlap-aware inference.
def gaps(measurements, config, output, basket='reference_option_feasible', years=(5,7)):
    panel = pd.read_parquet(Path(measurements)/'measurements.parquet')
    if len(config.specs()) != 1 or config.horizons != [30]:
        raise ValueError('GAP_EXPORT_REQUIRES_ONE_INDEX_30_DAYS')
    name = config.specs()[0].name
    d = panel.loc[panel['index'].eq(name) & panel.horizon.eq(30) & panel.basket.eq(basket)].copy()
    if d.date.duplicated().any():
        raise ValueError('DUPLICATE_ENTRY_DATE')
    good = d.loc[d.ic_status.eq('PASS') & d.label_status.eq('PASS')].sort_values('date')
    if good.empty or not (good.label_end-good.date).eq(pd.Timedelta(days=30)).all():
        raise ValueError('NO_VALID_MATCHED_30_DAY_ENTRIES')
    if not np.isfinite(good[['ic','rc_future']]).all().all():
        raise ValueError('NONFINITE_GAP_EXPORT')
    if not (good.label_first_session>good.date).all() or not (good.label_last_session<=good.label_end).all():
        raise ValueError('INVALID_FORWARD_SESSION_ALIGNMENT')
    if config.observation_end and (good.label_available_at>pd.Timestamp(config.observation_end)).any():
        raise ValueError('LABEL_BEYOND_OBSERVATION_CUTOFF')
    if not years or len(set(years))!=len(years) or any(y<1 for y in years):
        raise ValueError('UNIQUE_POSITIVE_YEAR_WINDOWS_REQUIRED')
    target = Path(output)
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gaps-',dir=target) as folder:
        root = Path(folder)
        results = []
        for count in years:
            grid = sessions(pd.Timestamp(config.entry_end)-pd.DateOffset(years=count),config.entry_end)
            part = good.loc[good.date.isin(grid)]
            export = part[['date','ic','label_end','rc_future']].set_axis(['date_of_IC','IC','matched_date_of_RC','RC'],axis=1)
            csv = root/f'{name}_IC_RC_{count}years.csv'
            export.to_csv(csv,index=False,date_format='%Y-%m-%d',float_format='%.17g')
            values = (part.set_index('date').ic-part.set_index('date').rc_future).reindex(grid).to_numpy(float)
            test = mean_test(values,30,config)
            test['p_two_sided_zero_mean'] = float(2*norm.sf(abs(test['mean']/test['se_hac'])))
            results.append({'years':count,'inference':test,
                            'HAC_lag_sensitivities':{str(lag):hac_mean(values,lag) for lag in (15,30,60)},
                            'csv_sha256':sha256(csv)})
        adjusted = holm([r['inference']['p_two_sided_zero_mean'] for r in results])
        for r,p in zip(results,adjusted):
            r['inference']['p_two_sided_Holm_windows'] = float(p)
        coverage=d.set_index('date').reindex(sessions(config.entry_start,config.entry_end))
        coverage.index.name='date'
        coverage[['ic_status','label_status']]=coverage[['ic_status','label_status']].fillna('NO_MEASUREMENT')
        errors=Path(measurements)/'exclusions.parquet'
        coverage['entry_error']=''
        if errors.exists():
            excluded=pd.read_parquet(errors)
            failed=excluded.loc[excluded.stage.isin(['universe','index_iv'])].groupby('date').code.agg(lambda v:','.join(sorted(set(v))))
            coverage['entry_error']=failed.reindex(coverage.index).fillna('')
        coverage.reset_index().to_csv(root/'coverage.csv',index=False,date_format='%Y-%m-%d')
        dump({'status':'PASS','index':name,'basket':basket,'periods':results,
              'source_measurements_sha256':sha256(Path(measurements)/'measurements.parquet'),
              'interpretation':'Available-input proxy; pair coverage is explicit; gaps are not profits',
              'new_WRDS_queries':0},root/'results.json')
        _publish(root,target)
    return {'status':'PASS','windows':len(results),'new_WRDS_queries':0}
