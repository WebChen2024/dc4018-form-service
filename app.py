"""DC-4018 多人自助填寫系統 — Flask 入口（M1：骨架）。

M1 範圍：GET / 陽春頁面、GET /lookup/<emp_id> 查識別資料 JSON。完整表單前端與
POST /submit（送出→產生 docx→歸檔）留給 M2，避免這個里程碑的驗收範圍跟下一個
里程碑混在一起。
"""
import os

from flask import Flask, jsonify

import db

app = Flask(__name__)


@app.get('/')
def index():
    return (
        '<h1>DC-4018 系統開發維護需求單</h1>'
        '<p>M1 骨架：完整表單頁面在 M2 才會加上。</p>'
        '<p>可先測試 <code>GET /lookup/&lt;員工編號&gt;</code> 確認 SQLite 讀寫正常。</p>'
    )


@app.get('/lookup/<emp_id>')
def lookup(emp_id):
    identity = db.get_identity(emp_id)
    if identity is None:
        return jsonify({'found': False})
    return jsonify({'found': True, **identity})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
