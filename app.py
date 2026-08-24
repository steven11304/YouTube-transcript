import streamlit as st
import re
import html
import requests
import json
import xml.etree.ElementTree as ET

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("直連 YouTube 官方資料流，支援長影片、直播重播與自動辨識字幕")

def extract_video_id(url: str):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:live\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"00:{m:02d}:{s:02d}"

def parse_caption_content(base_url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 策略 1：嘗試 json3 格式
    try:
        res = requests.get(base_url + "&fmt=json3", headers=headers, timeout=12)
        if res.status_code == 200 and res.text.strip().startswith("{"):
            data = res.json()
            lines = []
            for ev in data.get("events", []):
                if "segs" in ev:
                    start_sec = ev.get("tStartMs", 0) / 1000.0
                    text = "".join([s.get("utf8", "") for s in ev.get("segs", [])]).replace("\n", " ").strip()
                    if text:
                        lines.append(f"[{format_time(start_sec)}] {text}")
            if lines:
                return lines
    except Exception:
        pass

    # 策略 2：備用 XML 格式
    res = requests.get(base_url, headers=headers, timeout=12)
    root = ET.fromstring(res.text)
    lines = []
    for elem in root.findall("text"):
        start_sec = float(elem.attrib.get("start", 0))
        text = html.unescape(elem.text or "").replace("\n", " ").strip()
        if text:
            lines.append(f"[{format_time(start_sec)}] {text}")
    return lines

def fetch_youtube_transcript(video_id: str):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"
    }

    caption_tracks = []

    # 方案 A：Web Innertube API
    innertube_payload = {
        "context": {
            "client": {
                "hl": "zh-TW",
                "gl": "TW",
                "clientName": "WEB",
                "clientVersion": "2.20240101.00.00"
            }
        },
        "videoId": video_id
    }

    try:
        r = requests.post(
            "https://www.youtube.com/youtubei/v1/player",
            json=innertube_payload,
            headers=headers,
            timeout=12
        )
        if r.status_code == 200:
            data = r.json()
            caption_tracks = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    except Exception:
        pass

    # 方案 B：網頁端播放器數據提取（備用）
    if not caption_tracks:
        try:
            page_res = requests.get(f"https://www.youtube.com/watch?v={video_id}", headers=headers, timeout=12)
            match = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});(?:var\s|window\[|\n|</script>)', page_res.text)
            if match:
                player_data = json.loads(match.group(1))
                caption_tracks = player_data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
            else:
                cap_match = re.search(r'"captionTracks":\[(.*?)\]', page_res.text)
                if cap_match:
                    caption_tracks = json.loads(f"[{cap_match.group(1)}]")
        except Exception:
            pass

    if not caption_tracks:
        raise Exception("該影片尚未生成逐字稿，或已設為私人/關閉字幕。")

    # 篩選中文（繁/簡）或英文軌道
    target_track = None
    for track in caption_tracks:
        lang = track.get("languageCode", "").lower()
        if lang in ["zh", "zh-tw", "zh-hk", "zh-cn", "zh-hant", "zh-hans", "en"]:
            target_track = track
            break
    if not target_track:
        target_track = caption_tracks[0]

    base_url = target_track.get("baseUrl")
    if not base_url:
        raise Exception("無法取得字幕下載串流。")

    return parse_caption_content(base_url)

# 前端輸入介面
url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在向 YouTube 伺服器讀取逐字稿資料流..."):
                try:
                    output_lines = fetch_youtube_transcript(video_id)
                    full_text = "\n".join(output_lines)

                    st.success(f"提取成功！共 {len(output_lines)} 句逐字紀錄。")
                    st.download_button(
                        label="📥 下載 TXT 逐字稿",
                        data=full_text,
                        file_name=f"{video_id}_transcript.txt",
                        mime="text/plain; charset=utf-8"
                    )

                    with st.expander("預覽逐字稿內容（前 50 行）"):
                        st.text("\n".join(output_lines[:50]))

                except Exception as e:
                    st.error(f"提取失敗：{str(e)}")
