"""M3：Flask 送出流程的回歸測試——識別資料覆寫語意、超頁擋下、歸檔不互相覆蓋。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_module  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'DB_PATH', str(tmp_path / 'identities.db'))
    monkeypatch.setattr(app_module, 'ARCHIVE_DIR', str(tmp_path / 'archive'))
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


def _valid_payload(**overrides):
    payload = dict(
        emp_id='T0001', name='測試同仁', dept='總務處保管組', phone='12345',
        email='test@mail.shu.edu.tw', need='測試需求說明', headcount='50人',
        security=['需區隔使用者權限'], benefit=['精進作業程序、強化行政效率'],
        roc_year='115', roc_month='9', roc_day='23',
    )
    payload.update(overrides)
    return payload


def _archive_files(tmp_path):
    archive_dir = tmp_path / 'archive'
    if not archive_dir.exists():
        return []
    return [p for p in archive_dir.rglob('*') if p.is_file()]


def test_lookup_not_found_before_any_submission(client):
    assert client.get('/lookup/NOPE').get_json() == {'found': False}


def test_submit_then_lookup_autofill(client):
    resp = client.post('/submit', data=_valid_payload())
    assert resp.status_code == 200
    assert resp.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

    data = client.get('/lookup/T0001').get_json()
    assert data == {
        'found': True, 'name': '測試同仁', 'dept': '總務處保管組',
        'phone': '12345', 'email': 'test@mail.shu.edu.tw',
    }


def test_second_submission_same_emp_id_overwrites_not_accumulates(client):
    """規格書：「可覆寫更新」——第二次送出後查到的應該是最新一筆，不是歷史清單。"""
    client.post('/submit', data=_valid_payload())
    client.post('/submit', data=_valid_payload(name='改名後的同仁', dept='新單位', phone='99999',
                                                email='new@mail.shu.edu.tw'))
    data = client.get('/lookup/T0001').get_json()
    assert data['name'] == '改名後的同仁'
    assert data['dept'] == '新單位'
    assert data['phone'] == '99999'
    assert data['email'] == 'new@mail.shu.edu.tw'


def test_submit_missing_required_field_returns_400_and_does_not_save_identity(client):
    payload = _valid_payload(emp_id='E_MISSING')
    del payload['email']
    resp = client.post('/submit', data=payload)
    assert resp.status_code == 400
    assert 'E-Mail' in resp.get_data(as_text=True)
    # 必填檢查沒過，不該留下這個員工編號的識別資料紀錄
    assert client.get('/lookup/E_MISSING').get_json() == {'found': False}


def test_submit_need_overflow_blocks_but_keeps_identity_for_resubmit(client, tmp_path):
    need = '\n'.join(f'測試需求說明第{i:02d}行內容再加一些字撐長一點剛好接近整行寬度囉' for i in range(1, 10))
    resp = client.post('/submit', data=_valid_payload(need=need))
    assert resp.status_code == 400
    assert '超過安全範圍' in resp.get_data(as_text=True)
    assert _archive_files(tmp_path) == []
    # 識別資料已經記住，讓使用者改短需求說明後可以直接重送，不用重打身份欄位
    assert client.get('/lookup/T0001').get_json()['found'] is True


def test_submit_headcount_overflow_does_not_block_download(client):
    resp = client.post('/submit', data=_valid_payload(headcount='一二三四五六七八九十一二三'))
    assert resp.status_code == 200


def test_two_submissions_same_day_produce_two_distinct_archive_entries(client, tmp_path):
    r1 = client.post('/submit', data=_valid_payload(emp_id='A001'))
    r2 = client.post('/submit', data=_valid_payload(emp_id='A002'))
    assert r1.status_code == 200 and r2.status_code == 200

    files = _archive_files(tmp_path)
    docx_files = [f for f in files if f.suffix == '.docx']
    json_files = [f for f in files if f.suffix == '.json']
    assert len(docx_files) == 2, '兩筆送出應該各自留一份 docx，檔名不該互相覆蓋'
    assert len(json_files) == 2
    assert len({f.name for f in docx_files}) == 2  # 檔名確實不同


def test_archive_json_record_matches_submission(client, tmp_path):
    client.post('/submit', data=_valid_payload(emp_id='B001', need='紀錄比對用需求說明'))
    json_files = [f for f in _archive_files(tmp_path) if f.suffix == '.json']
    assert len(json_files) == 1
    record = json.loads(json_files[0].read_text(encoding='utf-8'))
    assert record['emp_id'] == 'B001'
    assert record['need'] == '紀錄比對用需求說明'
    assert record['security_selected'] == ['需區隔使用者權限']
    assert record['warnings'] == []


def test_invalid_date_returns_400(client):
    resp = client.post('/submit', data=_valid_payload(roc_month='13'))
    assert resp.status_code == 400
    assert '申請日期' in resp.get_data(as_text=True)
