"""
飛出台灣 — 最低價監控（排程入口）
==================================
每次執行：跑爬蟲 → 比對最低價變動 → 寫報告 → 跳 Windows 桌面通知。
由 Windows 工作排程器每天 08:00、20:00 透過 run_monitor.bat 呼叫，
或由 GitHub Actions 在 Linux runner 上呼叫（會自動略過桌面通知）。

產出（都在本資料夾）：
  price_report.txt   ← 人看的最新報告
  price_history.csv  ← 每次最低價的歷史紀錄（可用 Excel 開）
  .last_cheapest.json← 上次快照（用來比對變動，勿手動刪）
"""
import os
import sys
import csv
import json
import subprocess
from datetime import datetime

# Windows 排程的主控台是 cp950，印 emoji 會 UnicodeEncodeError 直接崩潰
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, ".last_cheapest.json")
REPORT = os.path.join(HERE, "price_report.txt")
HISTORY = os.path.join(HERE, "price_history.csv")
ROUTE_HISTORY = os.path.join(HERE, "route_history.csv")


def fmt(n):
    return f"${n:,}"


def load_prev():
    if os.path.exists(SNAP):
        try:
            return json.load(open(SNAP, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def notify(title, msg):
    """Windows 桌面氣球通知（用內建 PowerShell，免裝額外套件）。
    非 Windows 環境（如 GitHub Actions 的 Linux runner）自動略過。"""
    if os.name != "nt":
        print("[通知略過] 非 Windows 環境，不發桌面通知")
        return
    safe_title = title.replace("'", " ")
    safe_msg = msg.replace("'", " ")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        f"$n.BalloonTipTitle='{safe_title}';"
        f"$n.BalloonTipText='{safe_msg}';"
        "$n.Visible=$true;$n.ShowBalloonTip(10000);"
        "Start-Sleep -Seconds 6;$n.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=25,
        )
    except Exception as e:
        print(f"[通知略過] {e}")


def main():
    from scraper import run_all  # 跑爬蟲、寫 deals.json、回傳清單

    deals = run_all()
    if not deals:
        print("[monitor] 無資料，結束")
        return

    deals = sorted(deals, key=lambda d: d["price"])
    cheapest = deals[0]
    now = datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")

    prev = load_prev()
    prev_overall = prev.get("overall")
    prev_routes = prev.get("routes", {})

    if prev_overall is None:
        delta = None
        change_line = "（首次執行，建立比價基準）"
    else:
        delta = cheapest["price"] - prev_overall
        if delta < 0:
            change_line = f"↓ 比上次便宜 {fmt(-delta)}"
        elif delta > 0:
            change_line = f"↑ 比上次貴 {fmt(delta)}"
        else:
            change_line = "→ 與上次持平"

    cur_routes, drops = {}, []
    for d in deals:
        k = f"{d['airline_code']}|{d['destination']}"
        cur_routes[k] = d["price"]
        old = prev_routes.get(k)
        if old is not None and d["price"] < old:
            drops.append((d, old - d["price"]))
    drops.sort(key=lambda x: -x[1])

    L = ["=" * 50,
         f"飛出台灣 · 最低價報告   {ts}",
         "=" * 50,
         f"🏆 全站最低：{cheapest['airline']} 台北→{cheapest['destination_name']}"
         f"   {fmt(cheapest['price'])} TWD",
         f"   {change_line}",
         "",
         "💰 最便宜 Top 5："]
    for i, d in enumerate(deals[:5], 1):
        tag = "廉航" if d["is_lcc"] else "傳統"
        L.append(f"   {i}. {d['airline']}({tag}) 台北→{d['destination_name']}"
                 f"   {fmt(d['price'])}")
    if drops:
        L += ["", "📉 較上次降價的航線："]
        for d, amt in drops[:8]:
            L.append(f"   • {d['airline']} 台北→{d['destination_name']}"
                     f"   {fmt(d['price'])}  (↓{fmt(amt)})")
    L += ["", f"資料筆數：{len(deals)} 筆   報告檔：price_report.txt", ""]
    report = "\n".join(L)
    open(REPORT, "w", encoding="utf-8").write(report)
    print(report)

    new_file = not os.path.exists(HISTORY)
    with open(HISTORY, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["時間", "最低價航空", "目的地", "最低價TWD", "較上次變動TWD"])
        w.writerow([ts, cheapest["airline"], cheapest["destination_name"],
                    cheapest["price"], "" if delta is None else delta])

    json.dump({"overall": cheapest["price"], "routes": cur_routes,
               "updated": now.isoformat()},
              open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 每條航線的歷史價（給航線頁走勢圖用；欄位順序勿改：時間,航空,目的地,價格）
    rh_new = not os.path.exists(ROUTE_HISTORY)
    with open(ROUTE_HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if rh_new:
            w.writerow(["時間", "airline_code", "destination", "price"])
        for d in deals:
            w.writerow([ts, d["airline_code"], d["destination"], d["price"]])

    # 重建 SEO 航線頁（失敗不影響監控主流程）
    try:
        import build_pages
        n = build_pages.build()
        print(f"[monitor] 航線頁已更新：{n} 頁")
    except Exception as e:
        print(f"[monitor] 航線頁建置失敗（不影響報告）：{e}")

    notify("飛出台灣 最低價",
           f"台北→{cheapest['destination_name']} {fmt(cheapest['price'])}  {change_line}")


if __name__ == "__main__":
    main()
