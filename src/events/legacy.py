"""Keep original team script inputs/outputs while sharing the maintained event engine."""
import os
import shutil
import sys
import tempfile
from pathlib import Path
import pandas as pd
from .cli import main,parser


# Prefer an existing canonical artifact; also accept the original local filenames.
def first_existing(*paths):
    return str(next((Path(p) for p in paths if Path(p).is_file()),Path(paths[0])))


# Replace individual compatibility artifacts without exposing a partly written file.
def copy_alias(source,target):
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve():
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.legacy-',delete=False) as handle:
            temporary=Path(handle.name)
        shutil.copyfile(source,temporary)
        os.replace(temporary,target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# Legacy labels exist only for consumers of old artifacts; the primary project stays English.
def legacy_event_table(frame):
    names={'group':'Groupe','n':'N','median_change_3_sessions':'Médiane Δ 3 jours',
           'fraction_positive_3_sessions':'% hausses (3 jours)',
           'mean_abs_change_3_sessions':'|Δ| moyen 3 jours',
           'naive_mann_whitney_abs_p_3_sessions':'p-value |Δ| 3 jours (Mann-Whitney)'}
    for k,label in [(1,'1 jour'),(2,'2 jours'),(3,'3 jours')]:
        names[f'mean_change_{k}_sessions']=f'Δ moyen {label}'
        names[f'naive_welch_p_{k}_sessions']=f'p-value {label} (Welch)'
    result=frame.drop(columns=['inference']).rename(columns=names)
    result['Groupe']=result.Groupe.replace({'Normal days':'Jours normaux',
        'Broad move with event':'Mouvement large, jour FOMC/CPI/NFP',
        'Broad move without event':'Mouvement large, autre jour',
        'Event without broad move':'FOMC/CPI/NFP sans mouvement large'})
    return result


# Retain original filenames and table columns for teammates' existing consumers.
def aliases(command,year,output,destination):
    output,destination=Path(output),Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    if command=='basket':
        prefix='basket_correlation_v2' if year=='2024' else 'basket_correlation_v2_2021_2025'
        frame=pd.read_csv(output/'basket_correlation.csv')
        for column in ['events','event_description']:
            if column not in frame:
                frame[column]=None
        order=['date','rc_basket','rc_equal_weight','n_stocks','n_excluded','events','event_description']
        with tempfile.TemporaryDirectory(prefix='.legacy-basket-',dir=destination) as folder:
            temp=Path(folder)
            frame[order].to_csv(temp/(prefix+'.csv'),index=False)
            frame[order].to_excel(temp/(prefix+'.xlsx'),index=False,sheet_name='rc_basket')
            copy_alias(temp/(prefix+'.csv'),destination/(prefix+'.csv'))
            copy_alias(temp/(prefix+'.xlsx'),destination/(prefix+'.xlsx'))
            # Original downstream scripts omitted the producer's _v2 suffix.
            if year!='2024':
                copy_alias(temp/(prefix+'.csv'),destination/'basket_correlation_2021_2025.csv')
        for chart in output.glob('basket_*.png'):
            period=chart.stem.removeprefix('basket_')
            suffix='' if period=='full' else f'_Q{period[-1]}_{period[:4]}'
            copy_alias(chart,destination/(prefix+suffix+'.png'))
    elif command=='macro':
        frame=pd.read_csv(output/'macro_events.csv')
        copy_alias(output/'macro_events.csv',destination/'macro_events.csv')
        with tempfile.TemporaryDirectory(prefix='.legacy-macro-',dir=destination) as folder:
            file=Path(folder)/'macro_events.xlsx'
            frame.to_excel(file,index=False,sheet_name='events')
            copy_alias(file,destination/file.name)
    elif command=='study':
        first=legacy_event_table(pd.read_csv(output/'by_event_type.csv'))
        broad=legacy_event_table(pd.read_csv(output/'broad_moves.csv'))
        detail=pd.read_csv(output/'event_detail.csv')
        detail=detail[['trading_date','event_type','d1','d2','d3','index_return','breadth','broad_move']]
        with tempfile.TemporaryDirectory(prefix='.legacy-study-',dir=destination) as folder:
            folder=Path(folder)
            first.to_csv(folder/'event_study_2021_2025.csv',index=False)
            with pd.ExcelWriter(folder/'event_study_2021_2025.xlsx',engine='openpyxl') as writer:
                for name,frame in [('par type',first),('mouvements larges',broad),('détail',detail)]:
                    frame.to_excel(writer,index=False,sheet_name=name)
            for file in folder.iterdir():
                copy_alias(file,destination/file.name)
    else:
        frame=pd.read_csv(output/'vix_overlay.csv')
        columns=['date','rc_basket','vix','fwd_realized_vol','realized_above_vix']
        with tempfile.TemporaryDirectory(prefix='.legacy-vix-',dir=destination) as folder:
            file=Path(folder)/'vix_overlay_2021_2025.csv'
            frame[columns].to_csv(file,index=False)
            copy_alias(file,destination/file.name)
        for file in output.glob('vix_*.png'):
            copy_alias(file,destination/file.name)


# No-flag runs keep the original current-directory filenames; explicit output stays explicit.
def launch(command,year='2021_2025'):
    returns=first_existing(f'spx_returns_weights_{year}.csv',f'important_data/team/spx_returns_weights_{year}.csv')
    basket='data/events/basket_2024' if year=='2024' else 'data/events/basket'
    events=first_existing('data/events/macro/macro_events.csv','macro_events.csv')
    if command=='macro':
        config=first_existing('configs/events.json',str(Path(__file__).resolve().parents[2]/'configs/events.json'))
        defaults=['--start','2015-01-01','--end',str(pd.Timestamp.today().date()),'--config',str(config),'--output','data/events/macro']
    elif command=='basket':
        config=first_existing('configs/events.json',str(Path(__file__).resolve().parents[2]/'configs/events.json'))
        defaults=['--returns',returns,'--output',basket,'--legacy-shocks-config',config]
        if Path(events).is_file():
            defaults+=['--events',events]
    else:
        correlation=first_existing(f'{basket}/basket_correlation.csv','basket_correlation_2021_2025.csv','basket_correlation_v2_2021_2025.csv')
        defaults=['--returns',returns,'--correlation',correlation,'--output',f'data/events/{command}']
        defaults+=['--events',events] if command=='study' else ['--vix',first_existing('VIXCLS.csv','important_data/team/VIXCLS.csv')]
        if command=='vix' and Path(events).is_file():
            defaults+=['--events',events]
    arguments=[command,*defaults,*sys.argv[1:]]
    args=parser().parse_args(arguments)
    explicit_output=any(a=='--output' or a.startswith('--output=') for a in sys.argv[1:])
    code=main(arguments)
    if code==0 and not explicit_output:
        aliases(command,year,args.output,Path.cwd())
    return code
