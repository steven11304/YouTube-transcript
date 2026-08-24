import streamlit as st
import re
import html
import requests
import json
import yt_dlp

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("搭載 yt-dlp 核心引擎，支援長影片、直播重播與雲端防阻擋")

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

def get_transcript_via_ytdlp(video_url: str):
    """利用 yt-dlp 提取影片的自動辨識或手動字幕軌"""
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'quiet': True,
        'no_warnings': True,
        # 模擬 iOS / Web 混合客戶端繞過機房阻擋
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'web', 'mweb']
            }
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        
        # 合併人工字幕與自動生成字幕
        subs = info.get('subtitles') or {}
        auto_subs = info.get('automatic_captions') or {}
        all_subs = {**auto_subs, **subs}

        if not all_subs:
            raise Exception("YouTube 伺服器未提供此影片的字幕資料（可能尚未完成語音辨識）。")

        # 優先選擇中文或英文軌道
        target_lang = None
        for lang in ['zh-TW', 'zh-CN', 'zh', 'zh-Hant', 'zh-Hans', 'en']:
            if lang in all_subs:
                target_lang = lang
                break
        
        if not target_lang:
            target_lang = next(iter(all_subs.keys()))

        formats = all_subs[target_lang]
        
        # 優先獲取 json3 格式，其次選擇 vtt
        target_url = None
        for fmt in formats:
            if fmt.get('ext') == 'json3':
                target_url = fmt.get('url')
                break
        if not target_url:
            target_url = formats[0].get('url')

        # 下載並解析字幕資料
        res = requests.get(target_url, timeout=15)
        lines = []

        if target_url.endswith('json3') or res.text.strip().startswith('{'):
            data = res.json()
            for ev in data.get('events', []):
                if 'segs' in ev:
                    start_sec = ev.get('tStartMs', 0) / 1000.0
                    text = "".join([s.get('utf8', '') for s in ev.get('segs', [])]).replace('\n', ' ').strip()
                    if text:
                        lines.append(f"[{format_time(start_sec)}] {text}")
        else:
            # VTT / 純文字回退解析
            vtt_blocks = re.split(r'\n\s*\n', res.text)
            for block in vtt_blocks:
                time_match = re.search(r'(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->', block)
                if time_match:
                    h = int(time_match.group(1)[:-1]) if time_match.group(1) else 0
                    m = int(time_match.group(2))
                    s = int(time_match.group(3))
                    total_sec = h * 3600 + m * 60 + s
                    text_lines = [l for l in block.split('\n') if '-->' not in l and not l.strip().isdigit()]
                    text = " ".join(text_lines)
                    text = re.sub(r'<[^>]+>', '', text)
                    text = html.unescape(text).strip()
                    if text:
                        lines.append(f"[{format_time(total_sec)}] {text}")

        if not lines:
            raise Exception("成功取得字幕軌，但內容為空。")

        return lines

# 前端介面
url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在透過 yt-dlp 核心讀取 YouTube 逐字稿資料流..."):
                try:
                    output_lines = get_transcript_via_ytdlp(url)
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
