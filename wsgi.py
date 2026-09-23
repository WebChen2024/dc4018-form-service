"""生產環境啟動入口。

`python3 app.py` 用的是 Flask 內建開發伺服器，官方文件明確不建議拿來長時間對外
服務。這支改用 waitress（純 Python、Windows/Linux 都能跑，不需要另外裝 C 編譯
工具鏈），供部署腳本/服務設定檔呼叫。
"""
import os

from waitress import serve

from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    serve(app, host='0.0.0.0', port=port)
