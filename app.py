import streamlit as st
import re
import html
import os
import glob
import tempfile
import yt_dlp

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("透過 yt-dlp 原生通道下載，支援直播重播、長影片與自動辨識字幕")

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

def parse_vtt_file(file_path: str):
    """解析 yt-dlp 下載下來的標準 VTT 字幕檔"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    lines = []
    blocks = re.split(r'\n\s*\n', content)
    last_text = ""

    for block in blocks:
        time_match = re.search(r'(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->', block)
        if time_match:
            h = int(time_match.group(1)[:-1]) if time_match.group(1) else 0
            m = int(time_match.group(2))
            s = int(time_match.group(3))
            total_sec = h * 3600 + m * 60 + s

            raw_lines = block.split('\n')
            text_lines = []
            for l in raw_lines:
                l_strip = l.strip()
                if (
                    '-->' in l 
                    or l_strip.isdigit() 
                    or l_strip.startswith('WEBVTT') 
                    or l_strip.startswith('NOTE') 
                    or l_strip.startswith('Kind:') 
                    or l_strip.startswith('Language:')
                ):
                    continue
                # 清除 VTT 樣式標籤 (如 <c.color...>, </c>, 時間戳標籤)
                clean_l = re.sub(r'<[^>]+>', '', l_strip)
                clean_l = html.unescape(clean_l).strip()
                if clean_l:
                    text_lines.append(clean_l)

            text = " ".join(text_lines).strip()
            # 避免自動字幕常見的連續重複行
            if text and text != last_text:
                lines.append(f"[{format_time(total_sec)}] {text}")
                last_text = text

    return lines

def download_and_extract_subtitles(video_url: str):
    """使用 yt-dlp 內部會話原生下載字幕至臨時目錄"""
    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, '%(id)s.%(ext)s')
        
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['all'],
            'subtitlesformat': 'vtt',
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'ignore_no_formats_error': True,
            'allow_unplayable_formats': True,
            'noplaylist': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 搜尋下載下來的所有 VTT / SRT 字幕檔
        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt")) + glob.glob(os.path.join(tmpdir, "*.srt"))

        if not vtt_files:
            raise Exception("YouTube 伺服器未提供此影片的字幕資料（可能尚未完成語音辨識或已設為私人）。")

        # 優先選擇中文（繁/簡/香港/一般）或英文檔案
        selected_file = None
        for lang_code in ['zh-TW', 'zh-HK', 'zh-CN', 'zh-Hant', 'zh-Hans', 'zh', 'en']:
            for f in vtt_files:
                if f".{lang_code}." in os.path.basename(f).lower() or f".{lang_code.lower()}." in os.path.basename(f).lower():
                    selected_file = f
                    break
            if selected_file:
                break

        # 若無指定語言則選取第一個檔案
        if not selected_file:
            selected_file = vtt_files[0]

        parsed_lines = parse_vtt_file(selected_file)

        if not parsed_lines:
            raise Exception("字幕檔案已下載，但內容為空。")

        return parsed_lines

# 前端介面
url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在透過 yt-dlp 原生通道提取逐字稿資料流..."):
                try:
                    output_lines = download_and_extract_subtitles(url)
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
