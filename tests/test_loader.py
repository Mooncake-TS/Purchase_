from io import BytesIO
import pandas as pd
from loader import load_files, parse_date, number, repository_files
from demo import demo_files


def workbook(rows, company=False):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.DataFrame(rows, columns=['일자-No.','품목코드','수량','거래처명']).to_excel(writer,index=False,startrow=int(company))
    return out.getvalue()


def test_dates_numbers():
    assert parse_date('2026/10/31-2') == pd.Timestamp('2026-10-31')
    assert parse_date('20261031') == pd.Timestamp('2026-10-31')
    assert parse_date(45962) == pd.Timestamp('2025-11-01')
    assert pd.isna(parse_date('10/31'))
    assert number('(1,200)') == -1200
    assert pd.isna(number('oops'))


def test_overlap_preserves_multiplicity():
    row = ['2026-01-01-1','MODELRED','1,000','A']
    a = workbook([row,row])
    b = workbook([row,row,['2026-02-01','MODELRED',5,'A']])
    p,_,issues = load_files([('매입_a.xlsx',a),('매입_b.xlsx',b),('copy.xlsx',a)])
    assert len(p) == 3 and p.qty.sum() == 2005
    assert len(issues) == 3
    p,_,_ = load_files([('a.xlsx',a),('b.xlsx',b)],False)
    assert len(p) == 5


def test_invalid_and_returns():
    rows = [['bad','M',3,'A'],['2026-01-01','',3,'A'],['2026-01-01','M','bad','A'],['2026-01-01','M',-1,'']]
    p,_,issues = load_files([('매입.xlsx',workbook(rows))])
    assert len(p) == 1 and p.qty.iloc[0] == -1
    assert len(issues) == 5


def test_demo_headers_and_years():
    p,s,issues = load_files(demo_files())
    assert len(p) == 89 and len(s) == 265
    assert set(s.date.dt.year) == {2025,2026}
    assert len(issues) == 1


def test_summary_rows_with_valid_dates_codes_are_excluded():
    rows = [['2026-01-01','MODEL',10,'A'],['2026-01-01','MODEL',10,'소계'],
            ['2026-01-01','MODEL',10,'A 총계'],['2026-01-01','합 계',10,'A']]
    p,_,issues = load_files([('매입.xlsx',workbook(rows))])
    assert len(p) == 1 and p.qty.sum() == 10
    assert len(issues) == 3


def test_repository_discovery(tmp_path):
    (tmp_path/'data'/'2026').mkdir(parents=True)
    (tmp_path/'매입_10.31.xlsx').write_bytes(b'root')
    (tmp_path/'data'/'2026'/'금년도 판매.XLSX').write_bytes(b'sale')
    (tmp_path/'~$temp.xlsx').write_bytes(b'ignore')
    (tmp_path/'other').mkdir()
    (tmp_path/'other'/'ignore.xlsx').write_bytes(b'ignore')
    assert len(repository_files(tmp_path)) == 2
