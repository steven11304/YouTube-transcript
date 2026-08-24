import streamlit as st
import os
import tempfile
import requests
import re
from google import genai
from google.genai import types

st.set_page_config(page_title="YouTube 逐字稿 AI 轉錄器", page_icon="🎙️")
st.title("YouTube 逐字稿 AI 轉錄器")
st.caption("透過音訊橋接通道與 Gemini AI 語音理解引擎進行精確轉錄")

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

def download_audio_via_bridge(video_url: str, temp_dir: str) -> str:
    """透過雲端音訊橋接 API 下載音訊，避開 AWS 機房 403 阻擋"""
    vid = extract_video_id(video_url)
    if not vid:
        raise Exception("無效的 YouTube 網址。")

    target_audio_path = os.path.join(temp_dir, f"{vid}.mp3")

    # 橋接節點輪詢
    bridge_apis = [
        f"https://api.cobalt.tools/",
        f"https://cobalt-api.kwiatekm.com/",
        f"https://api.wuk.sh/"
    ]

    download_url = None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "url": video_url,
        "downloadMode": "audio",
        "audioFormat": "mp3"
    }

    for endpoint in bridge_apis:
        try:
            r = requests.post(endpoint, json=payload, headers=headers, timeout=12)
            if r.status_code == 200:
                res_data = r.json()
                download_url = res_data.get("url")
                if download_url:
                    break
        except Exception:
            continue

    if not download_url:
        raise Exception("雲端音訊橋接伺服器暫時繁忙，請稍後重試或改在電腦本機執行。")

    # 下載音訊串流至暫存檔案
    audio_res = requests.get(download_url, stream=True, timeout=60)
    if audio_res.status_code != 200:
        raise Exception("取得音訊資料流失敗。")

    with open(target_audio_path, 'wb') as f:
        for chunk in audio_res.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    return target_audio_path

def transcribe_audio_with_gemini(api_key: str, audio_path: str, model_name: str) -> str:
    """上傳至 Gemini 檔案庫並生成帶時間軸逐字稿"""
    client = genai.Client(api_key=api_key)
    uploaded_file = None

    try:
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
                    progress_status.info("⏳ 1/3 正在透過橋接伺服器安全串流音訊...")
                    audio_file_path = download_audio_via_bridge(url_input.strip(), tmpdir)

                    progress_status.info(f"⏳ 2/3 正在由 {selected_model} 進行語音聽寫與時間軸對齊...")
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
