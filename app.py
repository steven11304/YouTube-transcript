import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="YouTube 逐字稿 AI 轉錄器", page_icon="🎙️")
st.title("YouTube 逐字稿 AI 轉錄器")
st.caption("透過 Google Gemini 多模態影音辨識引擎，直接解析音軌並轉錄精確時間軸")

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
    
    # 提供模型切換選單，避免動態查詢觸發 401 錯誤
    selected_model = st.selectbox(
        "選擇 Gemini 模型",
        options=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0
    )

api_key_to_use = user_api_key.strip() if user_api_key else default_api_key.strip()

def transcribe_youtube_video(api_key: str, video_url: str, model_name: str) -> str:
    # 建立客戶端實例
    client = genai.Client(api_key=api_key)

    prompt = """
    請將這部 YouTube 影片的語音內容完整轉錄為帶有時間軸的逐字稿。

    格式規範：
    1. 每一行開頭必須標註精確時間戳記，格式為 [MM:SS] 或 [HH:MM:SS]。
    2. 時間戳記後方接逐字內容，保持講者原話與標點符號。
    3. 僅輸出逐字稿本體，嚴禁輸出任何開場白、問候語或 Markdown 解釋。
    """

    # 直連多模態解析
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_uri(
                file_uri=video_url,
                mime_type="video/*"
            ),
            prompt
        ]
    )
    return response.text

# 2. 前端介面
url_input = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url_input:
    if not api_key_to_use:
        st.warning("⚠️ 請先在左側側邊欄輸入你的 Gemini API Key（以 AIza 開頭）。")
    else:
        if st.button("開始 AI 語音轉錄", type="primary"):
            with st.spinner(f"正在由 {selected_model} 解析影音資料流（長影片約需 30~90 秒）..."):
                try:
                    transcript = transcribe_youtube_video(api_key_to_use, url_input.strip(), selected_model)

                    if not transcript or not transcript.strip():
                        raise Exception("模型未回傳文字，請確認該影片是否含有可辨識語音。")

                    st.success("轉錄成功！")

                    # 下載 TXT
                    st.download_button(
                        label="📥 下載 TXT 逐字稿",
                        data=transcript,
                        file_name="transcript.txt",
                        mime="text/plain; charset=utf-8"
                    )

                    # 預覽區域
                    with st.expander("預覽逐字稿內容", expanded=True):
                        st.text_area("逐字稿文字", value=transcript, height=450)

                except Exception as e:
                    st.error(f"轉錄失敗：{str(e)}")
