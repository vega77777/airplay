"""
飛出台灣 — 多航空公司促銷爬蟲（Playwright 版）
================================================
用「真實瀏覽器」渲染各航空官網促銷頁，抓取最低促銷票價，輸出 deals.json。
支援：虎航、長榮、華航、星宇、樂桃、酷航、亞航、捷星（+ 中國大陸重點航線）

為什麼需要 Playwright？
  這些航空官網的促銷頁全是 JavaScript 動態渲染，用 requests/BeautifulSoup
  靜態抓取只會拿到空殼。Playwright 會啟動真瀏覽器、等頁面跑完 JS 再讀內容。

連線失敗或抓不到時，會自動退回「已知促銷行情」(fallback)，確保 deals.json
永遠有資料、前端不會空白。fallback 的票價為市場參考價，非即時。

用法（請在你自己的電腦執行）：
    pip install playwright beautifulsoup4 lxml
    playwright install chromium
    python scraper.py

注意：本程式抓取的選擇器（CSS selector）以通用策略為主。第一次跑完後，
若某家航空抓到 0 筆（會退回 fallback），可依該航空官網實際 DOM 微調
AIRLINES 設定裡的 `card_selectors`。
"""

import os
import re
import sys
import json
import time
import random
from datetime import datetime

# Windows 排程的主控台是 cp950，印 emoji 會 UnicodeEncodeError 直接崩潰
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Playwright 為選用相依：環境若沒裝，全程以 fallback 運作（不會崩潰）
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# 輸出到本腳本所在資料夾（修正：原本寫死成失效的舊 session 路徑）
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deals.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ── 目的地 → 地區 / IATA → 中文名 ─────────────────────────────
DEST_REGION_MAP = {
    "東京": "northeast_asia", "大阪": "northeast_asia", "名古屋": "northeast_asia",
    "福岡": "northeast_asia", "北海道": "northeast_asia", "沖繩": "northeast_asia",
    "札幌": "northeast_asia", "仙台": "northeast_asia", "首爾": "northeast_asia",
    "釜山": "northeast_asia", "成田": "northeast_asia", "羽田": "northeast_asia",
    "上海": "china", "北京": "china", "廣州": "china", "成都": "china",
    "深圳": "china", "杭州": "china", "西安": "china", "重慶": "china",
    "廈門": "china", "昆明": "china", "青島": "china", "武漢": "china",
    "曼谷": "southeast_asia", "清邁": "southeast_asia", "普吉": "southeast_asia",
    "新加坡": "southeast_asia", "吉隆坡": "southeast_asia", "峇里島": "southeast_asia",
    "馬尼拉": "southeast_asia", "胡志明": "southeast_asia", "河內": "southeast_asia",
    "峴港": "southeast_asia", "雅加達": "southeast_asia",
    "倫敦": "europe", "巴黎": "europe", "阿姆斯特丹": "europe", "法蘭克福": "europe",
    "維也納": "europe", "布拉格": "europe", "羅馬": "europe", "巴塞隆納": "europe",
    "洛杉磯": "americas", "舊金山": "americas", "紐約": "americas",
    "溫哥華": "americas", "多倫多": "americas",
    "雪梨": "oceania", "墨爾本": "oceania", "澳洲": "oceania",
    # ── 更多目的地地區對應 ──
    "鹿兒島": "northeast_asia", "廣島": "northeast_asia", "岡山": "northeast_asia",
    "高松": "northeast_asia", "熊本": "northeast_asia", "小松": "northeast_asia",
    "富山": "northeast_asia", "佐賀": "northeast_asia", "濟州": "northeast_asia",
    "大邱": "northeast_asia",
    "南京": "china", "天津": "china", "長沙": "china", "三亞": "china",
    "海口": "china", "福州": "china", "寧波": "china", "大連": "china",
    "瀋陽": "china", "哈爾濱": "china", "鄭州": "china", "桂林": "china", "潮汕": "china",
    "暹粒": "southeast_asia", "金邊": "southeast_asia", "仰光": "southeast_asia",
    "芽莊": "southeast_asia", "富國島": "southeast_asia", "蘇梅島": "southeast_asia",
    "宿霧": "southeast_asia", "喀比": "southeast_asia",
}

IATA_NAMES = {
    "TPE": "台北", "KHH": "高雄", "RMQ": "台中",
    "NRT": "東京成田", "HND": "東京羽田", "KIX": "大阪關西", "FUK": "福岡",
    "OKA": "沖繩", "CTS": "札幌", "NGO": "名古屋",
    "ICN": "首爾仁川", "GMP": "首爾金浦", "PUS": "釜山",
    "PVG": "上海浦東", "SHA": "上海虹橋", "PEK": "北京", "PKX": "北京大興",
    "CAN": "廣州", "CTU": "成都", "WUH": "武漢", "XMN": "廈門",
    "HGH": "杭州", "SZX": "深圳", "CKG": "重慶",
    "BKK": "曼谷素萬那普", "DMK": "曼谷廊曼", "HKT": "普吉",
    "SIN": "新加坡", "KUL": "吉隆坡", "DPS": "峇里島",
    "MNL": "馬尼拉", "SGN": "胡志明市", "HAN": "河內", "DAD": "峴港", "CGK": "雅加達",
    "LHR": "倫敦", "CDG": "巴黎", "AMS": "阿姆斯特丹", "FRA": "法蘭克福", "VIE": "維也納",
    "LAX": "洛杉磯", "SFO": "舊金山", "JFK": "紐約", "YVR": "溫哥華", "YYZ": "多倫多",
    "SYD": "雪梨", "MEL": "墨爾本",
    # ── 更多目的地（API 回傳這些代碼時可顯示中文名）──
    "KOJ": "鹿兒島", "HIJ": "廣島", "OKJ": "岡山", "TAK": "高松", "KMJ": "熊本",
    "SDJ": "仙台", "KMQ": "小松", "TOY": "富山", "HSG": "佐賀",
    "CJU": "濟州", "TAE": "大邱",
    "NKG": "南京", "TSN": "天津", "KMG": "昆明", "TAO": "青島", "CSX": "長沙",
    "SYX": "三亞", "HAK": "海口", "FOC": "福州", "NGB": "寧波", "DLC": "大連",
    "SHE": "瀋陽", "HRB": "哈爾濱", "CGO": "鄭州", "KWL": "桂林", "SWA": "揭陽潮汕",
    "REP": "暹粒", "PNH": "金邊", "RGN": "仰光", "CXR": "芽莊", "PQC": "富國島",
    "USM": "蘇梅島", "CEB": "宿霧", "KBV": "喀比", "HKG": "香港", "MFM": "澳門",
}

# 名稱 → IATA（反查，用於從頁面文字辨識目的地）
NAME_TO_IATA = {v: k for k, v in IATA_NAMES.items()}


def get_region(text):
    text = str(text)
    for kw, region in DEST_REGION_MAP.items():
        if kw in text:
            return region
    return "other"


def clean_price(text):
    """從字串抽取最低有效票價（>100，避免抓到折扣%或年份）"""
    if not text:
        return None
    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", str(text))]
    nums = [n for n in nums if 100 < n < 200000]
    return min(nums) if nums else None


def match_destination(text):
    """從一段文字找出目的地 IATA + 中文名（找不到回 None）"""
    for name, iata in NAME_TO_IATA.items():
        if name in text and iata not in ("TPE", "KHH", "RMQ"):
            return iata, name
    return None, None


# ── 各航空設定（促銷頁網址、訂票連結、卡片選擇器、fallback 行情）──
AIRLINES = [
    {
        "airline": "台灣虎航", "code": "IT", "is_lcc": True,
        "promo_url": "https://www.tigerairtw.com/zh-tw/event",
        "booking_url": "https://booking.tigerairtw.com/",
        "card_selectors": [".promotion-card", "[class*='promo']", "[class*='deal']", "article", ".card"],
        "fallback": [
            ("KIX", 1499, 64), ("NRT", 1799, 58), ("OKA", 1299, 55), ("FUK", 1599, 52),
            ("CTS", 2299, 45), ("ICN", 1699, 48), ("PUS", 1499, 51), ("BKK", 1999, 42),
            ("SIN", 2299, 38), ("DMK", 1699, 50),
        ],
    },
    {
        "airline": "長榮航空", "code": "BR", "is_lcc": False,
        "promo_url": "https://www.evaair.com/zh-tw/promotions/",
        "booking_url": "https://www.evaair.com/zh-tw/index.html",
        "card_selectors": [".promo-item", ".deal-card", "[class*='promotion']", "article"],
        "fallback": [
            ("LHR", 19800, 25), ("CDG", 21500, 22), ("AMS", 20500, 20), ("LAX", 22000, 28),
            ("JFK", 24500, 22), ("NRT", 8800, 30), ("ICN", 7200, 25), ("SIN", 9500, 20),
        ],
    },
    {
        "airline": "中華航空", "code": "CI", "is_lcc": False,
        "promo_url": "https://www.china-airlines.com/tw/zh/promotions",
        "booking_url": "https://www.china-airlines.com/tw/zh",
        "card_selectors": ["[class*='promo']", "[class*='deal']", ".card", "article"],
        "fallback": [
            ("CDG", 22000, 30), ("AMS", 21800, 28), ("FRA", 23500, 25), ("LAX", 25000, 22),
            ("NRT", 9200, 28), ("KIX", 8500, 32), ("ICN", 7800, 25), ("BKK", 10500, 20),
            ("SIN", 11200, 18), ("PVG", 6800, 35), ("PEK", 7500, 30), ("CAN", 7200, 28),
        ],
    },
    {
        "airline": "星宇航空", "code": "JX", "is_lcc": False,
        "promo_url": "https://www.starlux-airlines.com/zh-TW/promotions",
        "booking_url": "https://www.starlux-airlines.com/zh-TW",
        "card_selectors": ["[class*='promo']", "[class*='deal']", ".card", "article"],
        "fallback": [
            ("LAX", 28500, 20), ("SFO", 29500, 18), ("JFK", 31000, 15), ("YVR", 27500, 18),
            ("NRT", 9800, 25), ("KIX", 9200, 22), ("ICN", 8500, 20), ("SIN", 12000, 15),
            ("BKK", 11500, 18),
        ],
    },
    {
        "airline": "樂桃航空", "code": "MM", "is_lcc": True,
        "promo_url": "https://www.flypeach.com/tw/lm/ai/airports/taoyuan",
        "booking_url": "https://www.flypeach.com/tw",
        "card_selectors": ["[class*='destination']", "[class*='route']", "[class*='city']", ".card", "article"],
        "fallback": [
            ("NRT", 2199, 52), ("KIX", 1999, 55), ("FUK", 1899, 50), ("OKA", 1699, 48),
            ("CTS", 2499, 42), ("NGO", 1999, 46), ("ICN", 1899, 44),
        ],
    },
    {
        "airline": "酷航", "code": "TR", "is_lcc": True,
        "promo_url": "https://www.flyscoot.com/en/promotions",
        "booking_url": "https://www.flyscoot.com/en",
        "card_selectors": ["[class*='promo']", "[class*='deal']", ".card", "article"],
        "fallback": [
            ("ICN", 1699, 48), ("SIN", 1899, 45), ("BKK", 1599, 50), ("KUL", 1499, 52),
            ("SYD", 7999, 30), ("MEL", 8500, 28), ("DPS", 2199, 40), ("SGN", 1799, 45),
        ],
    },
    {
        "airline": "亞洲航空", "code": "AK", "is_lcc": True,
        "promo_url": "https://www.airasia.com/deals",
        "booking_url": "https://www.airasia.com/",
        "card_selectors": ["[class*='deal']", "[class*='promo']", "[class*='offer']", ".card"],
        "fallback": [
            ("BKK", 1299, 55), ("KUL", 1199, 58), ("SIN", 1499, 52), ("HAN", 1399, 50),
            ("SGN", 1349, 52), ("MNL", 1099, 55), ("DAD", 1499, 48), ("DPS", 1999, 42),
            ("HKT", 1699, 45), ("CGK", 1799, 40),
        ],
    },
    {
        "airline": "捷星亞洲", "code": "3K", "is_lcc": True,
        "promo_url": "https://www.jetstar.com/tw/zh/deals",
        "booking_url": "https://www.jetstar.com/tw/zh/home",
        "card_selectors": ["[class*='deal']", "[class*='fare']", "[class*='promo']"],
        "fallback": [
            ("SIN", 1899, 41), ("KUL", 1699, 44), ("BKK", 1599, 46), ("HAN", 1799, 42),
            ("SYD", 8999, 25), ("MEL", 9500, 22),
        ],
    },
]

# 中國大陸重點航線補強（無專屬促銷頁，直接以行情補上）
CHINA_ROUTES = [
    ("中華航空", "CI", False, "PVG", 4800, 38), ("長榮航空", "BR", False, "PVG", 5200, 32),
    ("台灣虎航", "IT", True, "PVG", 2999, 45), ("中華航空", "CI", False, "PEK", 5800, 30),
    ("長榮航空", "BR", False, "PEK", 5500, 28), ("中華航空", "CI", False, "CAN", 5200, 33),
    ("中華航空", "CI", False, "CTU", 6200, 25), ("中華航空", "CI", False, "XMN", 4500, 35),
    ("台灣虎航", "IT", True, "XMN", 2799, 48), ("長榮航空", "BR", False, "HGH", 5400, 28),
]

BOOKING_BY_CODE = {a["code"]: a["booking_url"] for a in AIRLINES}


# ── Travelpayouts (Aviasales) Data API：真實票價來源 ──────────────
# token 走環境變數，不寫進原始碼（GitHub Secret: TP_TOKEN）。
# marker 是聯盟行銷代碼（公開值），透過深連結訂票可獲佣金。
TP_MARKER = os.environ.get("TP_MARKER", "737996")

# 航空 IATA 代碼 → 中文名（API 以代碼回傳；未列者直接顯示代碼）
CODE_TO_NAME = {a["code"]: a["airline"] for a in AIRLINES}
CODE_TO_NAME.update({
    "CX": "國泰航空", "D7": "亞洲航空 X", "JQ": "捷星航空", "GK": "捷星日本",
    "NH": "全日空", "JL": "日本航空", "KE": "大韓航空", "OZ": "韓亞航空",
    "TG": "泰國航空", "SQ": "新加坡航空", "MH": "馬來西亞航空", "PR": "菲律賓航空",
    "VN": "越南航空", "VJ": "越捷航空", "CZ": "中國南方航空", "MU": "中國東方航空",
    "CA": "中國國際航空", "HX": "香港航空", "UO": "香港快運", "5J": "宿霧太平洋",
    "SL": "泰國獅航", "FD": "泰國亞航",
    "MF": "廈門航空", "3U": "四川航空", "SC": "山東航空", "ZH": "深圳航空",
    "HO": "吉祥航空", "9C": "春秋航空", "HU": "海南航空", "GS": "天津航空",
    "7C": "濟州航空", "TW": "德威航空", "BX": "釜山航空", "LJ": "真航空",
    "RS": "首爾航空", "ZE": "易斯達航空", "VZ": "越捷泰國", "DD": "皇雀航空",
})
LCC_CODES = {"IT", "MM", "TR", "AK", "D7", "3K", "JQ", "GK",
             "VJ", "5J", "SL", "FD", "UO",
             "9C", "7C", "TW", "BX", "LJ", "RS", "ZE", "VZ", "DD"}


def _build_baseline():
    """(code, iata) → 行情基準價，用來推估折扣（不憑空捏造）。"""
    base = {}
    for cfg in AIRLINES:
        for iata, price, _ in cfg["fallback"]:
            base[(cfg["code"], iata)] = price
    for _airline, code, _lcc, iata, price, _disc in CHINA_ROUTES:
        base[(code, iata)] = price
    return base


BASELINE = _build_baseline()


def _aviasales_link(iata, depart_date):
    """組 Aviasales 單程搜尋深連結（含 marker，點擊訂票可獲聯盟佣金）。"""
    dm = ""
    if depart_date and len(depart_date) >= 10:
        try:
            dm = datetime.strptime(depart_date[:10], "%Y-%m-%d").strftime("%d%m")
        except Exception:
            dm = ""
    path = f"TPE{dm}{iata}1" if dm else f"TPE{iata}"
    return f"https://www.aviasales.com/search/{path}?marker={TP_MARKER}"


def _tp_get(url, token):
    """送出 Travelpayouts API 請求，回傳 payload dict；失敗回 None。"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"X-Access-Token": token})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print(f"[TP] API 取得失敗：{e}")
        return None


def _parse_tp_payload(payload):
    """把 Travelpayouts 回傳資料轉成標準 deal 清單（source=live）。"""
    if not payload or not payload.get("success"):
        if payload is not None:
            print(f"[TP] API success=false：{payload.get('error')}")
        return []
    deals = []
    for it in payload.get("data") or []:
        iata = it.get("destination")
        price = it.get("value") or it.get("price")
        if not iata or not price or iata in ("TPE", "KHH", "RMQ"):
            continue
        if "actual" in it and not it.get("actual"):
            continue  # 跳過過期/非現價
        code = (it.get("airline") or it.get("gate") or "").strip().upper()
        airline = CODE_TO_NAME.get(code, code or "多家航空")
        depart = it.get("depart_date") or it.get("departure_at") or ""
        link = _aviasales_link(iata, depart)
        base = BASELINE.get((code, iata))
        disc = round((1 - price / base) * 100) if base and price < base else 0
        d = make_deal(airline, code or "XX", code in LCC_CODES, iata,
                      int(price), disc, link, "live", link)
        exp = it.get("expires_at")
        if exp:
            d["_expires_raw"] = exp
        deals.append(d)
    return deals


def fetch_travelpayouts(token, limit=500):
    """從 Travelpayouts Data API 取台北出發的真實最低票價（source=live）。
    失敗或無資料時回傳 []，呼叫端會自動退回 fallback。"""
    url = ("https://api.travelpayouts.com/v2/prices/latest"
           "?currency=twd&origin=TPE&period_type=year&one_way=true"
           f"&page=1&limit={limit}&show_to_affiliates=true&sorting=price&token={token}")
    deals = _parse_tp_payload(_tp_get(url, token))
    print(f"[TP] 取得 {len(deals)} 筆真實票價")
    return deals


# 中國大陸主要城市（逐城市查 API 拿真實價，補強寫死的行情 fallback）
CHINA_IATAS = ["PVG", "SHA", "PEK", "PKX", "CAN", "CTU", "SZX", "HGH",
               "XMN", "CKG", "WUH", "NKG", "TSN", "KMG", "TAO", "CSX",
               "SYX", "FOC", "DLC", "KWL"]


def fetch_china_prices(token):
    """逐一查詢大陸重點城市的真實最低票價（source=live）。
    任一城市失敗只略過該城市，不影響其他城市與既有 fallback。"""
    deals = []
    for iata in CHINA_IATAS:
        url = ("https://api.travelpayouts.com/v2/prices/latest"
               f"?currency=twd&origin=TPE&destination={iata}&one_way=true"
               "&period_type=year&page=1&limit=5&show_to_affiliates=true"
               f"&sorting=price&token={token}")
        deals += _parse_tp_payload(_tp_get(url, token))
        time.sleep(0.2)
    print(f"[TP] 大陸航線取得 {len(deals)} 筆真實票價")
    return deals


def make_deal(airline, code, is_lcc, iata, price, discount, booking_url,
              source, promo_url):
    """組一筆標準格式 deal（欄位與 deals.json / 前端一致）"""
    dest_name = IATA_NAMES.get(iata, iata)
    return {
        "airline": airline, "airline_code": code, "is_lcc": is_lcc,
        "origin": "TPE", "origin_name": "台北",
        "destination": iata, "destination_name": dest_name,
        "region": get_region(dest_name),
        "price": price, "currency": "TWD",
        "discount_pct": discount,
        "title": f"{airline} 台北 → {dest_name} 限時促銷",
        "booking_url": booking_url,
        "promo_page": promo_url,
        "source": source,
        "scraped_at": datetime.now().isoformat(),
    }


def scrape_live(page, cfg):
    """用已開啟的瀏覽器頁面抓單一航空促銷頁。回傳 deal 清單（可能為空）。"""
    deals = []
    try:
        page.goto(cfg["promo_url"], wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"    [WARN] 載入失敗 {cfg['promo_url']} → {e}")
        return deals

    # 嘗試關掉 cookie / 彈窗（best effort，失敗就略過）
    for sel in ["button:has-text('接受')", "button:has-text('Accept')",
                "button:has-text('同意')", "[class*='cookie'] button"]:
        try:
            page.click(sel, timeout=1500)
            break
        except Exception:
            pass

    try:
        html = page.content()
    except Exception:
        return deals

    if not HAS_BS4:
        return deals

    soup = BeautifulSoup(html, "lxml")
    cards = []
    for sel in cfg["card_selectors"]:
        cards = soup.select(sel)
        if cards:
            break

    seen_dest = set()
    for card in cards[:30]:
        txt = card.get_text(" ", strip=True)
        if len(txt) < 4:
            continue
        iata, name = match_destination(txt)
        price = clean_price(txt)
        if not (iata and price):
            continue
        if iata in seen_dest:
            continue
        seen_dest.add(iata)
        link = card.find("a", href=True)
        href = link["href"] if link else cfg["booking_url"]
        if href.startswith("/"):
            href = cfg["booking_url"].rstrip("/") + href
        d = make_deal(cfg["airline"], cfg["code"], cfg["is_lcc"], iata, price,
                      None, href, "live", cfg["promo_url"])
        deals.append(d)
    return deals


def build_fallback(cfg):
    return [
        make_deal(cfg["airline"], cfg["code"], cfg["is_lcc"], iata, price,
                  disc, cfg["booking_url"], "known_promo", cfg["promo_url"])
        for iata, price, disc in cfg["fallback"]
    ]


# ── 特殊活動：破盤超低價 + 活動目的地 ─────────────────────────────
# 活動只收「季節性、會週期重複」的事件（演唱會檔期變動太快、易過期，不收）；
# 綁定城市 + 月日區間，只有活動「即將到來」時才亮燈，所以永不過期。
EVENTS = [
    ("NRT", "🎆 東京夏日花火季", (7, 1), (8, 31)),
    ("HND", "🎆 東京夏日花火季", (7, 1), (8, 31)),
    ("KIX", "🏮 京都祇園祭・大阪夏祭", (7, 1), (8, 15)),
    ("FUK", "🎆 福岡夏日花火", (7, 1), (8, 31)),
    ("OKA", "🏝️ 沖繩夏季海島季", (6, 15), (9, 15)),
    ("CTS", "☃️ 札幌雪祭", (2, 1), (2, 15)),
    ("ICN", "🍁 首爾賞楓季", (10, 15), (11, 15)),
    ("GMP", "🍁 首爾賞楓季", (10, 15), (11, 15)),
    ("NRT", "🌸 東京賞櫻季", (3, 20), (4, 15)),
    ("KIX", "🌸 京阪賞櫻季", (3, 20), (4, 15)),
    ("BKK", "💦 曼谷潑水節", (4, 12), (4, 16)),
    ("NRT", "🎉 東京跨年倒數", (12, 28), (1, 2)),
    ("ICN", "🎉 首爾跨年倒數", (12, 28), (1, 2)),
    ("BKK", "🎉 曼谷跨年倒數", (12, 28), (1, 2)),
    ("HKG", "🎆 香港跨年煙火", (12, 28), (1, 2)),
]
SPECIAL_HORIZON = 150  # 活動起始日在未來這麼多天內，就視為「即將到來」
FLASH_DISCOUNT = 50    # 折扣 ≥ 此值視為破盤超低價


def _event_label(iata, now):
    """回傳該目的地『即將到來』的活動標籤；沒有就回 None。"""
    best, best_days = None, None
    for ic, label, (sm, sd), (em, ed) in EVENTS:
        if ic != iata:
            continue
        for yr in (now.year, now.year + 1):
            try:
                start = datetime(yr, sm, sd)
                end_year = yr if (em, ed) >= (sm, sd) else yr + 1
                end = datetime(end_year, em, ed, 23, 59)
            except ValueError:
                continue
            if end < now:
                continue
            days = (start - now).days
            if days > SPECIAL_HORIZON:
                continue
            if best_days is None or days < best_days:
                best, best_days = label, days
    return best


def tag_special(deals, now):
    """為每筆 deal 標記 is_special / special_label（破盤超低價 + 活動目的地）。"""
    for d in deals:
        labels = []
        ev = _event_label(d["destination"], now)
        if ev:
            labels.append(ev)
        if (d.get("discount_pct") or 0) >= FLASH_DISCOUNT:
            labels.append("🔥 破盤超低價")
        d["is_special"] = bool(labels)
        d["special_label"] = labels[0] if labels else ""
        d["special_labels"] = labels


def run_all():
    print("=" * 56)
    print("飛出台灣 爬蟲啟動 —", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 真實票價優先：有 TP_TOKEN 就用 Travelpayouts API；沒有才走 Playwright
    token = os.environ.get("TP_TOKEN", "").strip()
    api_deals = fetch_travelpayouts(token) if token else []
    if token:
        api_deals += fetch_china_prices(token)
    if token and not api_deals:
        print("[TP] 無即時資料，全程退回行情 fallback")
    use_browser = HAS_PLAYWRIGHT and not token
    print("即時來源:", "Travelpayouts API" if token else
          ("Playwright" if HAS_PLAYWRIGHT else "無（全程用 fallback）"))
    print("=" * 56)

    all_deals = list(api_deals)
    browser = pw = None
    if use_browser:
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
        except Exception as e:
            print(f"[WARN] 瀏覽器啟動失敗，改用 fallback：{e}")
            browser = None

    for cfg in AIRLINES:
        print(f"[{cfg['airline']}] 抓取中…")
        live = []
        if browser:
            try:
                ctx = browser.new_context(user_agent=UA, locale="zh-TW")
                page = ctx.new_page()
                live = scrape_live(page, cfg)
                ctx.close()
            except Exception as e:
                print(f"    [ERROR] {e}")
            time.sleep(random.uniform(1.0, 2.0))

        if len(live) >= 3:
            all_deals.extend(live)
            print(f"    → 即時抓到 {len(live)} 筆")
        else:
            fb = build_fallback(cfg)
            all_deals.extend(fb)
            print(f"    → 即時 {len(live)} 筆不足，補 fallback {len(fb)} 筆")

    # 中國大陸航線補強
    for airline, code, lcc, iata, price, disc in CHINA_ROUTES:
        all_deals.append(make_deal(airline, code, lcc, iata, price, disc,
                                   BOOKING_BY_CODE.get(code, ""), "known_promo",
                                   BOOKING_BY_CODE.get(code, "")))

    if browser:
        browser.close()
    if pw:
        pw.stop()

    # 去重：同一航空 + 同一目的地只保留「最低價」那筆；同價時 live 優先
    best = {}
    for d in all_deals:
        key = (d["airline_code"], d["destination"])
        cur = best.get(key)
        if (cur is None or d["price"] < cur["price"]
                or (d["price"] == cur["price"]
                    and d.get("source") == "live" and cur.get("source") != "live")):
            best[key] = d
    unique = list(best.values())

    # 補欄位 + 含稅 + 到期時間
    # 注意：不偽造數據——沒有真實折扣就標 0、沒有真實到期時間就不顯示倒數、
    # 不生成假點擊數（信任是這個站的根本，假數據也會過不了聯盟行銷審核）
    now = datetime.now()
    for i, d in enumerate(unique):
        d["id"] = i + 1
        if d.get("discount_pct") is None:
            d["discount_pct"] = 0
        exp_raw = d.pop("_expires_raw", None)
        if exp_raw:
            try:
                edt = datetime.fromisoformat(
                    str(exp_raw).replace("Z", "+00:00")).replace(tzinfo=None)
                d["expires_at"] = edt.isoformat()
                d["hours_remaining"] = max(1, int((edt - now).total_seconds() // 3600))
            except Exception:
                pass  # 解析失敗就不給到期欄位，前端不顯示倒數
        tax_rate = 0.25 if d["is_lcc"] else 0.20
        d["price_with_tax"] = int(d["price"] * 2 * (1 + tax_rate))  # 來回含稅估算

    # 特殊活動標記（破盤超低價 + 即將到來的活動目的地）
    tag_special(unique, now)

    # 排序：價格由低到高（呼應「全站最便宜」）
    unique.sort(key=lambda x: x["price"])

    stats = {"total": len(unique), "by_region": {}, "by_airline": {},
             "last_updated": now.isoformat(), "update_interval_minutes": 15,
             "data_note": "即時抓取者標記 source=live；其餘為市場行情參考(known_promo)。"
                          "點擊後直達各航空官方訂票頁，請以官網顯示為準。"}
    for d in unique:
        stats["by_region"][d["region"]] = stats["by_region"].get(d["region"], 0) + 1
        stats["by_airline"][d["airline"]] = stats["by_airline"].get(d["airline"], 0) + 1
    stats["special_count"] = sum(1 for d in unique if d.get("is_special"))

    # 原子寫入：先寫暫存檔再 replace，避免中途被中斷留下半截 JSON
    tmp_path = OUT_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "deals": unique}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, OUT_PATH)

    live_cnt = sum(1 for d in unique if d.get("source") == "live")
    print("\n" + "=" * 56)
    print(f"✅ 完成！共 {len(unique)} 筆（即時 {live_cnt} / 行情 {len(unique)-live_cnt}）")
    if unique:
        c = unique[0]
        print(f"🏆 全站最低：{c['airline']} 台北→{c['destination_name']} ${c['price']:,} TWD")
    print(f"📁 已存至 {OUT_PATH}")
    print("=" * 56)
    return unique


if __name__ == "__main__":
    run_all()
# 2026-06-10 更新：utf-8 輸出、原子寫入、移除偽造數據（clicks/隨機折扣/假倒數）
