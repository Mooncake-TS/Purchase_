import pandas as pd
from engine import match_models, fifo, cohort_rates


def frame(rows):
    df = pd.DataFrame(rows, columns=['date','code','qty','partner'])
    df['date'] = pd.to_datetime(df.date)
    df['source'], df['row'] = 'test', range(len(df))
    return df


def test_longest_prefix_and_unmatched():
    p = frame([('2025-01-01','ABC123BLK008',10,'A'),('2025-01-01','XYZ',1,'A')])
    s = frame([('2025-01-02','ABC',1,'S'),('2025-01-02','ABC123',1,'S')])
    p, _ = match_models(p,s)
    assert p.model.tolist() == ['ABC123','']
    assert p.match_status.tolist() == ['다중 후보·최장 선택','미매칭']


def test_fifo_supplier_timing_returns_and_future():
    p = frame([('2025-01-10','MODELRED',10,'A'),('2025-01-20','MODELRED',20,'B'),('2025-01-21','MODELRED',-2,'B')])
    s = frame([('2025-01-01','MODEL',3,'S'),('2025-01-20','MODEL',15,'S'),('2025-01-22','MODEL',-2,'S'),('2026-01-01','MODEL',50,'S')])
    p,s = match_models(p,s)
    lots,a,x = fifo(p,s,'2025-12-31')
    assert a.qty.tolist() == [10,5]
    assert a.supplier.tolist() == ['A','B']
    assert a.days.tolist() == [10,0]
    assert x.qty.sum() == 3
    assert lots.remaining.sum() == 15
    assert lots.qty.sum() == a.qty.sum()+lots.remaining.sum()
    rates = cohort_rates(lots,a,'2025-12-31')
    assert rates['소진율(%)'].tolist() == [50]*4


def test_maturity_and_boundary():
    p = frame([('2026-01-01','MRED',10,'A'),('2026-02-01','MRED',100,'A')])
    s = frame([('2026-01-31','M',5,'S')])
    p,s = match_models(p,s)
    lots,a,_ = fifo(p,s,'2026-02-15')
    rates = cohort_rates(lots,a,'2026-02-15')
    assert rates.iloc[0]['소진율(%)'] == 50
    assert rates.iloc[0]['관찰미완료 입고수량'] == 100
    assert pd.isna(rates.iloc[1]['소진율(%)'])


def test_empty_matching():
    p = frame([('2026-01-01','OTHER',10,'A')])
    s = frame([('2026-01-31','M',5,'S')])
    p,s = match_models(p,s)
    lots,a,x = fifo(p,s,'2026-02-15')
    assert lots.empty and a.empty and x.qty.sum() == 5
