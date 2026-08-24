import streamlit as st
import re
import html
import requests
import json
import xml.etree.ElementTree as ET

st.set_page_config(page_title="YouTube 逐字稿下載器", page_icon="📝")
st.title("YouTube 逐字稿 TXT 下載器")
st.caption("具備雲端防阻擋節點輪詢，支援自動辨識與直播重播逐字稿")

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

def parse_vtt_or_xml(content: str):
    """解析 VTT 或 XML 格式字幕"""
    lines = []
    content = content.strip()
    
    # 1. XML 格式解析
    if content.startswith("<") or "<text" in content:
        try:
            root = ET.fromstring(content)
            for elem in root.findall(".//text"):
                start_sec = float(elem.attrib.get("start", 0))
                text = html.unescape(elem.text or "").replace("\n", " ").strip()
                if text:
                    lines.append(f"[{format_time(start_sec)}] {text}")
            if lines:
                return lines
        except Exception:
            pass

    # 2. VTT 格式解析
    vtt_blocks = re.split(r'\n\s*\n', content)
    for block in vtt_blocks:
        time_match = re.search(r'(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->', block)
        if time_match:
            # 取得時間
            h = int(time_match.group(1)[:-1]) if time_match.group(1) else 0
            m = int(time_match.group(2))
            s = int(time_match.group(3))
            total_sec = h * 3600 + m * 60 + s
            
            # 清理字幕文字（移除時間軸行與 HTML 標籤）
            text_lines = [l for l in block.split('\n') if '-->' not in l and not l.strip().isdigit()]
            text = " ".join(text_lines)
            text = re.sub(r'<[^>]+>', '', text)
            text = html.unescape(text).strip()
            if text:
                lines.append(f"[{format_time(total_sec)}] {text}")
                
    return lines

def fetch_from_invidious(video_id: str):
    """透過公共 Invidious 節點繞過 YouTube 機房 IP 限制"""
    instances = [
        "https://inv.tux.pizza",
        "https://invidious.nerdvpn.de",
        "https://yt.artemislena.eu",
        "https://invidious.lunar.icu",
        "https://inv.nadeko.net"
    ]
    
    for base_node in instances:
        try:
            api_url = f"{base_node}/api/v1/videos/{video_id}"
            res = requests.get(api_url, timeout=8)
            if res.status_code != 200:
                continue
                
            data = res.json()
            captions = data.get("captions", [])
            if not captions:
                continue

            # 優先篩選中文或英文
            target_cap = None
            for c in captions:
                lang = c.get("languageCode", "").lower()
                if any(k in lang for k in ["zh", "tw", "cn", "hk", "en"]):
                    target_cap = c
                    break
            if not target_cap:
                target_cap = captions[0]

            cap_url = target_cap.get("url")
            if not cap_url:
                continue
            if cap_url.startswith("/"):
                cap_url = f"{base_node}{cap_url}"

            cap_res = requests.get(cap_url, timeout=8)
            if cap_res.status_code == 200 and cap_res.text:
                parsed = parse_vtt_or_xml(cap_res.text)
                if parsed:
                    return parsed
        except Exception:
            continue
            
    return None

def fetch_transcript_pipeline(video_id: str):
    # 策略 1：先嘗試從第三方公共節點繞過 IP 封鎖獲取
    lines = fetch_from_invidious(video_id)
    if lines:
        return lines

    # 策略 2：直接嘗試 YouTube 網頁端抓取（備用）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"
    }
    try:
        page_res = requests.get(f"https://www.youtube.com/watch?v={video_id}", headers=headers, timeout=10)
        match = re.search(r'"baseUrl":"(https:\/\/www\.youtube\.com\/api\/timedtext[^"]+)"', page_res.text)
        if match:
            raw_url = match.group(1).replace("\\u0026", "&")
            xml_res = requests.get(raw_url, headers=headers, timeout=10)
            parsed = parse_vtt_or_xml(xml_res.text)
            if parsed:
                return parsed
    except Exception:
        pass

    raise Exception("無法從伺服器取得逐字稿。該影片可能尚未完成語音辨識、設為私人，或所有雲端公共節點暫時繁忙。")

# 前端介面
url = st.text_input("請貼上 YouTube 影片網址：", placeholder="https://www.youtube.com/watch?v=...")

if url:
    video_id = extract_video_id(url)
    if not video_id:
        st.error("無法解析此網址，請確認是否為正確的 YouTube 連結。")
    else:
        if st.button("開始提取逐字稿", type="primary"):
            with st.spinner("正在透過雲端節點請求逐字稿資料流..."):
                try:
                    output_lines = fetch_transcript_pipeline(video_id)
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
