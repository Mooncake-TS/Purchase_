"""Excel normalization, provenance, and conservative duplicate handling."""
from io import BytesIO
import hashlib
import re
import unicodedata
import pandas as pd

COLS = ['date','code','name','qty','partner','amount','source','sheet','row','signature','occurrence']


def repository_files(root):
    """Read root and data recursively; root is the directory containing app.py."""
    from pathlib import Path
    root = Path(root)
    paths = list(root.glob('*')) + list((root/'data').rglob('*'))
    return [(str(p.relative_to(root)), p.read_bytes()) for p in sorted(set(paths))
            if p.is_file() and p.suffix.lower() in ('.xlsx', '.xls') and not p.name.startswith('~$')]


def is_summary(row):
    # Check labels rather than numeric totals; the column named 합계 is valid.
    for value in row:
        text = re.sub(r'\s+', '', clean(value)).lower()
        if re.fullmatch(r'[\[\(【]*?(소계|총계|합계|총합계|누계|subtotal|grandtotal|total)[\]\)】:：]*', text):
            return True
        if re.search(r'(소계|총계|합계|누계)(?:[\]\)】:：]*)$', text):
            return True
    return False


def clean(value):
    return '' if pd.isna(value) else unicodedata.normalize('NFKC', str(value)).strip()


def code(value):
    return re.sub(r'\s+', '', clean(value)).upper()


def parse_date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (int, float)):
        if 20000 < value < 80000:
            return pd.Timestamp('1899-12-30') + pd.to_timedelta(value, unit='D')
    text = clean(value)
    if re.fullmatch(r'\d{8}', text):
        return pd.to_datetime(text, format='%Y%m%d', errors='coerce')
    match = re.match(r'^(\d{4})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})', text)
    if match:
        return pd.to_datetime('-'.join(match.groups()), errors='coerce')
    if isinstance(value, (pd.Timestamp,)) or hasattr(value, 'year'):
        return pd.Timestamp(value).normalize()
    return pd.NaT  # Never guess a year from filename or runtime clock.


def number(value):
    text = clean(value).replace(',', '').replace('₩', '').replace(' ', '')
    if text.startswith('(') and text.endswith(')'):
        text = '-'+text[1:-1]
    result = pd.to_numeric(text, errors='coerce')
    return result if pd.notna(result) and abs(result) != float('inf') else float('nan')


def load_files(files, deduplicate=True):
    """files: [(filename, bytes)]. Overlap removal preserves within-file multiplicity."""
    tables = {'purchase': [], 'sale': []}
    issues, hashes = [], set()
    for filename, content in files:
        digest = hashlib.sha256(content).hexdigest()
        if digest in hashes:
            issues.append(dict(source=filename, sheet='', row=0, reason='동일 파일 내용: 제외'))
            continue
        hashes.add(digest)
        try:
            workbook = pd.read_excel(BytesIO(content), sheet_name=None, header=None, dtype=object)
        except Exception as exc:
            issues.append(dict(source=filename, sheet='', row=0, reason=f'읽기 실패: {exc}'))
            continue
        for sheet, raw in workbook.items():
            header, kind = None, None
            for i in range(min(20, len(raw))):
                values = [clean(v) for v in raw.iloc[i]]
                if {'일자-No.', '품목코드', '수량'}.issubset(values):
                    header, kind = i, 'purchase'
                    break
                if {'일자', '모델번호', '수량'}.issubset(values):
                    header, kind = i, 'sale'
                    break
            if header is None:
                issues.append(dict(source=filename, sheet=sheet, row=0, reason='필수 헤더 미발견: 시트 제외'))
                continue
            hinted = 'purchase' if '매입' in filename else 'sale' if any(v in filename for v in ('매출','판매','금년도','전년도')) else None
            if hinted and hinted != kind:
                issues.append(dict(source=filename, sheet=sheet, row=0, reason='파일명/헤더 분류 불일치: 헤더 우선'))
            frame = raw.iloc[header+1:].copy()
            headers = [clean(v) for v in raw.iloc[header]]
            if len([v for v in headers if v]) != len(set(v for v in headers if v)):
                issues.append(dict(source=filename, sheet=sheet, row=header+1, reason='중복 헤더: 시트 제외'))
                continue
            frame.columns = headers
            datecol, codecol, namecol, partnercol = ('일자-No.','품목코드','품목명(규격)','거래처명') if kind == 'purchase' else ('일자','모델번호','품명 및 규격','판매처명')
            seen, rows = {}, []
            for idx, r in frame.iterrows():
                if all(not clean(v) for v in r):
                    continue
                issue = dict(source=filename, sheet=sheet, row=int(idx)+1)
                if is_summary(r):
                    issues.append({**issue, 'reason':'소계·총계·합계·누계 행: 제외'})
                    continue
                dt, item, qty = parse_date(r[datecol]), code(r[codecol]), number(r['수량'])
                if pd.isna(dt) or not item or pd.isna(qty):
                    issues.append({**issue, 'reason':'날짜/코드/수량 누락·오류 또는 합계행: 제외'})
                    continue
                partner = clean(r.get(partnercol, '')) or ('매입처 미상' if kind == 'purchase' else '판매처 미상')
                if partner.endswith('미상'):
                    issues.append({**issue, 'reason':'거래처 누락: 미상으로 포함'})
                if qty <= 0:
                    issues.append({**issue, 'reason':'반품·음수 또는 0 수량: 원장 포함, FIFO 제외'})
                signature = repr((kind, str(dt), item, float(qty), tuple((str(k), clean(v)) for k,v in r.items() if k)))
                seen[signature] = seen.get(signature, 0)+1
                rows.append(dict(date=dt, code=item, name=clean(r.get(namecol,'')), qty=float(qty),
                    partner=partner, amount=number(r.get('공급가액','')), **issue,
                    signature=signature, occurrence=seen[signature]))
            tables[kind].extend(rows)
    result = []
    for kind in ('purchase','sale'):
        df = pd.DataFrame(tables[kind], columns=COLS)
        duplicate = df.duplicated(['signature','occurrence'])
        for _, r in df[duplicate].iterrows():
            issues.append(dict(source=r.source, sheet=r.sheet, row=r.row,
                reason='파일·시트 간 동일행 후보: '+('제외' if deduplicate else '유지')))
        if deduplicate:
            df = df[~duplicate]
        df = df.reset_index(drop=True)
        df['date'] = pd.to_datetime(df['date'])
        df['qty'] = pd.to_numeric(df['qty'])
        result.append(df)
    return *result, pd.DataFrame(issues, columns=['source','sheet','row','reason'])
