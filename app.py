import streamlit as st
import re
import html
import requests
import json
import yt_dlp

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("直連 YouTube 逐字稿資料庫，支援直播重播、長影片與自動辨識字幕")

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
    """利用 yt-dlp 僅提取字幕/逐字稿資料，徹底忽略視訊格式驗證"""
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['all'],
        'quiet': True,
        'no_warnings': True,
        # 關鍵配置：略過影片格式檢查，避免直播/串流報錯
        'ignore_no_formats_error': True,
        'allow_unplayable_formats': True,
        'format': '*',
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        
        # 整合人工字幕軌與系統自動語音辨識軌
        subs = info.get('subtitles') or {}
        auto_subs = info.get('automatic_captions') or {}
        all_subs = {**auto_subs, **subs}

        if not all_subs:
            raise Exception("YouTube 伺服器未提供此影片的字幕資料（可能尚未完成語音辨識或已停用）。")

        # 優先篩選中文或英文軌道
        target_lang = None
        for lang in ['zh-TW', 'zh-CN', 'zh', 'zh-Hant', 'zh-Hans', 'zh-HK', 'en']:
            if lang in all_subs:
                target_lang = lang
                break
        
        if not target_lang:
            target_lang = next(iter(all_subs.keys()))

        formats = all_subs[target_lang]
        
        # 優先獲取 json3 格式，其次選擇 vtt / srv
        target_url = None
        for fmt in formats:
            if fmt.get('ext') == 'json3':
                target_url = fmt.get('url')
                break
        if not target_url:
            target_url = formats[0].get('url')

        # 下載並解析字幕資料流
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(target_url, headers=headers, timeout=20)
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
            # VTT / XML 格式備用解析
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
            raise Exception("成功取得字幕軌，但內容解析為空。")

        return lines

# 前端輸入介面
url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在向 YouTube 伺服器提取逐字稿資料流..."):
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
