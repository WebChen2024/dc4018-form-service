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


# ---------------------------------------------------------------- M3 regression matrix
def _need_lines(n):
    """產生 n 個段落，每段落刻意控制在 NEED_CHARS_PER_LINE(27) 全形字以內，確保
    estimate_lines() 對每一段只算 1 行——n 個段落就對應 n 行，才能準確測試
    NEED_MAX_LINES 這個行數門檻本身，不會被單一段落自己換行的部分混進來。"""
    return '\n'.join(f'測試需求說明第{i:02d}行內容' for i in range(1, n + 1))


@pytest.mark.parametrize('n_lines', [7, 8])
def test_need_within_safe_line_count_has_no_overflow_warning(tmp_path, n_lines):
    out = tmp_path / 'out.docx'
    warnings, _ = form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out), **_base_kwargs(need=_need_lines(n_lines)))
    assert not any(w['code'] == 'need_overflow' for w in warnings), warnings


def test_need_over_safe_line_count_warns_overflow(tmp_path):
    out = tmp_path / 'out.docx'
    warnings, _ = form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out), **_base_kwargs(need=_need_lines(9)))
    assert any(w['code'] == 'need_overflow' for w in warnings), warnings


def test_headcount_over_one_line_warns_but_still_produces_file(tmp_path):
    out = tmp_path / 'out.docx'
    # HEADCOUNT_CHARS_PER_LINE=11，13 個全形字必超過一行。
    warnings, _ = form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out), **_base_kwargs(headcount='一二三四五六七八九十一二三'))
    assert any(w['code'] == 'headcount_overflow' for w in warnings), warnings
    assert out.exists()  # 只是截字風險，不擋出檔


@pytest.mark.parametrize('security_selected,benefit_selected', [
    (form_fill.SECURITY_OPTIONS, form_fill.BENEFIT_OPTIONS),  # 全選
    ([], []),                                                  # 全不選
    (['其它，請於下方空白處填寫'], ['其它，請於下方空白處填寫']),  # 非預設值組合
])
def test_checkbox_combinations_written_correctly(tmp_path, security_selected, benefit_selected):
    """獨立於 form_fill.verify() 之外，直接重新開啟成品讀取勾選狀態，避免測試跟production
    程式碼共用同一段邏輯而看不出彼此都有的 bug（tautology）。"""
    out = tmp_path / 'out.docx'
    form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out),
                    **_base_kwargs(security_selected=security_selected, benefit_selected=benefit_selected))

    with zipfile.ZipFile(out) as z:
        from lxml import etree
        root = etree.fromstring(z.read('word/document.xml'))
    tbl = form_fill.main_table(root)

    for tc_label, options, selected in [
        ('安全要求', form_fill.SECURITY_OPTIONS, security_selected),
        ('效益評估', form_fill.BENEFIT_OPTIONS, benefit_selected),
    ]:
        tc = form_fill.cell_right_of(tbl, tc_label)
        text = form_fill.cell_text(tc)
        for option in options:
            expect_checked = option in selected
            marker_char = form_fill.CHECKBOX_CHECKED_CHAR if expect_checked else form_fill.CHECKBOX_UNCHECKED_CHAR
            assert marker_char + option in text, (
                f'{tc_label}「{option}」預期 {"已勾選" if expect_checked else "未勾選"}，但在成品裡讀不到對應符號'
            )


def test_two_consecutive_fills_do_not_leak_state_between_options(tmp_path):
    """先勾兩個選項存檔，再用同一個 out path 換成完全不同的另一組選項，確認舊的勾選
    痕跡（尤其是「取消勾選」要真的換回方框，不是殘留 ●）不會跨兩次呼叫殘留。"""
    out = tmp_path / 'out.docx'
    form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out),
                    **_base_kwargs(security_selected=['包含個人基本資料', '系統權限之新增或異動申請'],
                                    benefit_selected=['提昇教學及研究品質']))
    form_fill.fill(form_fill.DEFAULT_TEMPLATE, str(out),
                    **_base_kwargs(security_selected=['報表應標示警語'], benefit_selected=[]))

    with zipfile.ZipFile(out) as z:
        from lxml import etree
        root = etree.fromstring(z.read('word/document.xml'))
    tbl = form_fill.main_table(root)
    security_text = form_fill.cell_text(form_fill.cell_right_of(tbl, '安全要求'))
    benefit_text = form_fill.cell_text(form_fill.cell_right_of(tbl, '效益評估'))

    assert '●報表應標示警語' in security_text
    assert '●包含個人基本資料' not in security_text
    assert '●系統權限之新增或異動申請' not in security_text
    assert '●' not in benefit_text
