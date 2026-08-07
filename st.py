import sys
import os
import streamlit as st
import time
import cv2
from PIL import Image, ImageDraw
from streamlit_cropper import st_cropper

# Fix path cho Streamlit có thể gọi thư mục core/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core._1_download import download_video_metadata
from core._2_asr import run_asr
from core._3_translate import run_translate
from core._4_dubbing import run_dubbing

st.set_page_config(page_title="VideoLingo - Tool Việt Hóa Video", layout="wide")

st.title("🎬 VideoLingo - Trợ lý Việt Hóa Video")
st.markdown("---")

# Initialize session states
if 'metadata' not in st.session_state:
    st.session_state.metadata = None
if 'video_path' not in st.session_state:
    st.session_state.video_path = None
if 'preview_frame' not in st.session_state:
    st.session_state.preview_frame = None

st.sidebar.title("⚙️ Cài đặt")
src_language = st.sidebar.selectbox("Ngôn ngữ gốc (của video)", ["English", "Tiếng Trung", "Tiếng Hàn", "Tiếng Nhật", "Tiếng Việt"])
language = st.sidebar.selectbox("Ngôn ngữ đích (Lồng tiếng)", ["Tiếng Việt", "English", "Tiếng Trung"])
asr_method = st.sidebar.selectbox("Phương pháp nhận diện phụ đề", ["Âm thanh (CapCut ASR)", "Hình ảnh (Local OCR)"])

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔑 Cấu hình API Key (Gemini)")
import json
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "config", "apiKeys.json")
current_keys = []
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            current_keys = [item.get("key", "") for item in payload if item.get("provider") == "gemini" and item.get("status") != "invalid"]
    except Exception:
        pass

keys_input = st.sidebar.text_area(
    "Nhập các Gemini API Key (Mỗi key 1 dòng):", 
    value="\n".join(current_keys),
    height=100
)

if st.sidebar.button("Lưu API Keys"):
    lines = [line.strip() for line in keys_input.split('\n') if line.strip()]
    new_payload = []
    for k in lines:
        new_payload.append({
            "key": k,
            "provider": "gemini",
            "status": "valid"
        })
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(new_payload, f, indent=2, ensure_ascii=False)
    st.sidebar.success(f"Đã lưu {len(lines)} API Keys!")
    
st.sidebar.markdown("---")

url_input = st.text_input("Nhập URL Video (YouTube, TikTok, Facebook...):")

if st.button("Bước 1: Tải & Phân tích Video"):
    if not url_input:
        st.warning("Vui lòng nhập URL Video!")
    else:
        with st.spinner("Đang tải dữ liệu metadata..."):
            try:
                metadata = download_video_metadata(url_input)
                st.session_state.metadata = metadata
                st.session_state.video_path = metadata.get('video_path')
                
                # Extract one frame for preview
                if st.session_state.video_path and os.path.exists(st.session_state.video_path):
                    cap = cv2.VideoCapture(st.session_state.video_path)
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    # Read frame at 50%
                    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
                    ret, frame = cap.read()
                    if ret:
                        # Convert to RGB
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        st.session_state.preview_frame = frame
                    cap.release()
                    
                st.success("Tải video thành công! Bạn có thể xem trước và cấu hình ở bên dưới.")
            except Exception as e:
                st.error(f"Lỗi tải video: {e}")

# If we have downloaded video, show Step 2
if st.session_state.video_path:
    st.markdown("### Cấu hình & Xem trước")
    
    crop_coords_str = ""
    
    if "OCR" in asr_method:
        st.info("Kéo khung chữ nhật màu đỏ trên ảnh để chọn vùng chứa phụ đề (chỉ dùng cho OCR).")
        
        if st.session_state.preview_frame is not None:
            img = Image.fromarray(st.session_state.preview_frame)
            w, h = img.size
            
            # Use streamlit-cropper to get the bounding box interactively
            rect = st_cropper(
                img, 
                realtime_update=True, 
                box_color='red', 
                return_type='box',
                aspect_ratio=None
            )
            
            if rect:
                x_min = max(0.0, rect['left'] / w)
                x_max = min(1.0, (rect['left'] + rect['width']) / w)
                y_min = max(0.0, rect['top'] / h)
                y_max = min(1.0, (rect['top'] + rect['height']) / h)
                
                crop_coords_str = f"{y_min:.4f},{y_max:.4f},{x_min:.4f},{x_max:.4f}"
                st.write(f"Tọa độ cắt hiện tại: `{crop_coords_str}`")
        else:
            st.warning("Không thể trích xuất khung hình preview từ video.")
    else:
        # Nếu dùng ASR thường, có thể show thumbnail hoặc preview không có khung OCR
        if st.session_state.preview_frame is not None:
            st.image(st.session_state.preview_frame, caption="Khung hình ngẫu nhiên từ video", use_container_width=True)
                
    st.markdown("### Bước 2: Bắt đầu Việt Hóa")
    if st.button("Chạy ASR & Lồng tiếng", type="primary"):
        video_path = st.session_state.video_path
        with st.spinner("Đang nhận diện phụ đề..."):
            try:
                srt_path = run_asr(video_path, src_language, language, asr_method, crop_coords_str)
                st.success("Nhận diện phụ đề thành công!")
            except Exception as e:
                st.error(f"Lỗi ASR: {e}")
                st.stop()
                
        with st.spinner("Đang dịch phụ đề (nếu cần)..."):
            try:
                translated_srt = run_translate(srt_path, src_language, language)
                if translated_srt and os.path.exists(translated_srt):
                    srt_path = translated_srt
                    st.success("Dịch phụ đề thành công!")
            except Exception as e:
                st.warning(f"Lỗi Dịch phụ đề (Vẫn tiếp tục lồng tiếng bằng bản gốc): {e}")

        with st.spinner("Đang tổng hợp giọng nói và lồng tiếng (TTS & Dubbing)..."):
            try:
                output_path = os.path.join(os.path.dirname(video_path), "output_dubbed.mp4")
                final_video = run_dubbing(video_path, srt_path, output_path)
                st.success("Ghép nối âm thanh và video thành công!")
                if os.path.exists(final_video):
                    st.video(final_video)
                st.balloons()
            except Exception as e:
                st.error(f"Lỗi Dubbing: {e}")
