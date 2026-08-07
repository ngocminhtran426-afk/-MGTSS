import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from libs.capcut_asr.cli import process_video
from utils.decorator import except_handler
from utils.config_utils import load_key

@except_handler(retry=2, delay=5)
def run_asr(video_path: str, src_language: str = "English", dst_language: str = "Tiếng Việt", asr_method: str = "Âm thanh (CapCut ASR)", crop_coords: str = "0.75,1.0,0.0,1.0"):
    """
    Chạy nhận diện giọng nói sử dụng Capcut ASR (qua libs cũ) hoặc OCR.
    """
    print(f"Bắt đầu ASR cho video: {video_path}")
    
    try:
        srt_path = os.path.splitext(video_path)[0] + ".srt"
        
        if "OCR" in asr_method:
            import subprocess
            print("Đang chạy nhận diện phụ đề qua hình ảnh (OCR)...")
            
            ocr_lang_map = {
                "English": "en",
                "Tiếng Trung": "ch_sim,en",
                "Tiếng Hàn": "ko,en",
                "Tiếng Nhật": "ja,en",
                "Tiếng Việt": "vi,en"
            }
            ocr_lang = ocr_lang_map.get(src_language, "vi,en")
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs", "ocr", "fast_ocr.py")
            
            # Start process without showing window on Windows
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            cmd = [sys.executable, script_path, "--video", video_path, "--out_srt", srt_path, "--langs", ocr_lang]
            if crop_coords and crop_coords.strip():
                cmd.extend(["--crop", crop_coords.strip()])
                
            print("Đang thực thi OCR, vui lòng xem tiến trình trong cửa sổ dòng lệnh (CMD)...")
            result = subprocess.run(cmd, startupinfo=startupinfo)
            
            if result.returncode != 0:
                raise Exception(f"Lỗi OCR (Mã lỗi: {result.returncode})")
        else:
            print("Đang chạy nhận diện giọng nói qua âm thanh (CapCut ASR)...")
            capcut_lang_map = {
                "English": "Tiếng Anh",
                "Tiếng Trung": "Trung Quốc",
                "Tiếng Hàn": "Hàn Quốc",
                "Tiếng Nhật": "Nhật Bản",
                "Tiếng Việt": "Tiếng Việt"
            }
            capcut_lang = capcut_lang_map.get(src_language, "Tiếng Anh")
            
            process_video(video_path, capcut_lang)
            
        if os.path.exists(srt_path):
            print(f"Nhận diện thành công: {srt_path}")
            return srt_path
        else:
            raise Exception("File SRT không được tạo ra.")
    except Exception as e:
        print(f"Lỗi khi chạy trích xuất phụ đề: {e}")
        raise
