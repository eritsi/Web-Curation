import yaml
import json
import hashlib
import html as htmllib
import re
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

SNAPSHOT_DIR = "snapshots"
NEWS_FILE = "news.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; news-monitor/1.0)"}

os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def fetch(url, verify=True):
    if not verify:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    r = requests.get(url, headers=HEADERS, timeout=20, verify=verify)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    return r.text


def get_soup(html, selector_str):
    full = BeautifulSoup(html, "html.parser")
    if not selector_str:
        return full
    for sel in [s.strip() for s in selector_str.split(",")]:
        found = full.select(sel)
        if found:
            return BeautifulSoup("".join(str(t) for t in found), "html.parser")
    return full


def extract_sections(soup):
    """h2単位でコンテンツをグループ化する"""
    sections = []
    current = None
    for tag in soup.find_all(["h2", "h3", "h4", "p", "li"]):
        text = tag.get_text(strip=True)
        if not text:
            continue
        if tag.name == "h2":
            if current:
                sections.append(current)
            current = {"title": text, "body": []}
        elif current and tag.name in ["h3", "h4"]:
            current["body"].append(f"▸ {text}")
        elif current and len(text) > 4:
            current["body"].append(text)
    if current:
        sections.append(current)
    return sections


def extract_announcements(soup, base_url=""):
    """h2=月, h3=案内 の2段構造で抽出。各案内に直後のp（販売日時）とリンクを紐付ける"""
    months = []
    current_month = None
    current_ann = None

    for tag in soup.find_all(["h2", "h3", "h4", "p", "li"]):
        text = tag.get_text(strip=True)
        if not text:
            continue
        if tag.name == "h2":
            if current_ann and current_month is not None:
                current_month["announcements"].append(current_ann)
            current_ann = None
            if current_month is not None:
                months.append(current_month)
            current_month = {"title": text, "announcements": []}
        elif tag.name in ["h3", "h4"] and current_month is not None:
            if current_ann:
                current_month["announcements"].append(current_ann)
            current_ann = {"store": text, "details": [], "links": []}
        elif tag.name in ["p", "li"] and current_ann is not None and text:
            current_ann["details"].append(text)
            seen_hrefs = {l["href"] for l in current_ann["links"]}
            for a in tag.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http"):
                    href = urljoin(base_url, href)
                if href not in seen_hrefs:
                    current_ann["links"].append({
                        "text": a.get_text(strip=True) or "リンク",
                        "href": href,
                    })
                    seen_hrefs.add(href)

    if current_ann and current_month is not None:
        current_month["announcements"].append(current_ann)
    if current_month is not None:
        months.append(current_month)

    return months


def extract_text(soup):
    """フラットなテキストアイテムのリストを返す"""
    items = []
    seen = set()
    for tag in soup.find_all(["h2", "h3", "h4", "p", "li"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 4 and text not in seen:
            items.append(text)
            seen.add(text)
    return items


def extract_links(soup, base_url, link_filter):
    """フィルタにマッチするリンクを抽出する"""
    pattern = re.compile(link_filter) if link_filter else None
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text:
            continue
        if pattern and not pattern.search(text):
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        if href not in seen:
            links.append({"text": text, "href": href})
            seen.add(href)
    return links


def load_snapshot(sid):
    path = os.path.join(SNAPSHOT_DIR, f"{sid}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_snapshot(sid, data):
    path = os.path.join(SNAPSHOT_DIR, f"{sid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_id(name):
    return hashlib.md5(name.encode()).hexdigest()[:8]


def process_announcements(site, current_months, prev):
    keep = site.get("keep_latest", 2)

    # 既存のキーセット（月タイトル::店名）
    prev_keys = {
        f"{m['title']}::{a['store']}"
        for m in prev.get("months", [])
        for a in m.get("announcements", [])
    }

    new_keys = []
    for m in current_months:
        for a in m.get("announcements", []):
            key = f"{m['title']}::{a['store']}"
            if key not in prev_keys:
                new_keys.append(key)

    kept = current_months[:keep]

    return {
        "changed": len(new_keys) > 0,
        "new_keys": new_keys,
        "months": kept,
    }


def process_sections(site, current, prev):
    keep = site.get("keep_latest")
    prev_titles = {s["title"] for s in prev.get("sections", [])}
    new_sections = [s for s in current if s["title"] not in prev_titles]

    # ページ上の順序で保持、keep_latest を適用
    kept = current[:keep] if keep else current

    return {
        "changed": len(new_sections) > 0,
        "new_titles": [s["title"] for s in new_sections],
        "sections": kept,
    }


def process_text(site, current, prev):
    keep = site.get("keep_latest")
    prev_set = set(prev.get("items", []))
    new_items = [t for t in current if t not in prev_set]

    merged = new_items + [t for t in prev.get("items", []) if t not in set(new_items)]
    if keep:
        merged = merged[:keep]

    return {
        "changed": len(new_items) > 0,
        "new_items": new_items,
        "items": merged,
    }


def extract_show_schedule(soup, site, base_url, year_month=None):
    """スケジュールページから公演一覧を抽出する（新着公演の検知用）"""
    item_sel        = site.get("item_selector",          ".schedule-item")
    link_sel        = site.get("link_selector",          "a")
    artist_sel      = site.get("artist_selector",        "h2")
    date_sel        = site.get("date_selector",          ".date")
    date_sel2       = site.get("date_selector2",         "")
    title_sel       = site.get("title_selector",         "h3")
    require_child   = site.get("require_child_selector", "")
    excl_artist_pat = site.get("exclude_artist_pattern", "")
    filter_past     = site.get("filter_past",            False)
    today_str       = datetime.now().strftime("%Y%m%d")

    shows = []
    seen_urls = set()
    exclude_pat = site.get("exclude_link_pattern", "")
    for el in soup.select(item_sel):
        # カテゴリフィルタ（例：エンタメのみ）
        if require_child and not el.select_one(require_child):
            continue
        # アイテム自体が <a> の場合はそのまま使う
        if el.name == "a" and el.get("href"):
            href = el["href"]
            if not href.startswith("http"):
                href = urljoin(base_url, href)
        else:
            # メインリンクを探す（ナビ・ロゴ等を除外）
            link_el = el.select_one(link_sel) if link_sel != "a" else None
            if not link_el:
                for a in el.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = urljoin(base_url, href)
                    if exclude_pat and re.search(exclude_pat, href):
                        continue
                    link_el = a
                    break
            if not link_el:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = urljoin(base_url, href)
        if exclude_pat and re.search(exclude_pat, href):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        artist_el = el.select_one(artist_sel)
        date_el   = el.select_one(date_sel)
        title_el  = el.select_one(title_sel)

        artist = artist_el.get_text(strip=True) if artist_el else ""
        date   = date_el.get_text(strip=True) if date_el else ""
        title  = title_el.get_text(strip=True)[:60] if title_el else ""

        # date_selector2 が指定されている場合は2つのテキストを結合
        if date_sel2:
            date_el2 = el.select_one(date_sel2)
            if date_el2:
                date = f"{date}.{date_el2.get_text(strip=True)}"

        # year_month が渡されている場合（月別URLページ）は年月を付与
        if year_month and date:
            y, m = year_month
            day = date.split(".")[-1]
            date = f"{y}.{m:02d}.{day}"

        # アーティスト名除外パターン
        if excl_artist_pat and re.search(excl_artist_pat, artist):
            continue

        # 過去公演を除外（YYYY.M.D や YYYY.MM.DD 形式に対応）
        if filter_past and date:
            parts = re.split(r"\D+", date.strip())
            parts = [p for p in parts if p]
            if len(parts) >= 3:
                try:
                    show_dt = f"{int(parts[0]):04d}{int(parts[1]):02d}{int(parts[2]):02d}"
                    if show_dt < today_str:
                        continue
                except ValueError:
                    pass

        shows.append({
            "url":    href,
            "artist": artist,
            "date":   date,
            "title":  title,
        })
    return shows


def process_show_schedule(site, current, prev):
    keep = site.get("keep_latest")
    if keep:
        current = current[:keep]
    prev_urls = set(prev.get("urls", []))
    new_shows = [s for s in current if s["url"] not in prev_urls]
    return {
        "changed":   bool(new_shows),
        "new_shows": new_shows,
        "urls":      [s["url"] for s in current],
        "shows":     current,
    }


def fetch_wp_schedule_api(site):
    """WordPress REST API からスケジュールを全件取得する"""
    api_url  = site.get("api_url")
    per_page = site.get("per_page", 100)
    endpoint = site.get("api_type", "schedule")  # カスタム投稿タイプ名

    url = f"{api_url}?per_page={per_page}&orderby=id&order=desc&_fields=id,slug,title,link"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    items = r.json()

    today = datetime.now().strftime("%Y%m%d")
    shows = []
    for item in items:
        wp_id = item.get("id")
        slug  = item.get("slug", "")
        link  = item.get("link", "")
        title = htmllib.unescape(item.get("title", {}).get("rendered", ""))

        # slug YYYYMMDD-N から公演日を抽出
        m = re.match(r"(\d{4})(\d{2})(\d{2})", slug)
        if not m:
            continue
        slug_date = m.group(1) + m.group(2) + m.group(3)
        if slug_date < today:
            continue  # 過去の公演は除外
        date = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

        shows.append({
            "id":     wp_id,
            "url":    link,
            "artist": title,
            "date":   date,
            "title":  title,
        })
    return shows


def process_wp_schedule(site, current, prev):
    prev_ids = set(prev.get("ids", []))
    new_shows = [s for s in current if s["id"] not in prev_ids]
    return {
        "changed":   bool(new_shows),
        "new_shows": new_shows,
        "ids":       [s["id"] for s in current],
        "shows":     current,
    }


def extract_venue_news(soup, site, base_url):
    """ビルボードライブ等の what's-new ページからイベント情報を抽出する"""
    item_sel  = site.get("item_selector",        "[class*='LatestNews_item']")
    tag_sel   = site.get("tag_selector",         "[class*='LatestNews_tag']")
    content_sel = site.get("content_selector",   "[class*='LatestNews_content'] p")
    id_attr   = site.get("id_attr",              "data-id")

    items = []
    for el in soup.select(item_sel):
        item_id = el.get(id_attr, "")
        if not item_id:
            continue

        link_el = el.find("a", href=True)
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"):
            href = urljoin(base_url, href)

        tag_el     = el.select_one(tag_sel)
        content_el = el.select_one(content_sel)

        # 公演日：performanceYear + performanceDay + weekday を組み合わせる
        year_el    = el.select_one("[class*='performanceYear']")
        day_el     = el.select_one("[class*='performanceDay']")
        weekday_el = el.select_one("[class*='performanceWeekday']")
        show_date  = ""
        if year_el and day_el:
            y = year_el.get_text(strip=True)
            d = re.sub(r"\s+", "", day_el.get_text(strip=True))
            w = weekday_el.get_text(strip=True) if weekday_el else ""
            show_date = f"{y}.{d}{w}"

        event_id = None
        m = re.search(r"event_id=([\w-]+)", href)
        if m:
            event_id = m.group(1)

        items.append({
            "item_id":   item_id,
            "event_id":  event_id,
            "tag":       tag_el.get_text(strip=True) if tag_el else "",
            "content":   content_el.get_text(strip=True)[:80] if content_el else "",
            "show_date": show_date,
            "url":       href,
        })
    return items


def process_venue_news(site, current, prev):
    new_evt_pat = re.compile(site.get("new_event_tags", "新規公演決定"))
    ticket_pat  = re.compile(site.get("ticket_tags",    "先行|発売|受付|チケット"))

    prev_item_ids  = set(prev.get("item_ids",  []))
    prev_event_ids = set(prev.get("event_ids", []))

    new_events     = []
    ticket_updates = []

    for item in current:
        if item["item_id"] in prev_item_ids:
            continue  # 既知のニュースアイテム

        eid = item.get("event_id")
        tag = item.get("tag", "")

        if eid and eid not in prev_event_ids:
            new_events.append(item)          # 初出のイベント
        elif eid and eid in prev_event_ids and ticket_pat.search(tag):
            ticket_updates.append(item)      # 既知イベントにチケット系タグ
        elif not eid:
            new_events.append(item)          # SNS等の非イベントニュース

    return {
        "changed":        bool(new_events or ticket_updates),
        "new_events":     new_events,
        "ticket_updates": ticket_updates,
        "item_ids":       [i["item_id"]  for i in current if i["item_id"]],
        "event_ids":      list({i["event_id"] for i in current if i.get("event_id")}),
        "all_items":      current[:15],
    }


def process_links(site, current, prev):
    prev_hrefs = {l["href"] for l in prev.get("links", [])}
    new_links = [l for l in current if l["href"] not in prev_hrefs]
    changed = current != prev.get("links", [])

    return {
        "changed": changed,
        "new_links": new_links,
        "links": current,
    }


def main():
    with open("sites.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    results = []

    for site in config.get("sites", []):
        name = site["name"]
        sid = make_id(name)
        extract = site.get("extract", "sections")

        print(f"Checking: {name}")
        try:
            prev = load_snapshot(sid)

            if extract == "wp_schedule_api":
                current = fetch_wp_schedule_api(site)
                result_data = process_wp_schedule(site, current, prev)
                new_snapshot = {"ids": result_data["ids"]}
            elif extract == "show_schedule":
                url_pattern = site.get("url_pattern")
                ssl_ok = site.get("ssl_verify", True)
                if url_pattern:
                    shows_all, seen_urls_all = [], set()
                    months_ahead = site.get("months_ahead", 3)
                    today_dt = datetime.now()
                    for i in range(months_ahead + 1):
                        total_m = today_dt.month - 1 + i
                        yr = today_dt.year + total_m // 12
                        mo = total_m % 12 + 1
                        mu = url_pattern.format(year=yr, month=mo)
                        try:
                            html = fetch(mu, verify=ssl_ok)
                            soup = get_soup(html, site.get("selector", ""))
                            for s in extract_show_schedule(soup, site, mu, year_month=(yr, mo)):
                                if s["url"] not in seen_urls_all:
                                    seen_urls_all.add(s["url"])
                                    shows_all.append(s)
                        except Exception as me:
                            print(f"    {yr}-{mo:02d} エラー: {me}")
                    current = shows_all
                else:
                    html = fetch(site["url"], verify=ssl_ok)
                    soup = get_soup(html, site.get("selector", ""))
                    current = extract_show_schedule(soup, site, site["url"])
                result_data = process_show_schedule(site, current, prev)
                new_snapshot = {"urls": result_data["urls"]}
            elif extract == "venue_news":
                html = fetch(site["url"])
                soup = get_soup(html, site.get("selector", ""))
                current = extract_venue_news(soup, site, site["url"])
                result_data = process_venue_news(site, current, prev)
                new_snapshot = {
                    "item_ids":  result_data["item_ids"],
                    "event_ids": result_data["event_ids"],
                }
            elif extract == "links":
                html = fetch(site["url"])
                soup = get_soup(html, site.get("selector", ""))
                current = extract_links(soup, site["url"], site.get("link_filter", ""))
                result_data = process_links(site, current, prev)
                new_snapshot = {"links": current}
            elif extract == "announcements":
                html = fetch(site["url"])
                soup = get_soup(html, site.get("selector", ""))
                current = extract_announcements(soup, site["url"])
                result_data = process_announcements(site, current, prev)
                new_snapshot = {"months": result_data["months"]}
            elif extract == "text":
                html = fetch(site["url"])
                soup = get_soup(html, site.get("selector", ""))
                current = extract_text(soup)
                result_data = process_text(site, current, prev)
                new_snapshot = {"items": result_data["items"]}
            elif extract == "js_pending":
                # JavaScript 必須サイト：スキップしてプレースホルダ
                result_data = {"changed": False}
                new_snapshot = {}
            else:  # sections (default)
                html = fetch(site["url"])
                soup = get_soup(html, site.get("selector", ""))
                current = extract_sections(soup)
                result_data = process_sections(site, current, prev)
                new_snapshot = {"sections": result_data["sections"]}

            save_snapshot(sid, new_snapshot)

            entry = {
                "name": name,
                "description": site.get("description", ""),
                "url": site["url"],
                "extract": extract,
                "status": "changed" if result_data["changed"] else "unchanged",
                "checked_at": now,
            }
            entry.update({k: v for k, v in result_data.items() if k != "changed"})
            results.append(entry)

            label = "変更あり !" if result_data["changed"] else "変更なし"
            print(f"  → {label}")

        except Exception as e:
            print(f"  → エラー: {e}")
            results.append({
                "name": name,
                "description": site.get("description", ""),
                "url": site["url"],
                "extract": extract,
                "status": "error",
                "error": str(e),
                "checked_at": now,
            })

    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "sites": results}, f, ensure_ascii=False, indent=2)

    print(f"\nnews.json を生成しました（{len(results)} サイト）")


if __name__ == "__main__":
    main()
