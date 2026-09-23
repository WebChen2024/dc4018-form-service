# DC-4018 系統開發維護需求單 多人自助填寫系統

把原本只有 Web 能在本機用 CLI 產生 DC-4018 需求單的流程，改成同仁可在內網瀏覽器
各自填寫、送出後自動產生合規 docx 並留存紀錄的 Flask 服務。詳細背景、範疇與里程碑
規劃見開發計畫（另存，不在本 repo）。

## 目前進度：M2（表單前端 + 送出流程）完成

- `form_fill.py`：從既有 `shu-system-request-form` skill 的 `fill_form.py` 移植並擴充，
  除了原本的需求說明/預估使用人數/申請日期，新增「申請人姓名/員工編號/單位/電話/Email」
  動態欄位、「安全要求/效益評估」複選 checkbox 讀寫，版面規則（A4 單頁、需求說明列高、
  日期格式）完全沿用不變。回傳的 warnings 是 `{code, message}`，code 分
  `need_overflow`（需求說明撐爆頁面）／`headcount_overflow`（預估使用人數超過一行會被截字）。
- `db.py`：SQLite 識別資料存取層，以員工編號為 key，整筆覆寫（不留歷史）。
- `templates/index.html` + `static/form.{css,js}`：完整表單頁面，員工編號欄位 blur 時
  查 `/lookup` 自動帶入其餘識別欄位（可再手動覆寫），需求說明有即時行數提示。
- `app.py`：`GET /` 表單頁、`GET /lookup/<員工編號>`、`POST /submit`。`need_overflow`
  會擋下送出（回表單、保留已填資料、識別資料仍照常記住方便重送）；`headcount_overflow`
  不擋，照樣出檔並記在歸檔 json 供 Web 事後複核。送出成功即更新識別資料 → 產生 docx →
  存一份紀錄到 `archive/<日期>/<序號>.json`＋`.docx` → 回傳 docx 下載。
- 下一步 M3：超頁轉附件回歸測試矩陣、自動歸檔驗證。

## 本機測試

```bash
pip install -r requirements.txt
python3 -m pytest tests/ -q      # 單元測試
python3 app.py                   # 啟動開發伺服器，預設 :5000
```

手動測試 docx 產生邏輯（不透過網頁）：

```bash
python3 form_fill.py \
  --name "測試同仁" --empid T0001 --dept 總務處保管組 --phone 12345 --email test@mail.shu.edu.tw \
  --need "需求說明內容" --headcount 50人 \
  --security 需區隔使用者權限 --benefit 精進作業程序、強化行政效率 \
  --out /tmp/out.docx
```

## 已知限制

- 無登入機制，僅以「連得到內網」作為存取邊界（規格書 v1.0 定案的取捨，非遺漏）。
- `data/`、`archive/` 只存在部署機器本機，`.gitignore` 已排除，不進版本控制。
