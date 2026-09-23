# DC-4018 系統開發維護需求單 多人自助填寫系統

把原本只有 Web 能在本機用 CLI 產生 DC-4018 需求單的流程，改成同仁可在內網瀏覽器
各自填寫、送出後自動產生合規 docx 並留存紀錄的 Flask 服務。詳細背景、範疇與里程碑
規劃見開發計畫（另存，不在本 repo）。

## 目前進度：M3（回歸測試矩陣）完成

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
- `tests/test_form_fill.py`：需求說明 7/8 行不警告、9 行才警告（NEED_MAX_LINES=8 邊界）、
  預估使用人數超過一行的截字警告不擋出檔、安全要求/效益評估全選/全不選/非預設組合各自
  獨立重新開檔驗證勾選符號正確（不透過 production 內部同一套邏輯，避免測試跟被測程式
  共用 bug 看不出來）、連續兩次針對同一個檔案換不同勾選組合確認「取消勾選」真的會換回
  方框不會殘留。
- `tests/test_app.py`：同一員工編號第二次送出覆寫（不是累積歷史）、必填欄位缺漏擋下且
  不留識別資料、需求說明超頁擋下且不留歸檔檔案但識別資料仍照常記住、同一天兩筆送出各自
  產生獨立的 docx+json（檔名加了微秒時間戳+短亂數，理論上不會撞號）、歸檔 json 內容跟
  送出資料一致、日期不合法擋下。
- **已知限制**：這個開發環境的 LibreOffice 沙盒化 headless 轉檔會直接失敗（連原始未
  修改的 template.docx 都無法轉檔成功，`pdfinfo` 也沒裝上），所以沒辦法在這裡實測「用
  LibreOffice 轉 PDF 驗證真的是 1 頁/2 頁」，`form_fill.count_pages()` 全程都是走行數
  估計的 fallback 路徑（跟原本單人版 skill 在同類沙盒環境下的行為一致，不是這次新增的
  缺口）。**部署到內網機器時，建議確認該機器上 LibreOffice + poppler-utils(`pdfinfo`)
  可以正常運作**，這樣執行期的頁數判斷才會是真的轉檔結果，而不是行數估計。
- 下一步 M4：內網部署（開機自動啟動、systemd unit 範例）。

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
