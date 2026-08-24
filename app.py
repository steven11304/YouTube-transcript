import streamlit as st
import re
import html
import requests
import xml.etree.ElementTree as ET

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("支援自動辨識字幕與多國語言，一鍵輸出純文字檔")

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

def fetch_transcript_fallback(video_id: str):
    """備用方案：直接從 YouTube 網頁端抓取 timedtext 字幕軌"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"
    }
    res = requests.get(f"https://www.youtube.com/watch?v={video_id}", headers=headers, timeout=10)
    
    caption_match = re.search(r'"captionTracks":\[(.*?)\]', res.text)
    if not caption_match:
        raise Exception("該影片未提供任何字幕或後台逐字稿。")
    
    # 提取第一個 caption 軌道的 baseUrl
    url_match = re.search(r'"baseUrl":"(.*?)"', caption_match.group(1))
    if not url_match:
        raise Exception("無法取得字幕下載網址。")
        
    transcript_url = url_match.group(1).replace("\\u0026", "&")
    xml_res = requests.get(transcript_url, headers=headers, timeout=10)
    
    root = ET.fromstring(xml_res.text)
    raw_data = []
    for elem in root.findall('text'):
        start = float(elem.attrib.get('start', 0))
        text = html.unescape(elem.text or '')
        raw_data.append({'start': start, 'text': text})
    return raw_data

def get_transcript_safe(video_id: str):
    """整合套件與備用解析的多重抓取策略"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        # 策略 1：嘗試官方套件標準靜態調用
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            try:
                return YouTubeTranscriptApi.get_transcript(
                    video_id, 
                    languages=['zh-TW', 'zh-CN', 'zh', 'zh-Hant', 'zh-Hans', 'en']
                )
            except Exception:
                return YouTubeTranscriptApi.get_transcript(video_id)
        # 策略 2：嘗試實例化調用
        api_instance = YouTubeTranscriptApi()
        if hasattr(api_instance, 'get_transcript'):
            return api_instance.get_transcript(video_id)
    except Exception:
        pass
    
    # 策略 3：若套件調用失敗，直接走內建網頁解析
    return fetch_transcript_fallback(video_id)

url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在向 YouTube 伺服器請求逐字稿資料流..."):
                try:
                    raw_data = get_transcript_safe(video_id)
                    
                    output_lines = [
                        f"[{format_time(item['start'])}] {item['text'].replace(chr(10), ' ').strip()}" 
                        for item in raw_data if item['text'].strip()
                    ]
                    full_text = "\n".join(output_lines)
                    
                    st.success("提取成功！")
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
