"""Explicit FRED acquisition and exchange-session alignment for curated events."""
import json
import os
import pandas as pd
import requests
from src.research.inputs import sessions


# Network access occurs only when this function is explicitly requested.
def macro_events(start, end, config='configs/events.json'):
    key = os.environ.get('FRED_API_KEY')
    if not key:
        raise ValueError('Set FRED_API_KEY locally; never store it in source')
    start,end = pd.Timestamp(start),pd.Timestamp(end)
    if start > end or end > pd.Timestamp.today().normalize():
        raise ValueError('Require start <= end <= today')
    with open(config,encoding='utf-8') as stream:
        settings=json.load(stream)

    def get(endpoint,**params):
        params.update(api_key=key,file_type='json')
        try:
            response=requests.get('https://api.stlouisfed.org/fred/'+endpoint,params=params,timeout=30)
        except requests.RequestException:
            raise ValueError('FRED network request failed; check connectivity') from None
        # requests exceptions may embed a URL including the API key; expose only status.
        if response.status_code != 200:
            raise ValueError(f'FRED request failed (HTTP {response.status_code})')
        return response.json()

    releases,offset=[],0
    while True:
        page=get('releases',limit=1000,offset=offset)
        releases.extend(page['releases']);offset+=1000
        if offset>=page['count']:
            break
    ids={r['name']:r['id'] for r in releases}
    rows=[]
    for label,name in settings['fred_releases'].items():
        if name not in ids:
            raise ValueError(f'FRED release not found: {label}')
        dates=[];offset=0
        while True:
            page=get('release/dates',release_id=ids[name],realtime_start=str(start.date()),
                     realtime_end=str(end.date()),include_release_dates_with_no_data='false',
                     limit=10000,offset=offset,sort_order='asc')
            dates.extend(page['release_dates']);offset+=10000
            if offset>=page['count']:
                break
        frame=pd.DataFrame({'date':pd.to_datetime([d['date'] for d in dates])})
        frame=frame[frame.date.between(start,end)].drop_duplicates().sort_values('date')
        grouped=frame.groupby(frame.date.dt.to_period('M'))
        frame=grouped.tail(1) if label in settings['keep_last'] else grouped.head(1)
        rows.extend({'date':d,'event_type':label,'description':settings['descriptions'][label]} for d in frame.date)
    for date in settings['fomc_dates']:
        rows.append({'date':pd.Timestamp(date),'event_type':'FOMC',
                     'description':settings['fomc_special'].get(date,settings['descriptions']['FOMC'])})
    for date,description in settings['shocks']:
        rows.append({'date':pd.Timestamp(date),'event_type':'SHOCK','description':description})
    for date,title,description in settings['extra_shocks']:
        rows.append({'date':pd.Timestamp(date),'event_type':'SHOCK','description':description})
    result=pd.DataFrame(rows)
    result=result[result.date.between(start,end)].drop_duplicates(['date','event_type']).sort_values(['date','event_type'])
    return align_events(result,settings['after_close'])


# After-close announcements roll one session; weekends and exchange holidays roll forward.
def align_events(events,after_close=()):
    result=events.copy()
    result['date']=pd.to_datetime(result['date'])
    if result.empty:
        result['trading_date']=pd.to_datetime([])
        return result
    grid=sessions(result.date.min().strftime('%Y-%m-%d'),(result.date.max()+pd.Timedelta(days=14)).strftime('%Y-%m-%d'))
    def align(row):
        date=row['date']
        later=row['event_type']=='SHOCK' and date.strftime('%Y-%m-%d') in after_close
        candidates=grid[grid>date] if later else grid[grid>=date]
        return candidates[0]
    result['trading_date']=result.apply(align,axis=1)
    return result.reset_index(drop=True)


# The original basket scripts always added these five curated shocks themselves.
def legacy_shocks(events,config):
    with open(config,encoding='utf-8') as stream:
        settings=json.load(stream)
    extra=pd.DataFrame([{'date':pd.Timestamp(date),'event_type':'SHOCK','description':description}
                        for date,title,description in settings['extra_shocks']])
    extra=align_events(extra)
    if events is None:
        return extra
    events=events.copy()
    events['date']=pd.to_datetime(events['date'])
    return pd.concat([events,extra],ignore_index=True).drop_duplicates(['date','event_type'],keep='first')
