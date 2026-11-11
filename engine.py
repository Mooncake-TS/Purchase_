"""Model-level FIFO estimates. Returns are deliberately quarantined."""
from collections import defaultdict, deque
import pandas as pd


def match_models(purchases, sales):
    models = sorted(set(sales['code'].dropna()), key=lambda x: (-len(x), x))
    p = purchases.copy()
    candidates = p['code'].map(lambda code: [m for m in models if code.startswith(m)])
    p['model'] = candidates.map(lambda xs: xs[0] if xs else '')
    p['match_status'] = candidates.map(lambda xs: '미매칭' if not xs else '다중 후보·최장 선택' if len(xs) > 1 else '일치')
    p['candidates'] = candidates.map(lambda xs: ' | '.join(xs))
    s = sales.copy()
    s['model'] = s['code']
    return p, s


def fifo(purchases, sales, cutoff):
    cutoff = pd.Timestamp(cutoff)
    p = purchases[(purchases.date <= cutoff) & (purchases.qty > 0) & (purchases.model != '')].copy()
    s = sales[(sales.date <= cutoff) & (sales.qty > 0)].copy()
    lots, allocations, excess = [], [], []
    queues = defaultdict(deque)
    events = [(r.date, 0, i, r) for i, r in p.iterrows()]
    events += [(r.date, 1, i, r) for i, r in s.iterrows()]
    for date, kind, _, r in sorted(events, key=lambda e: (e[0], e[1], e[2])):
        if kind == 0:
            lot = dict(lot_id=len(lots), date=date, model=r.model, supplier=r.partner,
                       qty=float(r.qty), remaining=float(r.qty), source=r.source, row=r.row)
            lots.append(lot)
            queues[r.model].append(lot)
        else:
            remaining = float(r.qty)
            queue = queues[r.model]
            while remaining > 1e-9 and queue:
                lot = queue[0]
                amount = min(remaining, lot['remaining'])
                allocations.append(dict(lot_id=lot['lot_id'], purchase_date=lot['date'],
                    sale_date=date, model=r.model, supplier=lot['supplier'], qty=amount,
                    days=(date-lot['date']).days, source=r.source, row=r.row))
                remaining -= amount
                lot['remaining'] -= amount
                if lot['remaining'] < 1e-9:
                    queue.popleft()
            if remaining > 1e-9:
                excess.append(dict(date=date, model=r.model, qty=remaining, source=r.source, row=r.row))
    frames = (pd.DataFrame(lots, columns=['lot_id','date','model','supplier','qty','remaining','source','row']),
            pd.DataFrame(allocations, columns=['lot_id','purchase_date','sale_date','model','supplier','qty','days','source','row']),
            pd.DataFrame(excess, columns=['date','model','qty','source','row']))
    for frame in frames:
        for col in ('date','purchase_date','sale_date'):
            if col in frame:
                frame[col] = pd.to_datetime(frame[col])
        for col in ('qty','remaining','days'):
            if col in frame:
                frame[col] = pd.to_numeric(frame[col])
    return frames


def cohort_rates(lots, allocations, cutoff):
    records = []
    for horizon in (30, 60, 90, 180):
        eligible = lots[lots.date + pd.to_timedelta(horizon, unit='D') <= pd.Timestamp(cutoff)]
        a = allocations[allocations.lot_id.isin(eligible.lot_id) & (allocations.days <= horizon)]
        denominator = eligible.qty.sum()
        records.append({'관찰기간(일)': horizon, '관찰완료 입고수량': denominator,
                        '기간 내 추정판매': a.qty.sum(),
                        '소진율(%)': 100*a.qty.sum()/denominator if denominator else float('nan'),
                        '관찰미완료 입고수량': lots.qty.sum()-denominator})
    return pd.DataFrame(records)
