import yt_dlp

CHANNEL_URL = "https://www.youtube.com/@yobinori"

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
    
    # ネスト対応
    entries = info.get("entries", [])
    if entries and "entries" in entries[0]:
        entries = entries[0]["entries"]  # 一段掘り下げる

    for entry in entries:
        video_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
        title = entry.get("title", "タイトル不明")
        print(f"{title} - https://www.youtube.com/watch?v={video_id}")