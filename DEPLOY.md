# 飛出台灣 — 上線部署說明

架構：**Vercel**（放靜態網站）+ **GitHub Actions**（每天自動跑爬蟲、更新資料）。
全程免費、有公開網址、不需要自己的伺服器。

> 運作方式：GitHub Actions 跑爬蟲 → 把更新後的 `deals.json` commit 回 GitHub repo
> → Vercel 連到這個 repo，一偵測到新 commit 就自動重新部署 → 網站更新。

---

## 一次性設定（只做一次）

### 1. 建 GitHub repo 並上傳檔案

在這個資料夾（airplay）開終端機，執行：

```bash
git init
git add .
git commit -m "init: 飛出台灣機票最低價網站"
git branch -M main
# 把下面網址換成你自己建的 repo
git remote add origin https://github.com/<你的帳號>/<repo名稱>.git
git push -u origin main
```

> 還沒有 repo？先到 github.com 按 New repository 建一個空的（不要勾 Add README），再執行上面的指令。

### 2. 把 repo 連到 Vercel（發布網站）

1. 到 [vercel.com](https://vercel.com)，用 GitHub 帳號登入。
2. 點 **Add New… → Project**。
3. 在清單裡選你剛剛 push 的 repo，按 **Import**。
4. 設定畫面**全部保持預設**（Framework Preset 會顯示 *Other*，不需要 Build Command、不需要改 Output Directory）→ 按 **Deploy**。
5. 一兩分鐘後就會給你公開網址，例如 `https://<repo名稱>.vercel.app`。

之後每次 GitHub repo 有新 commit（包含 Actions 自動更新資料），Vercel 都會自動重新部署，你不用再做任何事。

> 不想用網頁、想用指令？也可以：
> ```bash
> npm i -g vercel
> vercel          # 第一次會要你登入並回答幾個問題
> vercel --prod   # 正式發布
> ```
> 但要讓「資料自動更新→網站自動更新」生效，仍建議用上面的 Git 連接方式（步驟 1–4）。

### 3. 確認 Actions 有寫入權限

repo → **Settings → Actions → General → Workflow permissions**：
選 **Read and write permissions** → Save。
（這樣排程跑完才能把更新後的 `deals.json` 推回 repo。）

---

## 自動更新怎麼運作

`.github/workflows/scrape.yml` 已經設好：

- **每天台北時間 08:00 與 20:00** 自動執行（UTC 00:00 / 12:00）
- 在 GitHub 的 Linux 機器上裝 Playwright、跑 `monitor.py`
- 抓到的資料 commit 回 repo → Vercel 自動重新部署 → 網站更新

**想立刻手動跑一次**：repo → **Actions → Scrape flight deals → Run workflow**。

---

## 重要：第一次跑完一定要看 log（調整選擇器）

爬蟲對各航空官網的「選擇器」目前是預設值，**很可能需要依實際頁面微調**。

第一次手動跑後：repo → **Actions** → 點進那次執行 → 看 `Run scraper + build report` 的輸出：

- 如果每家都顯示「即時 0 筆不足，補 fallback」→ 代表選擇器沒抓到，網站顯示的是**行情參考價**，不是即時價。
- 要抓到即時價，需要打開 `scraper.py` 裡每家航空的 `card_selectors`，對照官網實際的 HTML 結構修改。

> 想在自己電腦先除錯：
> ```bash
> pip install playwright beautifulsoup4
> python -m playwright install chromium
> python scraper.py
> ```
> 然後看終端機輸出與產生的 `deals.json`。

---

## 法務提醒

多數航空公司的服務條款（ToS）禁止自動爬取與公開轉載票價。你要把網站**公開上線**，建議先確認各航空的條款，或考慮改用合法的機票比價 API（Amadeus、Kiwi 等）。網站上已標示「票價為市場行情參考，以官網實際顯示為準」，但公開散布仍有風險，請自行評估。

---

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `index.html` | 網站本體（會自動讀 `deals.json` 與 `price_report.txt`） |
| `scraper.py` | 爬蟲：抓各航空促銷 → 寫 `deals.json` |
| `monitor.py` | 跑爬蟲 + 比對最低價變動 + 產生快報 |
| `deals.json` | 機票資料（網站讀這個） |
| `price_report.txt` | 首頁「最低價快報」顯示的內容 |
| `price_history.csv` | 每次最低價的歷史紀錄 |
| `.github/workflows/scrape.yml` | GitHub Actions 自動排程設定 |
| `setup_schedule.ps1` / `run_monitor.bat` | （選用）改在自己 Windows 電腦排程，非上線必要 |
