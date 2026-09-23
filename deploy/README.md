# 內網部署

**這份文件是給 Web 或該內網機器的管理者照著做的操作步驟。Claude Code 沒有那台機器
的存取權，無法代為執行部署、防火牆/VLAN 設定——這些需要人親自登入該機器完成。**

適用範圍：規格書 v1.0「依賴與前置條件」列的兩項前置確認（機器可常駐執行 Python
服務、同仁電腦可連到該機器的內網位址與埠號）已經確認過，才進到這一步。

## 共通前置作業

1. 確認機器已裝 Python 3.11 以上、`git`。
2. 把 repo clone 到機器上一個固定路徑（下面範例用 `/opt/dc4018-form-service`，
   Windows 範例用 `C:\dc4018-form-service`）。
3. 建虛擬環境並安裝套件：
   ```bash
   cd /opt/dc4018-form-service
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
4. `cp .env.example .env`，依機器實際狀況調整 `PORT` / `ARCHIVE_DIR` / `DB_PATH`
   （三個都有預設值，不用每個都設，只有需要改到 repo 目錄以外的路徑時才需要）。
5. **強烈建議先確認 LibreOffice + `pdfinfo`（poppler-utils）在這台機器上能正常運作**
   （`soffice --version`、`pdfinfo --version`）。這兩個工具存在時，`form_fill.py`
   的頁數判斷會是真的轉檔結果；不存在時會自動 fallback 成行數估計（不會壞掉，但
   準確度較低——M3 開發時的沙盒環境就是碰到這個限制，見主 README「已知限制」）。

## Linux（systemd）

1. （建議）建立一個專用的低權限系統帳號跑這個服務，不要用管理者帳號：
   ```bash
   sudo useradd --system --home /opt/dc4018-form-service --shell /usr/sbin/nologin dc4018-form
   sudo chown -R dc4018-form:dc4018-form /opt/dc4018-form-service
   ```
2. 把 `deploy/dc4018-form.service` 裡的路徑改成實際部署路徑（如果沒有用
   `/opt/dc4018-form-service`），複製到系統目錄並啟用：
   ```bash
   sudo cp deploy/dc4018-form.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now dc4018-form
   sudo systemctl status dc4018-form   # 應該顯示 active (running)
   ```
3. 重開機測試：`sudo reboot` 後再用 `systemctl status dc4018-form` 確認開機後自動
   啟動（風險登錄「常駐機器重開機/當機後服務沒自動復原」的緩解就是這一步）。
4. 服務當掉時 `Restart=on-failure` 會自動重啟；`journalctl -u dc4018-form -f` 可
   看即時 log。

## Windows

RDP 連進去的內網機器常見是 Windows，這裡給兩種做法，依機器管理者熟悉程度選一種即可。

### 做法 A：工作排程器（不用額外裝工具，設定較陽春）

1. 建一個啟動批次檔 `start.bat`（放在 repo 目錄下）：
   ```bat
   cd /d C:\dc4018-form-service
   .venv\Scripts\python.exe wsgi.py
   ```
2. 開啟「工作排程器」→ 建立工作：
   - 觸發程序：「電腦啟動時」
   - 動作：啟動程式 `start.bat`
   - 內容一般設定：「不管使用者是否登入均執行」、「以最高權限執行」視需要勾選
   - **設定頁籤**：勾選「如果工作失敗，重新啟動間隔」（例如每 1 分鐘、最多重試
     999 次）——這一步對應「常駐機器當機後服務沒自動復原」的風險緩解，工作排程器
     預設不會自動重試，一定要手動勾選。
3. 手動執行一次這個工作，確認瀏覽器連得到 `http://<這台機器的內網IP>:5000/`。
4. 重開機測試，確認開機後不用人手動點開就能連上。

### 做法 B：裝成 Windows 服務（NSSM，更穩，多一個小工具）

用 [NSSM](https://nssm.cc/)（免安裝的小工具，內網如果不能直接下載，找 IT 內部軟體
庫或帶隨身碟過去）把 `wsgi.py` 註冊成正式的 Windows 服務，好處是有內建的當機自動
重啟機制，行為更接近 Linux 的 systemd：

```bat
nssm install DC4018Form "C:\dc4018-form-service\.venv\Scripts\python.exe" "C:\dc4018-form-service\wsgi.py"
nssm set DC4018Form AppDirectory "C:\dc4018-form-service"
nssm set DC4018Form AppExit Default Restart
nssm start DC4018Form
```

之後可以在「服務」管理主控台看到 `DC4018Form`，設定為「自動（延遲啟動）」即可開機
自動啟動；當掉時 NSSM 會自動重啟。

## 部署後驗收（對應規格書「成功指標」）

1. **Web 不在場測試**：請一位同仁（不是 Web）在 Web 不在辦公室時，直接用瀏覽器連
   `http://<內網IP>:<PORT>/` 填寫並送出一次，確認能拿到下載的 .docx。這是這個專案
   要解決的核心問題（單點依賴 Web 本人），一定要實測過才算完成。
2. **識別資料記住測試**：同一位同仁用同一個員工編號送第二次，確認姓名/單位/電話/
   Email 有自動帶出（不用重打），且修改後送出會覆蓋成新值（不是疊加出兩筆）。
3. 檢查 `archive/<日期>/` 底下確實各自產生獨立的 `.docx` + `.json`，Web 可以直接
   打開來看內容。
4. 重開機/模擬當機（例如手動 kill 掉服務行程）後，確認服務會自動復原，不用人到現場
   手動重開。
