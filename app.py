"""DC-4018 多人自助填寫系統 — Flask 入口。

M1：GET / 、GET /lookup/<emp_id> 骨架。
M2：完整表單頁面 + POST /submit（更新識別資料 → 產生 docx → 歸檔 → 回傳下載）。
"""
import json
import os
import re
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request, send_file

import db
import form_fill

app = Flask(__name__)

ARCHIVE_DIR = os.environ.get('ARCHIVE_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'archive'))
TAIPEI = ZoneInfo('Asia/Taipei')

REQUIRED_FIELDS = {
    'emp_id': '員工編號', 'name': '申請人姓名', 'dept': '單位', 'phone': '電話',
    'email': 'E-Mail', 'need': '需求說明', 'headcount': '預估使用人數',
}


def _today_roc():
    today = datetime.now(TAIPEI).date()
    return {'roc_year': today.year - 1911, 'month': today.month, 'day': today.day}


def _sanitize_filename_part(text):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', text).strip()
    return re.sub(r'\s+', '_', text) or 'unknown'


def _render_form(*, error=None, values=None, selected_security=None, selected_benefit=None, default_date=None):
    return render_template(
        'index.html',
        error=error,
        values=values or {},
        security_options=form_fill.SECURITY_OPTIONS,
        benefit_options=form_fill.BENEFIT_OPTIONS,
        selected_security=selected_security if selected_security is not None else form_fill.DEFAULT_SECURITY_SELECTED,
        selected_benefit=selected_benefit if selected_benefit is not None else form_fill.DEFAULT_BENEFIT_SELECTED,
        default_date=default_date or _today_roc(),
        need_max_lines=form_fill.NEED_MAX_LINES,
        headcount_chars_per_line=form_fill.HEADCOUNT_CHARS_PER_LINE,
    )


@app.get('/')
def index():
    return _render_form()


@app.get('/lookup/<emp_id>')
def lookup(emp_id):
    identity = db.get_identity(emp_id)
    if identity is None:
        return jsonify({'found': False})
    return jsonify({'found': True, **identity})


@app.post('/submit')
def submit():
    form = request.form
    values = {k: form.get(k, '').strip() for k in REQUIRED_FIELDS}
    security_selected = form.getlist('security')
    benefit_selected = form.getlist('benefit')

    missing = [label for key, label in REQUIRED_FIELDS.items() if not values[key]]
    if missing:
        return _render_form(
            error=f'請填寫：{"、".join(missing)}', values=values,
            selected_security=security_selected, selected_benefit=benefit_selected,
        ), 400

    try:
        roc_year = int(form.get('roc_year', ''))
        month = int(form.get('roc_month', ''))
        day = int(form.get('roc_day', ''))
        submit_date = date(roc_year + 1911, month, day)
    except (TypeError, ValueError):
        return _render_form(
            error='申請日期不是合法的日期，請檢查年/月/日。', values=values,
            selected_security=security_selected, selected_benefit=benefit_selected,
        ), 400

    db.upsert_identity(values['emp_id'], values['name'], values['dept'], values['phone'], values['email'])

    now = datetime.now(TAIPEI)
    day_dir = os.path.join(ARCHIVE_DIR, now.strftime('%Y-%m-%d'))
    os.makedirs(day_dir, exist_ok=True)
    # 時間戳(微秒)+短亂數：低頻使用場景下微秒級時間戳幾乎不會撞號，但真的巧合同時
    # 送出時光靠時間戳仍有理論上的碰撞風險，加 6 碼亂數尾綴徹底排除。
    serial = now.strftime('%H%M%S_%f') + '_' + uuid.uuid4().hex[:6]
    base_name = f"{serial}_{_sanitize_filename_part(values['emp_id'])}"
    docx_path = os.path.join(day_dir, base_name + '.docx')
    record_path = os.path.join(day_dir, base_name + '.json')

    try:
        warnings, pages = form_fill.fill(
            form_fill.DEFAULT_TEMPLATE, docx_path,
            applicant_name=values['name'], emp_id=values['emp_id'], dept=values['dept'],
            phone=values['phone'], email=values['email'], need=values['need'],
            headcount=values['headcount'], security_selected=security_selected,
            benefit_selected=benefit_selected, date=submit_date,
        )
    except SystemExit as e:
        return _render_form(
            error=str(e), values=values,
            selected_security=security_selected, selected_benefit=benefit_selected,
        ), 400

    # 需求說明把表單撐到第 2 頁時不自動出檔——沒有 Web 在場複核，讓填寫者自己（他才是
    # 需求說明的作者）先縮短再送出，而不是悄悄產出一份不合規的 2 頁檔案。
    # 預估使用人數超過一行只是截字警告，不影響頁數，允許照樣送出。
    if any(w['code'] == 'need_overflow' for w in warnings):
        os.remove(docx_path)
        blocking_message = next(w['message'] for w in warnings if w['code'] == 'need_overflow')
        return _render_form(
            error=f'{blocking_message}（識別資料已記住，修改「需求說明」後可直接重新送出）',
            values=values, selected_security=security_selected, selected_benefit=benefit_selected,
        ), 400

    record = {
        'submitted_at': now.isoformat(), **values,
        'security_selected': security_selected, 'benefit_selected': benefit_selected,
        'submit_date': submit_date.isoformat(), 'warnings': warnings, 'pages': pages,
    }
    with open(record_path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    download_name = f"DC-4018_系統開發維護需求單_v1_6_{_sanitize_filename_part(values['name'])}.docx"
    return send_file(docx_path, as_attachment=True, download_name=download_name)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
