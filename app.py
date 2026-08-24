import streamlit as st
import re
import html
import requests
import json
import xml.etree.ElementTree as ET

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("直連 YouTube 後端資料流，支援自動辨識與直播重播逐字稿")

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

def fetch_youtube_transcript(video_id: str):
    """透過 YouTube Android Innertube API 直接獲取字幕軌數據"""
    api_url = "https://www.youtube.com/youtubei/v1/player"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "com.google.android.youtube/19.29.35 (Linux; U; Android 11) gzip"
    }
    payload = {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.29.35",
                "hl": "zh-TW",
                "gl": "TW"
            }
        },
        "videoId": video_id
    }

    response = requests.post(api_url, json=payload, headers=headers, timeout=15)
    if response.status_code != 200:
        raise Exception(f"YouTube 伺服器回應異常 (狀態碼: {response.status_code})")

    data = response.json()
    
    # 檢查是否含有字幕軌
    captions = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    if not captions:
        raise Exception("該影片後台尚未生成語音辨識字幕，或創作者已停用逐字稿功能。")

    # 1. 優先選取中文或英文軌道，若無則選取第一條預設軌道
    target_track = None
    for track in captions:
        lang_code = track.get("languageCode", "").lower()
        if lang_code in ["zh", "zh-tw", "zh-hk", "zh-cn", "zh-hant", "zh-hans", "en"]:
            target_track = track
            break
    if not target_track:
        target_track = captions[0]

    base_url = target_track.get("baseUrl")
    if not base_url:
        raise Exception("無法解析字幕下載串流網址。")

    # 2. 請求字幕內容 (使用 json3 格式確保相容性)
    sub_res = requests.get(base_url + "&fmt=json3", timeout=15)
    parsed_lines = []

    if sub_res.status_code == 200 and sub_res.text.strip().startswith("{"):
        sub_data = sub_res.json()
        events = sub_data.get("events", [])
        for ev in events:
            if "segs" in ev:
                start_sec = ev.get("tStartMs", 0) / 1000.0
                text = "".join([s.get("utf8", "") for s in ev.get("segs", [])]).replace("\n", " ").strip()
                if text:
                    parsed_lines.append(f"[{format_time(start_sec)}] {text}")
    else:
        # 若非 JSON 格式則採用 XML 解析
        xml_res = requests.get(base_url, timeout=15)
        root = ET.fromstring(xml_res.text)
        for elem in root.findall("text"):
            start_sec = float(elem.attrib.get("start", 0))
            text = html.unescape(elem.text or "").replace("\n", " ").strip()
            if text:
                parsed_lines.append(f"[{format_time(start_sec)}] {text}")

    if not parsed_lines:
        raise Exception("成功取得字幕軌，但內容為空。")

    return parsed_lines

# 前端介面
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
