import streamlit as st
import re
import html
import requests
import json
import xml.etree.ElementTree as ET
import yt_dlp

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("直連 YouTube 逐字稿資料庫，支援直播重播、長影片與所有字幕格式")

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

def parse_subtitle_content(raw_text: str):
    """全能字幕解析器：相容 JSON3、SRV1、SRV3、TTML、WebVTT 格式"""
    raw_text = raw_text.strip()
    lines = []
    if not raw_text:
        return lines

    # 1. 嘗試 JSON 解析 (json3 格式)
    if raw_text.startswith('{'):
        try:
            data = json.loads(raw_text)
            for ev in data.get('events', []):
                start_sec = ev.get('tStartMs', 0) / 1000.0
                txt_parts = []
                if 'segs' in ev:
                    for s in ev['segs']:
                        if 'utf8' in s:
                            txt_parts.append(s['utf8'])
                elif 'text' in ev:
                    txt_parts.append(str(ev['text']))
                
                text = "".join(txt_parts).replace('\n', ' ').strip()
                if text:
                    lines.append(f"[{format_time(start_sec)}] {text}")
            if lines:
                return lines
        except Exception:
            pass

    # 2. 嘗試 XML 解析 (srv1 / srv3 / ttml / transcript 格式)
    if '<' in raw_text and '>' in raw_text:
        try:
            clean_xml = re.sub(r'&(?!(?:amp|lt|gt|quot|apos);)', '&amp;', raw_text)
            root = ET.fromstring(clean_xml)
            
            # 模式 A: <text start="12.34">內容</text> (srv1)
            for elem in root.findall('.//text'):
                start_sec = float(elem.attrib.get('start', 0))
                text = html.unescape("".join(elem.itertext())).replace('\n', ' ').strip()
                if text:
                    lines.append(f"[{format_time(start_sec)}] {text}")
            if lines:
                return lines

            # 模式 B: <p t="12340"><s>內容</s></p> (srv3 格式)
            for elem in root.findall('.//p'):
                t_val = elem.attrib.get('t') or elem.attrib.get('begin')
                start_sec = 0.0
                if t_val:
                    if t_val.isdigit():
                        start_sec = float(t_val) / 1000.0
                    elif ':' in t_val:
                        parts = t_val.split(':')
                        if len(parts) == 3:
                            start_sec = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                        elif len(parts) == 2:
                            start_sec = float(parts[0])*60 + float(parts[1])
                
                text = html.unescape("".join(elem.itertext())).replace('\n', ' ').strip()
                if text:
                    lines.append(f"[{format_time(start_sec)}] {text}")
            if lines:
                return lines
        except Exception:
            pass

        # 模式 C: 正規表示式提取 XML 標籤內容
        matches_text = re.findall(r'<text[^>]*start="([\d\.]+)"[^>]*>(.*?)</text>', raw_text, re.DOTALL)
        if matches_text:
            for start_str, txt in matches_text:
                t = html.unescape(re.sub(r'<[^>]+>', '', txt)).replace('\n', ' ').strip()
                if t:
                    lines.append(f"[{format_time(float(start_str))}] {t}")
            if lines:
                return lines
        
        matches_p = re.findall(r'<p[^>]*t="(\d+)"[^>]*>(.*?)</p>', raw_text, re.DOTALL)
        if matches_p:
            for t_ms, txt in matches_p:
                t = html.unescape(re.sub(r'<[^>]+>', '', txt)).replace('\n', ' ').strip()
                if t:
                    lines.append(f"[{format_time(float(t_ms)/1000.0)}] {t}")
            if lines:
                return lines

    # 3. 嘗試 WebVTT / SRT 格式解析
    if '-->' in raw_text:
        vtt_blocks = re.split(r'\n\s*\n', raw_text)
        for block in vtt_blocks:
            time_match = re.search(r'(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->', block)
            if time_match:
                h = int(time_match.group(1)[:-1]) if time_match.group(1) else 0
                m = int(time_match.group(2))
                s = int(time_match.group(3))
                total_sec = h * 3600 + m * 60 + s
                text_lines = [
                    l for l in block.split('\n') 
                    if '-->' not in l and not l.strip().isdigit() and not l.startswith('WEBVTT') and not l.startswith('NOTE')
                ]
                text = " ".join(text_lines)
                text = re.sub(r'<[^>]+>', '', text)
                text = html.unescape(text).strip()
                if text:
                    lines.append(f"[{format_time(total_sec)}] {text}")
        if lines:
            return lines

    return lines

def get_transcript_via_ytdlp(video_url: str):
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['all'],
        'quiet': True,
        'no_warnings': True,
        'ignore_no_formats_error': True,
        'allow_unplayable_formats': True,
        'format': '*',
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        
        subs = info.get('subtitles') or {}
        auto_subs = info.get('automatic_captions') or {}
        all_subs = {**auto_subs, **subs}

        if not all_subs:
            raise Exception("YouTube 伺服器未提供此影片的字幕資料（可能尚未完成語音辨識或已停用）。")

        # 優先尋找中文或英文字幕軌
        ordered_langs = []
        for lang in all_subs.keys():
            l_lower = lang.lower()
            if any(k in l_lower for k in ['zh', 'tw', 'cn', 'hk', 'hant', 'hans']):
                ordered_langs.append(lang)
        for lang in all_subs.keys():
            if lang.lower().startswith('en') and lang not in ordered_langs:
                ordered_langs.append(lang)
        for lang in all_subs.keys():
            if lang not in ordered_langs:
                ordered_langs.append(lang)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # 逐一嘗試各語言軌道與格式，直到解析成功
        for lang in ordered_langs:
            formats = all_subs[lang]
            for fmt in formats:
                sub_url = fmt.get('url')
                if not sub_url:
                    continue
                try:
                    res = requests.get(sub_url, headers=headers, timeout=20)
                    if res.status_code == 200 and res.text:
                        parsed = parse_subtitle_content(res.text)
                        if parsed:
                            return parsed
                except Exception:
                    continue

        raise Exception("已獲取字幕軌下載連結，但所有格式解析皆未回傳有效文字。")

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
