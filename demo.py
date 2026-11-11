"""All records in this module are fictional, not the user's data."""
from io import BytesIO
import pandas as pd


def demo_files():
    pcols = ['일자-No.','품목코드','품목명(규격)','수량','단가','공급가액','부가세','합계','거래처명']
    scols = ['일자','판매처명','창고명','품명 및 규격','모델번호','COLOR','SIZE','수량','단가','공급가액','부가세','합계']
    p, s = [], []
    models = ['TF31KS019','TF31KS020','LONGMODEL2026X','AB12']
    for month in range(1, 23):
        dt = pd.Timestamp('2025-01-01') + pd.DateOffset(months=month-1)
        for j, model in enumerate(models):
            p.append([f'{dt:%Y/%m/%d}-{j+1}',model+'BLK008',f'가상 상품 {j+1}',100,10000,1000000,100000,1100000,['가상 매입처 A','가상 매입처 B'][month%2]])
            for day, qty in ((8,25),(20,35),(27,20)):
                s.append([dt.replace(day=day),'가상 판매처','가상 창고',f'가상 상품 {j+1}',model,'BLK','008',qty,20000,qty*20000,qty*2000,qty*22000])
    p.append(['2026/10/15-1','UNKNOWNBLK008','미매칭 예시',10,10000,100000,10000,110000,'가상 매입처 C'])
    s.append([pd.Timestamp('2026-10-28'),'가상 판매처','가상 창고','반품 예시','TF31KS019','BLK','008',-3,20000,-60000,-6000,-66000])
    def excel(frame, sale=False):
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            frame.to_excel(writer, index=False, startrow=1 if sale else 0)
            if sale:
                writer.sheets['Sheet1'].cell(1,1,'가상회사 — 시연 전용')
        return out.getvalue()
    sales = pd.DataFrame(s, columns=scols)
    return [('매입_10.31.xlsx', excel(pd.DataFrame(p, columns=pcols))),
            ('전년도 판매.xlsx', excel(sales[sales['일자'].dt.year == 2025], True)),
            ('금년도 판매_10.31.xlsx', excel(sales[sales['일자'].dt.year == 2026], True))]
