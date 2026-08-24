import streamlit as st
import os
import tempfile
from google import genai
from google.genai import types

st.set_page_config(page_title="YouTube 逐字稿 AI 轉錄器", page_icon="🎙️")
st.title("YouTube 逐字稿 AI 轉錄器")
st.caption("透過 Google Gemini 多模態語音理解引擎，直接生成帶時間軸逐字稿")

# 1. API Key 設定
default_api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ 設定")
    user_api_key = st.text_input(
        "Gemini API Key", 
        value=default_api_key, 
        type="password", 
        placeholder="AIzaSy...",
        help="請至 Google AI Studio 取得 API Key"
    )
    
    selected_model = st.selectbox(
        "選擇 Gemini 模型",
        options=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0
    )

api_key_to_use = user_api_key.strip() if user_api_key else default_api_key.strip()

def transcribe_audio_file(api_key: str, file_path: str, model_name: str) -> str:
    """上傳音訊檔案至 Gemini 暫存庫並轉錄逐字稿"""
    client = genai.Client(api_key=api_key)
    uploaded_file = None

    try:
        uploaded_file = client.files.upload(file=file_path)

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
        if uploaded_file and hasattr(uploaded_file, 'name'):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

# 2. 前端上傳介面
uploaded_audio = st.file_uploader(
    "請拖曳或上傳音訊檔案（支援 MP3, M4A, WAV, MP4, AAC）：", 
    type=["mp3", "m4a", "wav", "mp4", "aac"]
)

if uploaded_audio:
    if not api_key_to_use:
        st.warning("⚠️ 請先在左側側邊欄輸入你的 Gemini API Key。")
    else:
        if st.button("開始 AI 語音轉錄", type="primary"):
            progress_status = st.empty()
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    temp_file_path = os.path.join(tmpdir, uploaded_audio.name)
                    with open(temp_file_path, "wb") as f:
                        f.write(uploaded_audio.getbuffer())

                    progress_status.info(f"⏳ 正在由 {selected_model} 進行音訊分析與時間軸轉錄...")
                    transcript = transcribe_audio_file(api_key_to_use, temp_file_path, selected_model)
                    progress_status.empty()

                    if not transcript or not transcript.strip():
                        raise Exception("模型未回傳文字，請確認音訊內容是否清晰。")

                    st.success("🎉 轉錄成功！")

                    st.download_button(
                        label="📥 下載 TXT 逐字稿",
                        data=transcript,
                        file_name=f"{os.path.splitext(uploaded_audio.name)[0]}_transcript.txt",
                        mime="text/plain; charset=utf-8"
                    )

                    with st.expander("預覽逐字稿內容", expanded=True):
                        st.text_area("逐字稿文字", value=transcript, height=450)

            except Exception as e:
                progress_status.empty()
                st.error(f"轉錄失敗：{str(e)}")
