"""識別資料（申請人姓名/單位/電話/Email）的 SQLite 存取層。

以員工編號為 key，只保留「最後一次」的值——同一員工編號再次送單時整筆覆寫，
不保留歷史（規格書 v1.0：「依員工編號記住識別資料...下次同一員工編號填寫時
自動帶入、可覆寫更新」）。
"""
import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'identities.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (
    emp_id     TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    dept       TEXT NOT NULL,
    phone      TEXT NOT NULL,
    email      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def get_connection(db_path=None):
    db_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def get_identity(emp_id, db_path=None):
    """回傳 {'name', 'dept', 'phone', 'email'}，查無資料回傳 None。"""
    emp_id = emp_id.strip()
    if not emp_id:
        return None
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT name, dept, phone, email FROM identities WHERE emp_id = ?', (emp_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_identity(emp_id, name, dept, phone, email, db_path=None):
    """整筆覆寫（不留歷史）。emp_id 為空時直接略過，不寫入。"""
    emp_id = emp_id.strip()
    if not emp_id:
        return
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO identities (emp_id, name, dept, phone, email, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(emp_id) DO UPDATE SET
                name=excluded.name, dept=excluded.dept, phone=excluded.phone,
                email=excluded.email, updated_at=excluded.updated_at
            """,
            (emp_id, name, dept, phone, email, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
