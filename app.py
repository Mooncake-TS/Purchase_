from pathlib import Path
from datetime import date
import pandas as pd
import plotly.express as px
import streamlit as st
from loader import load_files, repository_files
from engine import match_models, fifo, cohort_rates
from demo import demo_files

st.set_page_config(page_title='매입 → 판매 흐름', page_icon='📊', layout='wide')
st.title('매입 → 판매 흐름')
st.caption('입고부터 판매까지 · 모델 단위 분석 · 매입처별 FIFO 추정')
with st.sidebar:
    st.header('데이터 및 분석 조건')
    mode = st.radio('데이터 선택', ['GitHub 저장소 엑셀 자동 연결', '가상 예시 데이터', '내 엑셀 업로드'])
    st.button('저장소 파일 다시 읽기')
    uploaded = st.file_uploader('매입·전년도 판매·금년도 판매 엑셀', type=['xlsx','xls'], accept_multiple_files=True)
    dedup = st.checkbox('파일·시트 간 동일행 후보 자동 제외', value=True)
    st.caption('같은 파일 내부의 반복 거래는 보존합니다. 서로 다른 거래가 완전히 같으면 중복으로 판단될 수 있으니 검증 탭을 확인하세요.')
if mode == '가상 예시 데이터':
    files = demo_files()
    st.info('현재 화면의 모든 예시 데이터는 가상입니다. 사용자 실제 데이터가 아닙니다.')
elif mode == '내 엑셀 업로드':
    files = [(f.name, f.getvalue()) for f in uploaded]
else:
    files = repository_files(Path(__file__).parent)
if not files:
    st.info('GitHub 저장소의 app.py 옆 또는 data 폴더에 엑셀을 업로드하고 변경사항을 저장하세요. 배포 앱에 변경이 반영되면 자동으로 읽습니다. 먼저 둘러보려면 왼쪽에서 가상 예시 데이터를 선택하세요.')
    st.stop()
with st.expander(f'연결된 파일 {len(files)}개'):
    st.write([name for name, _ in files])
p, s, issues = load_files(files, dedup)
if not issues.empty:
    st.info(f'데이터 점검 항목 {len(issues):,}건이 있습니다. 제외 행과 반품 내역은 데이터 검증 탭에서 확인하세요.')
if p.empty or s.empty:
    st.error('분석하려면 유효한 매입과 판매 데이터가 모두 필요합니다.')
    st.dataframe(issues, hide_index=True)
    st.stop()
p, s = match_models(p, s)
minimum = min(p.date.min(), s.date.min()).date()
maximum = max(p.date.max(), s.date.max()).date()
with st.sidebar:
    cutoff = st.date_input('분석 기준일 / 판매 관찰 종료일', maximum, min_value=minimum)
    st.caption('기준일까지 업로드한 판매자료가 빠짐없이 있다는 가정입니다. 파일명 날짜로 자료 완전성을 보장하지 않습니다.')
    period = st.date_input('화면 표시 기간', (minimum, max(minimum, min(maximum, cutoff))), min_value=minimum)
    years = st.multiselect('판매연도', sorted(s.date.dt.year.unique().tolist()), default=sorted(s.date.dt.year.unique().tolist()))
    suppliers = st.multiselect('매입처', sorted(p.partner.unique()), default=sorted(p.partner.unique()))
    selected_models = st.multiselect('모델', sorted(set(p.model)-{''}), default=[])
    st.caption('모델 미선택은 전체입니다. 기간·연도·매입처 필터는 전체 FIFO 계산 후 적용됩니다.')
if len(period) != 2 or period[0] > period[1]:
    st.info('표시 시작일과 종료일을 선택해 주세요.')
    st.stop()
start, end = pd.Timestamp(period[0]), min(pd.Timestamp(period[1]), pd.Timestamp(cutoff))
lots, allocation, excess = fifo(p, s, cutoff)
models = selected_models or sorted(set(s.model) | set(p.model))
lp = lots[lots.supplier.isin(suppliers) & lots.model.isin(models) & lots.date.between(start,end)]
ap = allocation[allocation.supplier.isin(suppliers) & allocation.model.isin(models) & allocation.sale_date.between(start,end) & allocation.sale_date.dt.year.isin(years)]
pv = p[p.partner.isin(suppliers) & p.model.isin(models) & p.date.between(start,end)]
sv = s[s.model.isin(models) & s.date.between(start,end) & s.date.dt.year.isin(years)]
st.warning('소진율·매입처별 판매는 입고 코호트와 FIFO에 따른 추정입니다. 실제 현재 재고를 계산하지 않습니다. 색상·사이즈는 합치며, 반품·음수 수량은 FIFO에서 제외합니다. 동일 날짜는 입고 후 판매 순서, 같은 날 복수 매입처는 입력 순서로 배분됩니다.')
c1,c2,c3,c4 = st.columns(4)
c1.metric('선택 매입처 · 양수 매입', f'{pv.loc[pv.qty>0,"qty"].sum():,.0f}')
c2.metric('전체 판매처 · 양수 판매', f'{sv.loc[sv.qty>0,"qty"].sum():,.0f}')
c3.metric('선택 매입처 · FIFO 판매', f'{ap.qty.sum():,.0f}')
c4.metric('판매까지 가중평균 일수', f'{(ap.days*ap.qty).sum()/ap.qty.sum():,.1f}일' if ap.qty.sum() else '—')
st.caption('표시 기간 기준 수량입니다. 전체 판매처 원장에는 매입처 정보가 없으므로 매입처 필터는 FIFO 판매에만 적용됩니다.')
tabs = st.tabs(['전체 흐름','매입처별 판매','입고 코호트 소진율','모델 상세','데이터 검증'])

def chart_daily(frame, datecol, group=None):
    if frame.empty:
        st.info('선택 조건에 해당하는 데이터가 없습니다.')
        return
    keys = [datecol]+([group] if group else [])
    chart = frame.groupby(keys, as_index=False).qty.sum()
    st.plotly_chart(px.line(chart, x=datecol, y='qty', color=group, markers=True,
        labels={datecol:'날짜','qty':'수량','supplier':'매입처'}), use_container_width=True)


def table(frame, name):
    labels = {'date':'거래일','code':'원본 코드','name':'품명','qty':'수량','partner':'거래처',
        'amount':'공급가액','source':'파일','sheet':'시트','row':'엑셀 행','reason':'검증 내용',
        'model':'모델','match_status':'연결 결과','candidates':'접두 일치 후보',
        'lot_id':'입고 묶음 번호','purchase_date':'입고일','sale_date':'판매일',
        'supplier':'추정 매입처','days':'입고 후 경과일','remaining':'미배분 입고수량'}
    frame = frame.rename(columns=labels)
    st.dataframe(frame, use_container_width=True, hide_index=True)
    # Prevent spreadsheet formula evaluation in user-originated CSV text cells.
    export = frame.copy()
    for col in export.select_dtypes(include=['object','string']).columns:
        export[col] = export[col].map(lambda x: "'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x)
    st.download_button('CSV 다운로드', export.to_csv(index=False).encode('utf-8-sig'), file_name=name+'.csv', key=name)

with tabs[0]:
    st.subheader('날짜별 매입 / 판매 원장')
    st.caption('음수 반품을 포함한 순수량입니다. 입고와 판매의 날짜를 각각 사용합니다.')
    flow = pd.concat([pv[['date','qty']].assign(구분='선택 매입처 매입'),sv[['date','qty']].assign(구분='전체 판매처 판매')])
    chart_daily(flow, 'date', '구분')
    st.subheader('입고 후 판매까지 걸린 시간')
    if not ap.empty:
        st.plotly_chart(px.histogram(ap, x='days', y='qty', histfunc='sum', nbins=30, labels={'days':'입고 후 경과일','qty':'추정 판매수량'}), use_container_width=True)
with tabs[1]:
    st.subheader('매입처별 날짜별 추정 판매')
    chart_daily(ap, 'sale_date', 'supplier')
    table(ap.groupby('supplier', as_index=False).agg(추정판매수량=('qty','sum')), 'supplier_summary')
with tabs[2]:
    st.subheader('입고일 기준 30 / 60 / 90 / 180일 소진율')
    st.caption('표시 기간에 입고된 물량 중 기준일까지 각 관찰기간이 끝난 입고만 분모에 포함합니다. 판매연도 필터는 이 탭에 적용하지 않습니다. 입고일부터 기준일까지의 전체 판매를 사용합니다. 30일은 입고 당일~30일 후를 포함합니다.')
    table(cohort_rates(lp, allocation, cutoff), 'cohort_rates')
    if not lp.empty:
        monthly = []
        for month, group in lp.groupby(lp.date.dt.to_period('M')):
            monthly.append(cohort_rates(group, allocation, cutoff).assign(입고월=str(month)))
        table(pd.concat(monthly, ignore_index=True), 'monthly_cohorts')
with tabs[3]:
    model = st.selectbox('상세 모델', sorted(set(s.model)))
    st.caption('아래 매입 원장은 선택 매입처, 판매 원장은 전체 판매처 기준입니다.')
    st.write('매입 원장')
    table(pv[pv.model==model].drop(columns=['signature','occurrence']), 'model_purchases')
    st.write('판매 원장')
    table(sv[sv.model==model].drop(columns=['signature','occurrence']), 'model_sales')
    st.write('입고 → 판매 배분 내역')
    table(ap[ap.model==model], 'model_allocations')
with tabs[4]:
    st.caption('이 탭은 표시 필터와 관계없이 전체 입력을 점검합니다. 초과판매만 분석 기준일까지 계산합니다.')
    st.write('읽기 오류 / 누락 / 중복 / 반품')
    table(issues, 'validation')
    st.write('모델 연결 검증 — 가장 긴 접두 모델 우선')
    table(p[['code','model','match_status','candidates']].drop_duplicates(), 'model_matches')
    st.write('매입에 연결되지 않은 판매 모델')
    table(s[~s.model.isin(p.model)][['model','qty','date','source','row']], 'unmatched_sales')
    st.write('과거 입고로 배분할 수 없는 판매')
    st.caption('입고 이전 판매·입고자료 누락·수량 초과 등이 원인일 수 있습니다. 미래 입고에 소급 배분하지 않습니다.')
    table(excess, 'unallocated_sales')
    st.write('반품 / 0 수량 원장 — FIFO와 소진율에서 제외')
    table(pd.concat([p[p.qty<=0].assign(종류='매입'),s[s.qty<=0].assign(종류='판매')], ignore_index=True).drop(columns=['signature','occurrence']), 'returns')
