from pathlib import Path
import shutil
from io import BytesIO
import pandas as pd
from streamlit.testing.v1 import AppTest


def test_unmatched_data_renders(tmp_path):
    root = Path(__file__).parents[1]
    for filename in ('app.py','loader.py','engine.py','demo.py'):
        shutil.copyfile(root/filename, tmp_path/filename)
    p = pd.DataFrame({'일자-No.':['2026-01-01-1'], '품목코드':['OTHER'], '수량':[10]})
    s = pd.DataFrame({'일자':['2026-01-02'], '모델번호':['MODEL'], '수량':[2]})
    p.to_excel(tmp_path/'매입.xlsx',index=False)
    s.to_excel(tmp_path/'판매.xlsx',index=False,startrow=1)
    app = AppTest.from_file(str(tmp_path/'app.py'), default_timeout=60).run()
    assert not app.exception
    assert len(app.metric) == 4
