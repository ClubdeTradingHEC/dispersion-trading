"""English, explicit entry points for the team's independent event workflows."""
from pathlib import Path
import argparse
import os
from datetime import datetime, timezone
import pandas as pd
from .analysis import basket_correlation, event_study, save_tables, vix_overlay
from .macro import macro_events,legacy_shocks
from .output import publish_run
from src.research.inputs import sha256


# Every data path is explicit; importing a module cannot query services or write outputs.
def parser():
    p=argparse.ArgumentParser(prog='dispersion-events',description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    macro=sub.add_parser('macro',help='Live FRED acquisition; requires FRED_API_KEY')
    macro.add_argument('--start',required=True)
    macro.add_argument('--end',required=True)
    macro.add_argument('--config',default='configs/events.json')
    macro.add_argument('--output',required=True)
    for name in ['basket','study','vix']:
        cmd=sub.add_parser(name,help='Offline: uses supplied local input files')
        cmd.add_argument('--returns',required=True)
        cmd.add_argument('--output',required=True)
        if name!='basket':
            cmd.add_argument('--correlation',required=True)
        cmd.add_argument('--events',required=name=='study')
        if name=='basket':
            cmd.add_argument('--window',type=int,default=30,help='Observed trading sessions, not calendar days')
            cmd.add_argument('--legacy-shocks-config',help='Compatibility: include the original basket scripts\' curated extra shocks')
        if name=='vix':
            cmd.add_argument('--vix',required=True,help='FRED CSV: observation_date,VIXCLS')
            cmd.add_argument('--horizon',type=int,default=21)
        if name!='study':
            cmd.add_argument('--no-plots',action='store_true')
    return p


# Full-period and quarterly charts retain the team's weighted/equal correlation views.
def basket_plots(frame,events,output):
    import matplotlib.pyplot as plt
    groups=[('full',frame)] + [(str(q),g) for q,g in frame.groupby(frame.date.dt.to_period('Q'))]
    for name,data in groups:
        fig,ax=plt.subplots(figsize=(11,4))
        ax.plot(data.date,data.rc_basket,label='Constituent-weighted pair RC')
        ax.plot(data.date,data.rc_equal_weight,color='grey',label='Equal pair RC',linewidth=1)
        if events is not None:
            curve=data.set_index('date').rc_basket
            for typ,group in events.groupby('event_type'):
                dates=pd.DatetimeIndex(group.trading_date).intersection(curve.index)
                if len(dates):
                    ax.scatter(dates,curve.reindex(dates),s=18,label=typ)
            labels=events[events.event_type.isin(['SHOCK','FOMC']) & events.trading_date.isin(curve.index)]
            # Rotate sparse labels; dense full-history charts use event markers and table descriptions.
            if len(labels)<=16:
                for _,row in labels.iterrows():
                    text=str(row.get('description',row.event_type))[:48]
                    ax.annotate(text,(row.trading_date,curve.loc[row.trading_date]),fontsize=6,
                                rotation=60,xytext=(0,8),textcoords='offset points')
        ax.set(title=f'Trailing basket correlation — {name}',ylabel='Correlation')
        ax.grid(alpha=.25)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.22),ncol=4,fontsize=7)
        fig.autofmt_xdate();fig.savefig(output/f'basket_{name}.png',dpi=150,bbox_inches='tight');plt.close(fig)


# VIX is index volatility, not IC or a complete dispersion-trade payoff.
def vix_plots(frame,output,events=None):
    import matplotlib.pyplot as plt
    periods={'full':frame,'2022':frame.loc['2022-01-01':'2022-12-31'],
             '2025_spring':frame.loc['2025-03-01':'2025-05-31']}
    for name,data in periods.items():
        if data.empty:
            continue
        fig,ax=plt.subplots(figsize=(11,4))
        ax.plot(data.index,data.rc_basket,label='Trailing basket RC')
        right=ax.twinx();right.plot(data.index,data.vix,color='orangered',label='VIX')
        ax.set(ylabel='Correlation',title=f'Basket RC and VIX — {name}');right.set_ylabel('Annualized volatility (%)')
        lines=ax.lines+right.lines
        ax.legend(lines,[l.get_label() for l in lines],loc='upper left')
        if events is not None and name!='full':
            draw_shocks(ax,data,events)
        fig.autofmt_xdate();fig.savefig(output/f'vix_corr_{name}.png',dpi=150,bbox_inches='tight');plt.close(fig)
        fig,ax=plt.subplots(figsize=(11,4))
        ax.plot(data.index,data.vix,label='Entry VIX')
        ax.plot(data.index,data.fwd_realized_vol,label='Subsequent realized volatility')
        ax.fill_between(data.index,data.vix,data.fwd_realized_vol,
                        where=data.fwd_realized_vol>data.vix,alpha=.2,color='red',label='Realized above implied (not P&L)')
        ax.set(ylabel='Annualized volatility (%)',title=f'VIX and future volatility — {name}');ax.legend()
        if events is not None and name!='full':
            draw_shocks(ax,data,events)
        fig.autofmt_xdate();fig.savefig(output/f'vix_rv_{name}.png',dpi=150,bbox_inches='tight');plt.close(fig)


# Preserve the team's shock annotations in the 2022 and spring-2025 zoom views.
def draw_shocks(ax,data,events):
    selected=events.loc[events.event_type.eq('SHOCK') & events.trading_date.between(data.index.min(),data.index.max())]
    for number,(_,row) in enumerate(selected.iterrows()):
        ax.axvline(row.trading_date,color='green',linestyle='--',alpha=.5)
        ax.annotate(str(row.get('description','Shock'))[:40],(row.trading_date,.97-.08*(number%2)),
                    xycoords=('data','axes fraction'),fontsize=7,rotation=30,ha='left',va='top')


# Dispatch common filenames to prevent the old producer/consumer mismatch.
def main(argv=None):
    args=parser().parse_args(argv)
    try:
        target=Path(args.output)
        paths={name:Path(getattr(args,name)) for name in ['returns','correlation','events','vix','config','legacy_shocks_config']
               if getattr(args,name,None)}
        # Read/validate provenance before touching the previous output generation.
        sources={name:{'path':str(path.resolve()),'sha256':sha256(path)} for name,path in paths.items()}
        with publish_run(target,paths.values(),args.command) as output:
            if args.command=='macro':
                frame=macro_events(args.start,args.end,args.config)
                save_tables(output,{'macro_events':frame})
            else:
                raw=pd.read_csv(args.returns,parse_dates=['date'])
                if args.command=='basket':
                    frame=basket_correlation(raw,args.window)
                    events=pd.read_csv(args.events,parse_dates=['trading_date']) if args.events else None
                    if args.legacy_shocks_config:
                        events=legacy_shocks(events,args.legacy_shocks_config)
                    if events is not None:
                        descriptions=events.groupby('trading_date').agg(
                            events=('event_type',lambda s:', '.join(sorted(set(s)))),
                            event_description=('description',lambda s:' | '.join(map(str,s))))
                        frame=frame.merge(descriptions.rename_axis('date'),on='date',how='left')
                    save_tables(output,{'basket_correlation':frame})
                    if not args.no_plots:
                        basket_plots(frame,events,output)
                else:
                    corr=pd.read_csv(args.correlation,parse_dates=['date']).set_index('date').rc_basket
                    if not corr.index.is_monotonic_increasing or corr.index.has_duplicates:
                        raise ValueError('Correlation dates must be sorted and unique')
                    if args.command=='study':
                        events=pd.read_csv(args.events,parse_dates=['trading_date'])
                        by_type,broad,detail=event_study(corr,events,raw)
                        save_tables(output,{'by_event_type':by_type,'broad_moves':broad,'event_detail':detail})
                    else:
                        vix=pd.read_csv(args.vix,parse_dates=['observation_date']).set_index('observation_date').VIXCLS
                        frame=vix_overlay(corr,raw,vix,args.horizon)
                        save_tables(output,{'vix_overlay':frame.rename_axis('date').reset_index()})
                        if not args.no_plots:
                            events=pd.read_csv(args.events,parse_dates=['trading_date']) if args.events else None
                            vix_plots(frame,output,events)
            from src.research.store import dump
            dump({'command':args.command,'status':'PASS','arguments':vars(args),
                  'generated_at_utc':datetime.now(timezone.utc).isoformat(),
                  'inputs':sources,
                  'code_sha256':{p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')},
                  'files':{p.name:sha256(p) for p in output.iterdir() if p.is_file()},
                  'interpretation':'Retrospective exploration; no causal or trade-profit certification'},output/'run.json')
        print(f'PASS: {args.command} -> {target}')
        return 0
    except (ValueError,OSError,KeyError) as exc:
        # Avoid echoing HTTP URLs or connection strings from third-party exceptions.
        detail = 'Set FRED_API_KEY locally; never put it in source.' if args.command=='macro' and not os.environ.get('FRED_API_KEY') else 'Check input schemas and use a separate output directory.'
        print(f'FAIL: {args.command} ({type(exc).__name__}). {detail}')
        return 2


if __name__=='__main__':
    raise SystemExit(main())
