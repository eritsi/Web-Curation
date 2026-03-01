import yt_dlp
import re

CHANNEL_URL = "https://www.youtube.com/@yuutera"

ydl_opts = {
    "extract_flat": True,
    "quiet": True,
    "extractor_args": {
        "youtube": {
            "lang": ["ja"]
        }
    }
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(CHANNEL_URL, download=False)
    entries = info.get("entries", [])
    if entries and "entries" in entries[0]:
        entries = entries[0]["entries"]

videos = []
for entry in entries:
    video_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
    title = entry.get("title", "タイトル不明")
    url = f"https://www.youtube.com/watch?v={video_id}"
    videos.append((title, url))

# 分類
categories = {
    "ゼロから世界史（講座シリーズ）": r"ゼロから世界史第?\d+講|世界史?\d+講",
    "ゼロから日本史（講座シリーズ）": r"ゼロから日本史第?\d+講|日本史第?\d+講|平成史第?\d+講|日本史?\d+",
    "テーマ史": r"テーマ史",
    "総集編": r"総集編",
    "文化史・伝記": r"世界文化史|文化史|世界伝記|人物史",
    "佐藤幸夫": r"幸夫(?!.*大紀行|時事)|世界史講師",
    "世界時事・時事解説": r"世界時事|イスラエルvsイラン",
    "受験対策": r"共通テスト|私大|勉強法|対策|論述|直前|入試|代ゼミ|東大|受験|合格|慶應",
    "英語講座": r"英文法|英文解釈|英語長文|英作文|和文英訳|語源講座|即効英|英単語|早慶ハイレベル|背景知識講座|英語学",
    "現代文・古文講座": r"現代文|古文常識|古典|漢文|基礎現代文",
    "世界史大紀行（旅行記）": r"大紀行|旅行記|ひとり旅",
    "メンバー限定": r"メンバー|会員限定",
    "その他": r".*",
}

grouped = {k: [] for k in categories}

for title, url in videos:
    for cat, pattern in categories.items():
        if re.search(pattern, title):
            grouped[cat].append((title, url))
            break

for cat, items in grouped.items():
    print(f"\n## {cat} ({len(items)}本)")
    for title, url in items:
        print(f"- {title} - {url}")