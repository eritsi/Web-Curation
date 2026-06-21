import yaml
import json
import hashlib
import re
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

SNAPSHOT_DIR = "snapshots"
REALESTATE_FILE = "realestate.json"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def fetch(url, extra_headers=None, retries=2, backoff=5):
    import time
    headers = dict(BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    for attempt in range(retries + 1):
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 503 or attempt == retries:
            r.raise_for_status()
            return r.content
        time.sleep(backoff * (attempt + 1))
    r.raise_for_status()
    return r.content


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


def extract_globalbase(site):
    url = site["url"]
    base_url = site.get("base_url", "https://www.globalbase.jp/renocolle/obje/")
    soup = BeautifulSoup(fetch(url), "html.parser")

    listings = []
    for box in soup.select("div.prop_box"):
        a = box.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(base_url, href)

        m = re.search(r"pid=(\d+)", href)
        prop_id = m.group(1) if m else href

        h4 = box.find("h4")
        price = h4.get_text(strip=True).replace("価格/", "").strip() if h4 else ""

        spec = {}
        for li in box.select("ul.reno_spec li"):
            text = li.get_text(strip=True)
            for key in ["間取り", "専有面積", "交通", "物件名", "所在地"]:
                if text.startswith(key + ":"):
                    spec[key] = text[len(key) + 1:]

        listings.append({
            "id": prop_id,
            "url": href,
            "name": spec.get("物件名", ""),
            "price": price,
            "area": spec.get("専有面積", ""),
            "madori": spec.get("間取り", ""),
            "traffic": spec.get("交通", ""),
            "location": spec.get("所在地", ""),
        })
    return listings


def extract_meiwa(site):
    base_url_root = site.get("base_url", "https://www.meiwajisyo.co.jp/chukai/buy/sch/")
    pref_cds = site.get("pref_cds", [14])
    max_price = site.get("max_price_man")
    min_area = site.get("min_area_m2")

    listings = []
    seen_ids = set()

    for pref_cd in pref_cds:
        url = f"{site['url']}?pref_cd={pref_cd}"
        soup = BeautifulSoup(fetch(url), "html.parser")

        for item in soup.select("div.sch-item"):
            a = item.select_one("a.pos-link")
            if not a:
                continue
            href = a.get("href", "")
            if not href.startswith("http"):
                href = urljoin(base_url_root, href)

            m = re.search(r"k_number=([\w-]+)", href)
            prop_id = m.group(1) if m else href

            if prop_id in seen_ids:
                continue
            seen_ids.add(prop_id)

            name_el = item.select_one("p.ttl")
            name = name_el.get_text(strip=True) if name_el else ""

            price_el = item.select_one("p.sizes")
            price_text = price_el.get_text(strip=True) if price_el else ""
            mp = re.search(r"([\d,]+)万円", price_text)
            price_man = int(mp.group(1).replace(",", "")) if mp else 0

            sub_el = item.select_one("p.sub")
            traffic = sub_el.get_text(strip=True).replace("交　通：", "").strip() if sub_el else ""

            note_el = item.select_one("p.note")
            note = note_el.get_text(" ", strip=True) if note_el else ""
            ma = re.search(r"専有面積：([\d.]+)", note)
            area_sqm = float(ma.group(1)) if ma else 0.0
            area = f"{ma.group(1)}㎡" if ma else ""
            mm = re.search(r"間取り：\s*(\S+)", note)
            madori = mm.group(1) if mm else ""

            if max_price and price_man > max_price:
                continue
            if min_area and area_sqm < min_area:
                continue

            listings.append({
                "id": prop_id,
                "url": href,
                "name": name,
                "price": price_text,
                "area": area,
                "madori": madori,
                "traffic": traffic,
                "location": "",
            })

    return listings


def extract_suumo(site):
    url = site["url"]
    referer = site.get("referer", "https://suumo.jp/")
    soup = BeautifulSoup(fetch(url, extra_headers={"Referer": referer}), "html.parser")

    listings = []
    for unit in soup.select(".property_unit"):
        link_el = unit.select_one(".property_unit-title a")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if href and not href.startswith("http"):
            href = "https://suumo.jp" + href

        m = re.search(r"nc_(\d+)", href)
        prop_id = m.group(1) if m else href

        def get_field(label):
            for dl in unit.find_all("dl"):
                dt = dl.find("dt")
                dd = dl.find("dd")
                if dt and dd and dt.get_text(strip=True) == label:
                    return dd.get_text(strip=True)
            return ""

        price_span = unit.select_one(".dottable-value")
        price = price_span.get_text(strip=True) if price_span else get_field("販売価格")

        # Remove (壁芯) etc. from area
        area_raw = get_field("専有面積")
        area = re.sub(r"\s*[（(][^）)]*[）)]", "", area_raw).strip()

        listings.append({
            "id": prop_id,
            "url": href,
            "name": get_field("物件名") or link_el.get_text(strip=True),
            "price": price,
            "area": area,
            "madori": get_field("間取り"),
            "traffic": get_field("沿線・駅"),
            "location": get_field("所在地"),
        })

    return _filter_by_station(listings, site)


def _parse_price_man(text):
    """1億4,980万円 → 14980、5,780万円 → 5780"""
    m_oku = re.search(r"(\d+)億(?:([\d,]+)万)?円", text)
    if m_oku:
        oku = int(m_oku.group(1)) * 10000
        man = int(m_oku.group(2).replace(",", "")) if m_oku.group(2) else 0
        return oku + man
    m_man = re.search(r"([\d,]+)万円", text)
    return int(m_man.group(1).replace(",", "")) if m_man else 0


def extract_cowcamo(site):
    base_url = site.get("base_url", "https://cowcamo.jp")
    max_price = site.get("max_price_man")
    min_area = site.get("min_area_m2")
    allowed_prefs = site.get("allowed_prefs", [])

    listings = []
    seen_ids = set()

    for page in range(1, site.get("pages", 1) + 1):
        url = site["url"] if page == 1 else f"{site['url']}?page={page}"
        soup = BeautifulSoup(fetch(url), "html.parser")
        items = soup.select("div.p-entry")
        if not items:
            break

        for item in items:
            link = item.select_one("a.p-entry__cover")
            if not link:
                continue
            prop_id = link.get("data-event-label", "")
            href = link.get("href", "")
            if not href.startswith("http"):
                href = base_url + href

            pref = unquote(href.replace(base_url, "").lstrip("/")).split("/")[0]
            if allowed_prefs and pref not in allowed_prefs:
                continue

            if prop_id in seen_ids:
                continue
            seen_ids.add(prop_id or href)

            price_el = item.select_one("div.p-entry__price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_man = _parse_price_man(price_text)

            layout_el = item.select_one("div.p-entry__layout")
            layout_text = layout_el.get_text(" ", strip=True) if layout_el else ""
            ma = re.search(r"([\d.]+)㎡", layout_text)
            area_sqm = float(ma.group(1)) if ma else 0.0
            area = f"{ma.group(1)}㎡" if ma else ""
            mm = re.search(r"㎡\s*・\s*(\S+)", layout_text)
            madori = mm.group(1) if mm else ""

            traffic, location = "", ""
            for span in item.select("div.p-entry__misc span"):
                text = span.get_text(strip=True)
                if ("駅" in text or "徒歩" in text) and not traffic:
                    traffic = text
                elif not location and text and "不可" not in text and "可" not in text:
                    location = text

            title_el = item.select_one("a.p-entry__title")
            name = title_el.get_text(strip=True) if title_el else unquote(href.rstrip("/").split("/")[-1])

            if max_price and price_man > max_price:
                continue
            if min_area and area_sqm < min_area:
                continue

            listings.append({
                "id": prop_id or href,
                "url": href,
                "name": name,
                "price": price_text,
                "area": area,
                "madori": madori,
                "traffic": traffic,
                "location": location or pref,
            })

    return listings


def extract_rte(site):
    url = site["url"]
    base_url = site.get("base_url", "https://www.realtokyoestate.co.jp")
    max_price = site.get("max_price_man")
    min_area = site.get("min_area_m2")

    soup = BeautifulSoup(fetch(url), "html.parser")
    listings = []

    for table in soup.select("table.estate_link"):
        a = table.find("a", href=lambda h: h and "estate.php?n=" in h)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = base_url + href
        m = re.search(r"n=(\d+)", href)
        prop_id = m.group(1) if m else href

        b = a.find("b")
        name = b.get_text(strip=True) if b else a.get_text(strip=True)

        price_span = table.find("span", style=lambda s: s and "5f221c" in s)
        price_text = price_span.get_text(strip=True) if price_span else ""
        price_man = _parse_price_man(price_text)
        ma = re.search(r"([\d.]+)㎡", price_text)
        area_sqm = float(ma.group(1)) if ma else 0.0
        area = f"{ma.group(1)}㎡" if ma else ""
        price = re.sub(r"\s*/.*", "", price_text).strip()

        loc_span = table.find("span", style=lambda s: s and "13px" in s and "4d4d4d" in s)
        location = loc_span.get_text(strip=True) if loc_span else ""
        if re.search(r"(?!神奈川)[^\s]+県", location):
            continue

        traffic = ""
        for span in table.find_all("span", style=lambda s: s and "12px" in s and "4d4d4d" in s):
            if span.find("b"):
                traffic = span.get_text(strip=True)
                break

        if max_price and price_man > max_price:
            continue
        if min_area and area_sqm < min_area:
            continue

        listings.append({
            "id": prop_id,
            "url": href,
            "name": name,
            "price": price,
            "area": area,
            "madori": "",
            "traffic": traffic,
            "location": location,
        })

    return listings


def _filter_by_station(listings, site):
    allowed_stations = site.get("allowed_stations", [])
    max_walk_min = site.get("max_walk_min")

    if not allowed_stations and max_walk_min is None:
        return listings

    filtered = []
    for prop in listings:
        traffic = prop.get("traffic", "")

        if allowed_stations and not any(s in traffic for s in allowed_stations):
            continue

        if max_walk_min is not None:
            m = re.search(r"徒歩(\d+)分", traffic)
            if not m or int(m.group(1)) > max_walk_min:
                continue

        filtered.append(prop)
    return filtered


def extract_sections(soup):
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


def process_listings(current, prev):
    prev_ids = set(prev.get("ids", []))
    new_listings = [l for l in current if l["id"] not in prev_ids]
    return {
        "changed": bool(new_listings),
        "new_listings": new_listings,
        "all_listings": current,
        "ids": [l["id"] for l in current],
    }


def process_sections(current, prev, keep=None):
    prev_titles = {s["title"] for s in prev.get("sections", [])}
    new_sections = [s for s in current if s["title"] not in prev_titles]
    kept = current[:keep] if keep else current
    return {
        "changed": bool(new_sections),
        "new_titles": [s["title"] for s in new_sections],
        "sections": kept,
    }


def main():
    with open("sites.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    now = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S")
    results = []

    for site in config.get("sites", []):
        name = site["name"]
        sid = make_id(name)
        extract = site.get("extract", "sections")

        print(f"Checking: {name}")
        try:
            prev = load_snapshot(sid)

            if extract == "globalbase":
                current = extract_globalbase(site)
                result_data = process_listings(current, prev)
                new_snapshot = {"ids": result_data["ids"]}
            elif extract == "meiwa":
                current = extract_meiwa(site)
                result_data = process_listings(current, prev)
                new_snapshot = {"ids": result_data["ids"]}
            elif extract == "cowcamo":
                current = extract_cowcamo(site)
                result_data = process_listings(current, prev)
                new_snapshot = {"ids": result_data["ids"]}
            elif extract == "rte":
                current = extract_rte(site)
                result_data = process_listings(current, prev)
                new_snapshot = {"ids": result_data["ids"]}
            elif extract == "suumo":
                current = extract_suumo(site)
                result_data = process_listings(current, prev)
                new_snapshot = {"ids": result_data["ids"]}
            elif extract == "sections":
                soup = BeautifulSoup(fetch(site["url"]), "html.parser")
                current = extract_sections(soup)
                result_data = process_sections(current, prev, keep=site.get("keep_latest"))
                new_snapshot = {"sections": result_data["sections"]}
            else:
                result_data = {"changed": False}
                new_snapshot = {}

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

            label = "新着あり !" if result_data["changed"] else "変更なし"
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

    with open(REALESTATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "sites": results}, f, ensure_ascii=False, indent=2)

    print(f"\nrealestate.json を生成しました（{len(results)} サイト）")


if __name__ == "__main__":
    main()
