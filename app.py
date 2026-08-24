import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="YouTube 逐字稿 AI 轉錄器", page_icon="🎙️")
st.title("YouTube 逐字稿 AI 轉錄器")
st.caption("透過 Google Gemini 多模態影音辨識引擎，直接解析音軌並轉錄精確時間軸")

# 1. API Key 設定（優先讀取 Streamlit Secrets，亦可於介面手動輸入）
default_api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 設定")
    user_api_key = st.text_input(
        "Gemini API Key", 
        value=default_api_key, 
        type="password", 
        help="可至 Google AI Studio 免費建立 API 金鑰"
    )
    api_key_to_use = user_api_key if user_api_key else default_api_key

def get_active_model(client: genai.Client) -> str:
    """自動偵測目前帳號支援且在線的最新 Flash 生成端點"""
    models = [
        m.name for m in client.models.list()
        if "generateContent" in (m.supported_actions or []) and "flash" in m.name.lower()
    ]
    if not models:
        # 若無 flash 系列，則選取任意支援內容生成的端點
        models = [m.name for m in client.models.list() if "generateContent" in (m.supported_actions or [])]
    
    if not models:
        raise Exception("目前的 API Key 無可用的 Gemini 生成模型端點。")
    
    return models[-1]

def transcribe_youtube_video(client: genai.Client, video_url: str, model_name: str) -> str:
    prompt = """
    請將這部 YouTube 影片的語音內容完整轉錄為帶有時間軸的逐字稿。

    格式規範：
    1. 每一行開頭必須標註精確時間戳記，格式為 [MM:SS] 或 [HH:MM:SS]。
    2. 時間戳記後方接逐字內容，保持講者原話與適當標點符號。
    3. 僅輸出逐字稿本體，嚴禁輸出任何開場白、問候語或 Markdown 解釋說明。
    """

    # 將 YouTube 網址作為影音部件直接傳入
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
        st.warning("⚠️ 請先在左側側邊欄輸入你的 Gemini API Key 才能執行轉錄。")
    else:
        if st.button("開始 AI 語音轉錄", type="primary"):
            with st.spinner("正在由 Google 雲端多模態模型辨識音訊（長影片約需 30~90 秒）..."):
                try:
                    client = genai.Client(api_key=api_key_to_use)
                    active_model = get_active_model(client)
                    
                    st.info(f"📡 已連線至雲端端點：`{active_model}`")
                    transcript = transcribe_youtube_video(client, url_input, active_model)

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
