"""
飛出台灣 — SEO 航線靜態頁產生器
================================
讀 deals.json，為每個目的地生成靜態頁（routes/tpe-xxx.html）、
航線總覽（routes/index.html）、sitemap.xml、robots.txt。
由 monitor.py 在每次更新資料後自動呼叫，也可單獨執行：python build_pages.py

目的：單頁 SPA Google 只收錄一頁；靜態航線頁吃「台北 東京 便宜機票」這類搜尋流量。
"""
import os
import sys
import json
import html
from datetime import datetime
from urllib.parse import quote

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://airplay-jet.vercel.app"
ROUTES_DIR = os.path.join(HERE, "routes")

REGION_NAMES = {
    "northeast_asia": "東北亞", "china": "中國大陸", "southeast_asia": "東南亞",
    "europe": "歐洲", "americas": "美洲", "oceania": "大洋洲", "other": "其他",
}

# 機場代碼 → 行程搜尋用城市名（同 index.html 的 CITY_QUERY）
CITY_QUERY = {
    "NRT": "東京", "HND": "東京", "KIX": "大阪", "ICN": "首爾", "GMP": "首爾",
    "BKK": "曼谷", "DMK": "曼谷", "PVG": "上海", "SHA": "上海",
    "PEK": "北京", "PKX": "北京", "CTS": "札幌", "SWA": "潮汕", "SGN": "胡志明市",
}

CSS = """
:root{color-scheme:dark}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans TC',-apple-system,sans-serif;background:#0B1426;color:#e8eaed;line-height:1.7}
a{color:#60a5fa;text-decoration:none}
.wrap{max-width:860px;margin:0 auto;padding:2rem 1.25rem 4rem}
.crumb{font-size:.8rem;color:#8b95a7;margin-bottom:1.5rem}
h1{font-size:1.6rem;margin-bottom:.5rem}
.sub{color:#8b95a7;font-size:.9rem;margin-bottom:1.5rem}
.hero-price{font-size:2.4rem;font-weight:900;color:#ff8c42;margin:.25rem 0}
table{width:100%;border-collapse:collapse;margin:1.25rem 0;font-size:.9rem}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid rgba(255,255,255,.08)}
th{color:#8b95a7;font-weight:600;font-size:.8rem}
.tag{font-size:.7rem;padding:2px 8px;border-radius:100px;background:rgba(255,255,255,.08)}
.btn{display:inline-block;padding:8px 16px;border-radius:8px;font-size:.85rem;font-weight:700;background:#2563eb;color:#fff}
.btn.alt{background:rgba(255,92,40,.15);border:1px solid rgba(255,92,40,.4)}
.note{font-size:.78rem;color:#8b95a7;background:rgba(255,255,255,.04);border-radius:10px;padding:.8rem 1rem;margin:1.5rem 0}
.chart-box{margin:1.5rem 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:.75rem;margin:1rem 0 2rem}
.grid a{display:block;padding:.8rem 1rem;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:10px;color:#e8eaed;font-size:.88rem}
.grid a span{color:#ff8c42;font-weight:800}
h2{font-size:1.1rem;margin:2rem 0 .5rem}
footer{margin-top:3rem;padding-top:1.25rem;border-top:1px solid rgba(255,255,255,.08);font-size:.75rem;color:#5b6575}
"""

CHART_JS = """
// 從 route_history.csv 取本航線歷史最低價，畫成 SVG 走勢圖（資料不足就不顯示）
fetch('../route_history.csv?'+Date.now()).then(r=>r.ok?r.text():'').then(txt=>{
  if(!txt) return
  const dest = document.body.dataset.dest
  const pts = txt.trim().split('\\n').slice(1).map(l=>l.split(','))
    .filter(c=>c[2]===dest).map(c=>({t:c[0], p:+c[3]})).filter(x=>x.p>0)
  // 同一天多筆取最低
  const byDay = {}
  pts.forEach(x=>{const d=x.t.slice(0,10); if(!(d in byDay)||x.p<byDay[d]) byDay[d]=x.p})
  const days = Object.keys(byDay).sort()
  if(days.length < 2) return
  const vals = days.map(d=>byDay[d])
  const W=760,H=180,P=36
  const mn=Math.min(...vals), mx=Math.max(...vals), span=(mx-mn)||1
  const X=i=>P+(W-2*P)*i/(days.length-1), Y=v=>H-P-(H-2*P)*(v-mn)/span
  const path = vals.map((v,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')
  const dots = vals.map((v,i)=>`<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="3.5" fill="#ff8c42"/>`).join('')
  const labels = days.map((d,i)=>`<text x="${X(i).toFixed(1)}" y="${H-10}" font-size="10" fill="#8b95a7" text-anchor="middle">${d.slice(5)}</text>`).join('')
  document.getElementById('chart').innerHTML =
    `<h2>📈 歷史最低價走勢</h2><svg viewBox="0 0 ${W} ${H}" style="width:100%;background:rgba(255,255,255,.03);border-radius:12px">
     <text x="${P}" y="18" font-size="11" fill="#8b95a7">最低 $${mn.toLocaleString()} / 最高 $${mx.toLocaleString()}</text>
     <path d="${path}" fill="none" stroke="#ff8c42" stroke-width="2.5"/>${dots}${labels}</svg>`
})
"""


def esc(s):
    return html.escape(str(s), quote=True)


def city_of(iata, dest_name):
    return CITY_QUERY.get(iata, dest_name)


def fmt_dt(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso or ""


def page_shell(title, desc, canonical, body, dest=""):
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="飛出台灣">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body{f' data-dest="{dest}"' if dest else ''}>
<div class="wrap">
{body}
<footer>票價為自動抓取之參考價（標示「即時票價」者來自 Travelpayouts API；「行情參考價」為市場常見促銷行情），實際金額以航空公司官網為準。部分連結為聯盟連結，透過連結訂購本站可能獲得佣金，不影響你的價格。<br>© 飛出台灣 airplay-jet.vercel.app</footer>
</div>
</body>
</html>"""


def build_route_page(iata, deals, updated):
    deals = sorted(deals, key=lambda d: d["price"])
    cheapest = deals[0]
    dest_name = cheapest.get("destination_name", iata)
    city = city_of(iata, dest_name)
    slug = f"tpe-{iata.lower()}"
    canonical = f"{SITE_URL}/routes/{slug}.html"
    title = f"台北飛{dest_name}最低價 ${cheapest['price']:,} 起（{datetime.now():%Y年%m月}）｜飛出台灣"
    desc = (f"台北 (TPE) 飛 {dest_name} ({iata}) 機票最低 NT${cheapest['price']:,} 起，"
            f"含稅來回估算 NT${cheapest.get('price_with_tax', 0):,}。"
            f"比較 {len(deals)} 家航空促銷價，直達官方訂票頁。")

    rows = []
    for d in deals:
        src = "✅ 即時票價" if d.get("source") == "live" else "📊 行情參考價"
        lcc = "廉航" if d.get("is_lcc") else "傳統"
        rows.append(
            f"<tr><td>{esc(d['airline'])} <span class='tag'>{lcc}</span></td>"
            f"<td><strong style='color:#ff8c42'>${d['price']:,}</strong> 起</td>"
            f"<td>${d.get('price_with_tax', 0):,}</td>"
            f"<td>{src}</td>"
            f"<td><a class='btn' href='{esc(d['booking_url'])}' target='_blank' rel='noopener nofollow'>查票價 ↗</a></td></tr>")

    q = quote(city)
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "飛出台灣", "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": "所有航線", "item": f"{SITE_URL}/routes/"},
            {"@type": "ListItem", "position": 3, "name": f"台北→{dest_name}", "item": canonical},
        ],
    }, ensure_ascii=False)

    body = f"""<nav class="crumb"><a href="{SITE_URL}/">飛出台灣</a> › <a href="./">所有航線</a> › 台北→{esc(dest_name)}</nav>
<h1>台北 → {esc(dest_name)} 便宜機票</h1>
<p class="sub">TPE → {iata}　·　資料更新：{fmt_dt(updated)}</p>
<div class="hero-price">${cheapest['price']:,} <span style="font-size:1rem;color:#8b95a7">TWD 起（單程未稅）</span></div>
<p class="sub">最低價航空：{esc(cheapest['airline'])}　·　含稅來回估算約 ${cheapest.get('price_with_tax', 0):,}</p>
<h2>各航空最低價比較</h2>
<table>
<tr><th>航空公司</th><th>單程票價</th><th>含稅來回估算</th><th>資料來源</th><th></th></tr>
{''.join(rows)}
</table>
<div id="chart" class="chart-box"></div>
<h2>到了{esc(city)}玩什麼</h2>
<p style="margin:.5rem 0 1rem">
<a class="btn alt" href="https://www.klook.com/zh-TW/search/result/?query={q}" target="_blank" rel="noopener nofollow">🎡 {esc(city)}行程・門票（Klook）</a>
<a class="btn alt" href="https://www.kkday.com/zh-tw/product/productlist?keyword={q}" target="_blank" rel="noopener nofollow">🎟 {esc(city)}玩樂（KKday）</a>
</p>
<div class="note">💡 票價隨艙位即時變動，看到低價建議直接到官網確認。本頁每日台北時間 08:00 / 20:00 自動更新。</div>
<script type="application/ld+json">{jsonld}</script>
<script>{CHART_JS}</script>"""
    return slug, page_shell(title, desc, canonical, body, dest=iata)


def build_index_page(by_dest, updated):
    canonical = f"{SITE_URL}/routes/"
    title = "台北出發全航線最低價總覽｜飛出台灣"
    desc = f"台北 (TPE) 出發 {len(by_dest)} 個目的地的最低機票價格總覽，每日自動更新，直達官方訂票。"

    by_region = {}
    for iata, deals in by_dest.items():
        cheapest = min(deals, key=lambda d: d["price"])
        by_region.setdefault(cheapest.get("region", "other"), []).append((iata, cheapest))

    sections = []
    order = ["northeast_asia", "china", "southeast_asia", "europe", "americas", "oceania", "other"]
    for region in order:
        items = by_region.get(region)
        if not items:
            continue
        items.sort(key=lambda x: x[1]["price"])
        links = "".join(
            f"<a href='tpe-{iata.lower()}.html'>台北 → {esc(c.get('destination_name', iata))}"
            f"<br><span>${c['price']:,}</span> 起</a>"
            for iata, c in items)
        sections.append(f"<h2>{REGION_NAMES.get(region, region)}</h2><div class='grid'>{links}</div>")

    body = f"""<nav class="crumb"><a href="{SITE_URL}/">飛出台灣</a> › 所有航線</nav>
<h1>台北出發 全航線最低價</h1>
<p class="sub">共 {len(by_dest)} 個目的地　·　資料更新：{fmt_dt(updated)}</p>
{''.join(sections)}"""
    return page_shell(title, desc, canonical, body)


def build(deals=None, stats=None):
    if deals is None:
        with open(os.path.join(HERE, "deals.json"), encoding="utf-8") as f:
            data = json.load(f)
        deals, stats = data["deals"], data["stats"]
    updated = (stats or {}).get("last_updated", datetime.now().isoformat())

    by_dest = {}
    for d in deals:
        by_dest.setdefault(d["destination"], []).append(d)

    os.makedirs(ROUTES_DIR, exist_ok=True)
    slugs = []
    for iata, ds in by_dest.items():
        slug, html_text = build_route_page(iata, ds, updated)
        with open(os.path.join(ROUTES_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(html_text)
        slugs.append(slug)

    with open(os.path.join(ROUTES_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index_page(by_dest, updated))

    today = datetime.now().strftime("%Y-%m-%d")
    urls = [f"{SITE_URL}/", f"{SITE_URL}/routes/"] + [f"{SITE_URL}/routes/{s}.html" for s in sorted(slugs)]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls]
    sitemap.append("</urlset>")
    with open(os.path.join(HERE, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap))

    with open(os.path.join(HERE, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")

    print(f"[pages] 已生成 {len(slugs)} 個航線頁 + 總覽 + sitemap.xml + robots.txt")
    return len(slugs)


if __name__ == "__main__":
    build()
