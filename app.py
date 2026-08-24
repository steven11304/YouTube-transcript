import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
import re

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")

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

url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在向 YouTube 伺服器請求逐字稿資料流..."):
                try:
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    
                    try:
                        transcript = transcript_list.find_transcript(['zh-TW', 'zh-CN', 'zh', 'zh-Hant', 'zh-Hans', 'en'])
                    except Exception:
                        transcript = next(iter(transcript_list))
                    
                    raw_data = transcript.fetch()
                    
                    output_lines = [f"[{format_time(item['start'])}] {item['text'].replace('\n', ' ')}" for item in raw_data]
                    full_text = "\n".join(output_lines)
                    
                    st.success("提取成功！")
                    st.download_button(
                        label="📥 下載 TXT 逐字稿",
                        data=full_text,
                        file_name=f"{video_id}_transcript.txt",
                        mime="text/plain"
                    )
                    
                    with st.expander("預覽逐字稿內容"):
                        st.text("\n".join(output_lines[:50]))
                        
                except Exception as e:
                    st.error(f"提取失敗：該影片可能尚未完成語音辨識或停用了逐字稿功能。（{str(e)}）")
