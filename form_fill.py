#!/usr/bin/env python3
"""Fill the 世新大學「系統開發維護需求單」(DC-4018 v1.6) Word template — multi-user version.

移植自 shu-system-request-form skill 的 scripts/fill_form.py，把原本寫死的申請人姓名/
員工編號/單位/電話/Email/安全要求/效益評估全部改成參數，供 Flask app 依每次送出的表單
資料動態產生。版面規則（A4 單頁、需求說明列高、日期格式）完全沿用，不重新設計。

版面事實（實測 template.docx 得出，維護用）：
  - 表格 row1 cell0 是「申請人姓名」+「員工編號」兩個 label 疊在同一個 cell 的兩個段落，
    對應的 value cell（row1 cell1）也是兩個段落——所以這兩欄用 cell_right_of() 傳入合併
    後的 label 文字「申請人姓名員工編號」去比對，再用 set_cell_paragraphs() 寫兩行。
  - 單位／電話／E-Mail 各自是獨立的 label cell，跟原本需求說明/預估使用人數/申請日期
    用同一套 cell_right_of() 機制。
  - 安全要求／效益評估是複選：每個選項是「勾選符號 run」+「選項文字 run」兩個相鄰的
    run。未勾選＝Wingdings 2 字型、字元 U+F0A3；已勾選＝minorEastAsia 佈景字型、字元
    「●」。用 set_checkboxes() 依「這次選了哪些」把每個選項的符號 run 重寫成對應狀態，
    不依賴模板原本的勾選狀態（模板目前預設勾的是「需區隔使用者權限」「擴大對學生之服務
    能量」，跟本系統表單前端的預設值不一定一致，但無所謂——每次送出都是全量覆寫）。
"""
import argparse
import copy
import datetime
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from zoneinfo import ZoneInfo

from lxml import etree

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W_NS}
W = '{%s}' % W_NS
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, 'assets', 'template.docx')

# 複選選項固定清單，順序即前端 checkbox 呈現順序（跟模板文件裡的順序一致）。
SECURITY_OPTIONS = [
    '包含個人基本資料',
    '需區隔使用者權限',
    '報表應標示警語',
    '系統權限之新增或異動申請',
    '其它，請於下方空白處填寫',
]
BENEFIT_OPTIONS = [
    '提昇教學及研究品質',
    '擴大對學生之服務能量',
    '精進作業程序、強化行政效率',
    '其它，請於下方空白處填寫',
]

# 規格書 v1.0 定案的預設勾選值
DEFAULT_SECURITY_SELECTED = ['需區隔使用者權限']
DEFAULT_BENEFIT_SELECTED = ['精進作業程序、強化行政效率']

CHECKBOX_UNCHECKED_CHAR = ''
CHECKBOX_CHECKED_CHAR = '●'

# Layout facts measured from the template (12pt 標楷體/Arial), unchanged from原single-user腳本:
NEED_CHARS_PER_LINE = 27       # 需求說明 cell ≈ 27 全形字/行
NEED_MAX_LINES = 8             # 2600-twip 列高下，9 行起溢出到第2頁（保守字型估計）
HEADCOUNT_CHARS_PER_LINE = 11  # 預估使用人數 cell 列高固定，第2行會被截掉

SOFFICE_PY_CANDIDATES = [
    os.environ.get('SOFFICE_PY', ''),
    '/mnt/skills/public/docx/scripts/office/soffice.py',
]


# ---------------------------------------------------------------- text/layout helpers
def paras_of(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip('\n')
    return [ln.rstrip() for ln in text.split('\n')]


def display_width(s):
    """Width in half-width units (full-width CJK = 2)."""
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def estimate_lines(paragraphs, chars_per_line):
    return sum(max(1, math.ceil(display_width(p) / (chars_per_line * 2))) for p in paragraphs)


def cell_text(tc):
    return '\n'.join(''.join(t.text or '' for t in p.iter(W + 't')) for p in tc.findall('w:p', NS))


def cell_right_of(tbl, label):
    """The cell immediately to the right of the cell whose whole text is `label`."""
    want = label.replace(' ', '')
    for tr in tbl.findall('w:tr', NS):
        tcs = tr.findall('w:tc', NS)
        for i, tc in enumerate(tcs[:-1]):
            if ''.join(t.text or '' for t in tc.iter(W + 't')).replace(' ', '').replace('\n', '') == want:
                return tcs[i + 1]
    raise KeyError('label not found in template: ' + label)


def make_run(text, *, underline=False, arial=False, hint=False):
    r = etree.Element(W + 'r')
    rpr = etree.SubElement(r, W + 'rPr')
    f = etree.SubElement(rpr, W + 'rFonts')
    if arial:
        f.set(W + 'ascii', 'Arial')
        f.set(W + 'hAnsi', 'Arial')
    f.set(W + 'eastAsia', '標楷體')
    if hint:
        f.set(W + 'hint', 'eastAsia')
    if underline:
        etree.SubElement(rpr, W + 'u').set(W + 'val', 'single')
    t = etree.SubElement(r, W + 't')
    t.text = text
    t.set(XML_SPACE, 'preserve')
    return r


def clear_runs(p):
    for child in list(p):
        if child.tag != W + 'pPr':
            p.remove(child)


def set_cell_paragraphs(tc, lines):
    """Replace the cell's content with `lines`, cloning the first paragraph's properties."""
    paras = tc.findall('w:p', NS)
    proto = paras[0]
    for extra in paras[1:]:
        tc.remove(extra)
    clear_runs(proto)
    pristine = copy.deepcopy(proto)  # run-free copy, taken before any text is added
    anchor = proto
    for i, line in enumerate(lines):
        p = proto if i == 0 else copy.deepcopy(pristine)
        if i > 0:
            anchor.addnext(p)
            anchor = p
        if line:
            p.append(make_run(line, arial=True, hint=True))


def roc_date_parts(d):
    """115年 9 月 21 日 — digits and their padding spaces underlined, 年/月/日 not."""
    return [(str(d.year - 1911), True), ('年', False), (' ', True), (f'{d.month} ', True),
            ('月', False), (' ', True), (f'{d.day} ', True), ('日', False)]


def roc_date_text(d):
    return ''.join(t for t, _ in roc_date_parts(d))


def set_date(tc, d):
    p = tc.find('w:p', NS)
    clear_runs(p)
    for text, ul in roc_date_parts(d):
        p.append(make_run(text, underline=ul))


def main_table(root):
    return next(root.iter(W + 'tbl'))


def all_cell_texts(root):
    tbl = main_table(root)
    return [[cell_text(tc) for tc in tr.findall('w:tc', NS)] for tr in tbl.findall('w:tr', NS)]


# ---------------------------------------------------------------- checkbox helpers
def find_checkbox_runs(tc, options):
    """在 tc 內找每個 option 文字 run 前面緊接的「勾選符號」run，回傳 {option: marker_run}。

    每個選項在文件裡都是「符號 run 緊接著文字 run」，符號 run 沒有自己的文字內容意義
    （純圖示），所以用「文字 run 的內容剛好等於某個 option 字串」來定位，取它在同一個
    <w:p> 裡的前一個 run 當 marker。找不到就直接炸掉——版面跟預期不符時，寧可讓 M1
    的手動驗證發現，也不要悄悄跳過某個選項。
    """
    found = {}
    for p in tc.findall('w:p', NS):
        runs = p.findall('w:r', NS)
        for i, r in enumerate(runs):
            t = r.find('w:t', NS)
            if t is not None and t.text in options and i > 0:
                found[t.text] = runs[i - 1]
    missing = [o for o in options if o not in found]
    if missing:
        raise KeyError(f'checkbox option(s) not found in template: {missing}')
    return found


def set_checkbox_marker(run, checked):
    """把一個勾選符號 run 重寫成勾選／未勾選的樣式。"""
    rpr = run.find(W + 'rPr')
    if rpr is None:
        rpr = etree.SubElement(run, W + 'rPr')
        run.insert(0, rpr)
    for child in list(rpr):
        rpr.remove(child)
    fonts = etree.SubElement(rpr, W + 'rFonts')
    t = run.find(W + 't')
    if t is None:
        t = etree.SubElement(run, W + 't')
    if checked:
        fonts.set(W + 'asciiTheme', 'minorEastAsia')
        fonts.set(W + 'eastAsiaTheme', 'minorEastAsia')
        fonts.set(W + 'hAnsiTheme', 'minorEastAsia')
        fonts.set(W + 'cs', 'Wingdings 2')
        fonts.set(W + 'hint', 'eastAsia')
        t.text = CHECKBOX_CHECKED_CHAR
    else:
        fonts.set(W + 'ascii', 'Wingdings 2')
        fonts.set(W + 'eastAsia', 'Wingdings 2')
        fonts.set(W + 'hAnsi', 'Wingdings 2')
        fonts.set(W + 'cs', 'Wingdings 2')
        t.text = CHECKBOX_UNCHECKED_CHAR
    t.set(XML_SPACE, 'preserve')


def set_checkboxes(tc, options, selected):
    """依 selected（子集合）把 tc 裡屬於 options 的每個選項的勾選狀態全部覆寫一次。"""
    selected = set(selected)
    unknown = selected - set(options)
    if unknown:
        raise ValueError(f'未知的選項: {unknown}')
    markers = find_checkbox_runs(tc, options)
    for option, run in markers.items():
        set_checkbox_marker(run, option in selected)


def count_pages(docx_path):
    """Render to PDF and count pages. Returns int, or None if no renderer is available."""
    soffice = next((c for c in SOFFICE_PY_CANDIDATES if c and os.path.exists(c)), None)
    if not soffice or not shutil.which('pdfinfo'):
        return None
    tmp = tempfile.mkdtemp(prefix='pagecheck_')
    try:
        src = os.path.join(tmp, 'form.docx')
        shutil.copy(docx_path, src)
        subprocess.run([sys.executable, soffice, '--headless', '--convert-to', 'pdf', '--outdir', tmp, src],
                       capture_output=True, timeout=180)
        pdf = os.path.join(tmp, 'form.pdf')
        if not os.path.exists(pdf):
            return None
        info = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
        m = re.search(r'Pages:\s+(\d+)', info)
        return int(m.group(1)) if m else None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ main entry point
def fill(template, out_path, *, applicant_name, emp_id, dept, phone, email,
          need, headcount, security_selected, benefit_selected, date):
    need_lines = paras_of(need)
    if not any(need_lines):
        raise SystemExit('ERROR: 需求說明是空的')
    headcount = ' '.join(headcount.split())
    if not headcount:
        raise SystemExit('ERROR: 預估使用人數是空的')
    for label, value in [('申請人姓名', applicant_name), ('員工編號', emp_id), ('單位', dept),
                          ('電話', phone), ('Email', email)]:
        if not value or not value.strip():
            raise SystemExit(f'ERROR: {label}是空的')

    warnings = []
    n = estimate_lines(need_lines, NEED_CHARS_PER_LINE)
    if estimate_lines([headcount], HEADCOUNT_CHARS_PER_LINE) > 1:
        warnings.append({
            'code': 'headcount_overflow',
            'message': f'預估使用人數「{headcount}」超過一行（約 {HEADCOUNT_CHARS_PER_LINE} 個全形字），該格列高固定，第二行會被截掉；請縮短。',
        })

    with zipfile.ZipFile(template) as zin:
        items = zin.infolist()
        blobs = {i.filename: zin.read(i.filename) for i in items}
    root = etree.fromstring(blobs['word/document.xml'])
    before = all_cell_texts(root)
    tbl = main_table(root)

    set_cell_paragraphs(cell_right_of(tbl, '申請人姓名員工編號'), [applicant_name.strip(), emp_id.strip()])
    set_cell_paragraphs(cell_right_of(tbl, '單位'), [dept.strip()])
    set_cell_paragraphs(cell_right_of(tbl, '電話'), [phone.strip()])
    set_cell_paragraphs(cell_right_of(tbl, 'E-Mail'), [email.strip()])
    set_cell_paragraphs(cell_right_of(tbl, '需求說明'), need_lines)
    set_checkboxes(cell_right_of(tbl, '安全要求'), SECURITY_OPTIONS, security_selected)
    set_checkboxes(cell_right_of(tbl, '效益評估'), BENEFIT_OPTIONS, benefit_selected)
    set_cell_paragraphs(cell_right_of(tbl, '預估使用人數'), [headcount])
    set_date(cell_right_of(tbl, '申請日期'), date)

    new_xml = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in items:
            data = new_xml if item.filename == 'word/document.xml' else blobs[item.filename]
            zout.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)

    verify(template, out_path, applicant_name, emp_id, dept, phone, email,
           need_lines, headcount, security_selected, benefit_selected, date, before)

    pages = count_pages(out_path)
    if pages is None:  # no renderer: fall back to the line estimate
        if n > NEED_MAX_LINES:
            warnings.append({
                'code': 'need_overflow',
                'message': f'需求說明約 {n} 行，超過安全範圍（約 {NEED_MAX_LINES} 行），表單可能被撐到第二頁；請精簡或改用附件。',
            })
    elif pages > 1:
        warnings.append({
            'code': 'need_overflow',
            'message': f'整份表單轉檔後是 {pages} 頁（需求說明約 {n} 行），超過 1 頁 A4；請精簡需求說明，或改寫成簡短說明並註明「詳如附件」。',
        })
    return warnings, pages


def verify(template, out_path, applicant_name, emp_id, dept, phone, email,
           need_lines, headcount, security_selected, benefit_selected, d, before_cells):
    """重新開啟成品，證明：該動的欄位/勾選內容正確，其餘 cell 一律不在「預期變動集合」外變動。"""
    with zipfile.ZipFile(out_path) as zo, zipfile.ZipFile(template) as zt:
        assert zo.testzip() is None, 'output zip is corrupt'
        for name in zt.namelist():
            if name != 'word/document.xml':
                assert zo.read(name) == zt.read(name), f'unexpected change in {name}'
        root = etree.fromstring(zo.read('word/document.xml'))
    after = all_cell_texts(root)
    tbl = main_table(root)

    assert cell_text(cell_right_of(tbl, '申請人姓名員工編號')) == f'{applicant_name.strip()}\n{emp_id.strip()}', '申請人姓名/員工編號 mismatch'
    assert cell_text(cell_right_of(tbl, '單位')) == dept.strip(), '單位 mismatch'
    assert cell_text(cell_right_of(tbl, '電話')) == phone.strip(), '電話 mismatch'
    assert cell_text(cell_right_of(tbl, 'E-Mail')) == email.strip(), 'E-Mail mismatch'
    assert cell_text(cell_right_of(tbl, '需求說明')) == '\n'.join(need_lines), '需求說明 mismatch'
    assert cell_text(cell_right_of(tbl, '預估使用人數')) == headcount, '預估使用人數 mismatch'
    assert cell_text(cell_right_of(tbl, '申請日期')) == roc_date_text(d), '申請日期 mismatch'

    # 逐一核對複選狀態：勾了的 cell 文字裡要有 ●，沒勾的選項周圍不該有 ●（用 marker 直接判讀最準）。
    for tc_label, options, selected in [
        ('安全要求', SECURITY_OPTIONS, security_selected),
        ('效益評估', BENEFIT_OPTIONS, benefit_selected),
    ]:
        markers = find_checkbox_runs(cell_right_of(tbl, tc_label), options)
        for option, run in markers.items():
            t = run.find(W + 't')
            expect_checked = option in selected
            actual_checked = (t.text == CHECKBOX_CHECKED_CHAR)
            assert actual_checked == expect_checked, f'{tc_label}「{option}」勾選狀態不符（預期 {expect_checked}）'

    # 找出「這個 cell 有變動」的座標，跟這次實際會寫入的欄位對應的座標集合比對，
    # 確保沒有意料之外的地方被動到（沿用原腳本 verify() 的紀律，只是從硬編碼上限
    # 改成明確列出這次要變動的欄位）。
    expected_changed_labels = {'申請人姓名員工編號', '單位', '電話', 'E-Mail', '需求說明',
                                '安全要求', '效益評估', '預估使用人數', '申請日期'}
    expected_changed_coords = set()
    for tr_i, tr in enumerate(tbl.findall('w:tr', NS)):
        tcs = tr.findall('w:tc', NS)
        for i, tc in enumerate(tcs[:-1]):
            label = ''.join(t.text or '' for t in tc.iter(W + 't')).replace(' ', '').replace('\n', '')
            if label in expected_changed_labels:
                expected_changed_coords.add((tr_i, i + 1))

    changed = {(r, c) for r, (ra, rb) in enumerate(zip(before_cells, after))
               for c, (a, b) in enumerate(zip(ra, rb)) if a != b}
    unexpected = changed - expected_changed_coords
    assert not unexpected, f'非預期變動的 cell 座標: {unexpected}'


def _cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--name', required=True, help='申請人姓名')
    ap.add_argument('--empid', required=True, help='員工編號')
    ap.add_argument('--dept', required=True, help='單位')
    ap.add_argument('--phone', required=True, help='電話')
    ap.add_argument('--email', required=True, help='E-Mail')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--need', help='需求說明 text (use --need-file for long / multi-line text)')
    src.add_argument('--need-file', help='UTF-8 text file containing 需求說明')
    ap.add_argument('--headcount', required=True, help='預估使用人數')
    ap.add_argument('--security', default=','.join(DEFAULT_SECURITY_SELECTED),
                     help=f'安全要求，逗號分隔，可選: {SECURITY_OPTIONS}')
    ap.add_argument('--benefit', default=','.join(DEFAULT_BENEFIT_SELECTED),
                     help=f'效益評估，逗號分隔，可選: {BENEFIT_OPTIONS}')
    ap.add_argument('--out', required=True, help='輸出 .docx 路徑')
    ap.add_argument('--template', default=DEFAULT_TEMPLATE)
    ap.add_argument('--date', help='YYYY-MM-DD override (testing only; default = today in Asia/Taipei)')
    a = ap.parse_args()

    need = a.need if a.need is not None else open(a.need_file, encoding='utf-8').read()
    d = datetime.date.fromisoformat(a.date) if a.date else datetime.datetime.now(ZoneInfo('Asia/Taipei')).date()
    security_selected = [s for s in a.security.split(',') if s]
    benefit_selected = [s for s in a.benefit.split(',') if s]

    warnings, pages = fill(
        a.template, a.out, applicant_name=a.name, emp_id=a.empid, dept=a.dept, phone=a.phone,
        email=a.email, need=need, headcount=a.headcount, security_selected=security_selected,
        benefit_selected=benefit_selected, date=d,
    )
    print(f'OK  {a.out}')
    print(f'    申請日期: {roc_date_text(d)}')
    if pages is None:
        print('    頁數檢查: 略過（找不到 LibreOffice / pdfinfo），僅以行數估計')
    else:
        print(f'    頁數檢查: {pages} 頁' + (' ✓' if pages == 1 else ''))
    for w in warnings:
        print('WARNING: ' + w['message'])


if __name__ == '__main__':
    sys.exit(_cli())
