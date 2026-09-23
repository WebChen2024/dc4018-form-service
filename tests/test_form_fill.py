import os
import sys
import zipfile
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import form_fill  # noqa: E402


def _base_kwargs(**overrides):
    kwargs = dict(
        applicant_name='測試同仁', emp_id='T0001', dept='總務處保管組',
        phone='12345', email='test@mail.shu.edu.tw',
        need='測試需求說明',
        headcount='50人',
        security_selected=form_fill.DEFAULT_SECURITY_SELECTED,
        benefit_selected=form_fill.DEFAULT_BENEFIT_SELECTED,
        date=date(2026, 9, 23),
    )
    kwargs.update(overrides)
    return kwargs


def test_fill_smoke(tmp_path):
    out = tmp_path / 'out.docx'
    warnings, pages = form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out), **_base_kwargs())
    assert out.exists()
    assert zipfile.is_zipfile(out)
    # 沒有 LibreOffice 的沙盒環境裡 pages 會是 None；有的話應該是 1 頁。
    if pages is not None:
        assert pages == 1
    assert warnings == []


def test_checkbox_selection_roundtrip(tmp_path):
    out = tmp_path / 'out.docx'
    form_fill.fill(
        form_fill.DEFAULT_TEMPLATE, str(out),
        **_base_kwargs(
            security_selected=['包含個人基本資料', '系統權限之新增或異動申請'],
            benefit_selected=['提昇教學及研究品質'],
        ),
    )
    # form_fill.verify() 已經在 fill() 內部斷言過勾選狀態正確；這裡再次呼叫 fill()
    # 對同一個 out path 換一組選項，確認「取消勾選」也會正確還原成方框（不是只會勾、
    # 不會消）。
    form_fill.fill(
        form_fill.DEFAULT_TEMPLATE, str(out),
        **_base_kwargs(security_selected=[], benefit_selected=[]),
    )


def test_missing_required_field_raises(tmp_path):
    out = tmp_path / 'out.docx'
    with pytest.raises(SystemExit):
        form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out), **_base_kwargs(applicant_name='  '))


def test_unknown_checkbox_option_rejected(tmp_path):
    out = tmp_path / 'out.docx'
    with pytest.raises(ValueError):
        form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out), **_base_kwargs(security_selected=['不存在的選項']))
