import streamlit as st
import os
import tempfile
import yt_dlp
from google import genai
from google.genai import types

st.set_page_config(page_title="YouTube 逐字稿 AI 轉錄器", page_icon="🎙️")
st.title("YouTube 逐字稿 AI 轉錄器")
st.caption("透過 Gemini 原生音訊理解引擎，自動解析音軌並轉錄精確時間軸")

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
    """下載 YouTube 輕量音訊流（m4a 格式，無需安裝 ffmpeg）"""
    out_path = os.path.join(temp_dir, 'audio.%(ext)s')
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': out_path,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    for f in os.listdir(temp_dir):
        if f.startswith('audio.'):
            return os.path.join(temp_dir, f)
    raise Exception("無法成功提取影片音訊流。")

def transcribe_audio_with_gemini(api_key: str, audio_path: str, model_name: str) -> str:
    """將音訊上傳至 Google Files API 並調用模型聽寫逐字稿"""
    client = genai.Client(api_key=api_key)
    uploaded_file = None

    try:
        # 上傳音訊檔案至 Gemini 檔案庫
        uploaded_file = client.files.upload(file=audio_path)

        prompt = """
        請將這段音訊內容完整轉錄為帶有時間軸的逐字稿。

        格式規範：
        1. 每一行開頭必須標註精確時間戳記，格式為 [MM:SS] 或 [HH:MM:SS]。
        2. 時間戳記後方接逐字內容，保持講者原話與標點符號。
        3. 僅輸出逐字稿本體，不要輸出任何開場白、問候語或 Markdown 解釋。
        """

        response = client.models.generate_content(
            model=model_name,
            contents=[uploaded_file, prompt]
        )
        return response.text

    finally:
        # 清理雲端暫存音訊檔
        if uploaded_file and hasattr(uploaded_file, 'name'):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

# 2. 前端介面
url_input = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url_input:
    if not api_key_to_use:
        st.warning("⚠️ 請先在左側側邊欄輸入你的 Gemini API Key（以 AIza 開頭）。")
    else:
        if st.button("開始 AI 語音轉錄", type="primary"):
            progress_status = st.empty()
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    progress_status.info("⏳ 1/3 正在串流下載影片音訊（極速 m4a 格式）...")
                    audio_file_path = download_audio(url_input.strip(), tmpdir)

                    progress_status.info(f"⏳ 2/3 正在將音訊上傳至 Gemini 並由 {selected_model} 轉錄中...")
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
