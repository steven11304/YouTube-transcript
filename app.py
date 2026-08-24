import streamlit as st
import os
import tempfile
import yt_dlp
from google import genai
from google.genai import types

st.set_page_config(page_title="YouTube 逐字稿 AI 轉錄器", page_icon="🎙️")
st.title("YouTube 逐字稿 AI 轉錄器")
st.caption("透過行動端協定提取音訊並交由 Gemini 原生模型轉錄")

# 1. API Key 與模型設定
default_api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ 設定")
    user_api_key = st.text_input(
        "Gemini API Key", 
        value=default_api_key, 
        type="password", 
        placeholder="AIzaSy...",
        help="請貼上 Google AI Studio 取得的 API Key"
    )
    
    selected_model = st.selectbox(
        "選擇 Gemini 模型",
        options=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0
    )

api_key_to_use = user_api_key.strip() if user_api_key else default_api_key.strip()

def download_audio(video_url: str, temp_dir: str) -> str:
    """透過 iOS / Android 行動端協定下載音訊，避開機房 403 限制"""
    out_path = os.path.join(temp_dir, 'audio.%(ext)s')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_path,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.ios.youtube/19.29.1 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    for f in os.listdir(temp_dir):
        if f.startswith('audio.'):
            return os.path.join(temp_dir, f)
    raise Exception("無法成功提取影片音訊檔。")

def transcribe_audio_with_gemini(api_key: str, audio_path: str, model_name: str) -> str:
    """將音訊傳入 Gemini 進行高精確度時間軸逐字稿轉錄"""
    client = genai.Client(api_key=api_key)
    uploaded_file = None

    try:
        # 上傳音訊檔案至 Gemini 暫存庫
        uploaded_file = client.files.upload(file=audio_path)

        prompt = """
        請將這段音訊內容完整轉錄為帶有時間軸的逐字稿。

        格式規範：
        1. 每一行開頭必須標註精確時間戳記，格式為 [MM:SS] 或 [HH:MM:SS]。
        2. 時間戳記後方接逐字內容，保持講者原話與標點符號。
        3. 僅輸出逐字稿本體，嚴禁輸出任何開場白、問候語或 Markdown 解釋。
        """

        response = client.models.generate_content(
            model=model_name,
            contents=[uploaded_file, prompt]
        )
        return response.text

    finally:
        # 轉錄完成後刪除暫存檔
        if uploaded_file and hasattr(uploaded_file, 'name'):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

# 2. 前端介面
url_input = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url_input:
    if not api_key_to_use:
        st.warning("⚠️ 請先在左側側邊欄輸入你的 Gemini API Key。")
    else:
        if st.button("開始 AI 語音轉錄", type="primary"):
            progress_status = st.empty()
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    progress_status.info("⏳ 1/3 正在串流下載影片音訊...")
                    audio_file_path = download_audio(url_input.strip(), tmpdir)

                    progress_status.info(f"⏳ 2/3 正在由 {selected_model} 進行音訊辨識與時間軸轉錄...")
                    transcript = transcribe_audio_with_gemini(api_key_to_use, audio_file_path, selected_model)

                    progress_status.empty()

                    if not transcript or not transcript.strip():
                        raise Exception("模型未回傳文字，請確認音訊內容是否清晰。")

                    st.success("🎉 轉錄成功！")

                    st.download_button(
                        label="📥 下載 TXT 逐字稿",
                        data=transcript,
                        file_name="transcript.txt",
                        mime="text/plain; charset=utf-8"
                    )

                    with st.expander("預覽逐字稿內容", expanded=True):
                        st.text_area("逐字稿文字", value=transcript, height=450)

            except Exception as e:
                progress_status.empty()
                st.error(f"轉錄失敗：{str(e)}")
