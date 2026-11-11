from pathlib import Path
from streamlit.testing.v1 import AppTest
from demo import demo_files


def test_empty_repository():
    app = AppTest.from_file(str(Path(__file__).parents[1]/'app.py'), default_timeout=60).run()
    assert not app.exception


def test_repository_excel_default(tmp_path):
    import shutil
    root = Path(__file__).parents[1]
    for filename in ('app.py','loader.py','engine.py','demo.py'):
        shutil.copyfile(root/filename, tmp_path/filename)
    (tmp_path/'data').mkdir()
    for filename, content in demo_files():
        (tmp_path/'data'/filename).write_bytes(content)
    app = AppTest.from_file(str(tmp_path/'app.py'), default_timeout=60).run()
    assert not app.exception
    assert len(app.metric) == 4
    app.radio[0].set_value('가상 예시 데이터').run()
    assert not app.exception
    assert len(app.metric) == 4
    app.multiselect[0].set_value([2026]).run()
    assert not app.exception
    app.multiselect[1].set_value([]).run()
    assert not app.exception
    app.radio[0].set_value('내 엑셀 업로드').run()
    assert not app.exception
