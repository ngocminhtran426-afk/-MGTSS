import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from libs.capcut_asr.cli import process_video
from utils.decorator import except_handler, check_file_exists
from utils.config_utils import load_key

@except_handler(retry=2, delay=5)
def run_asr(video_path: str, language: str = "Tiếng Việt"):
    """
    Chạy nhận diện giọng nói sử dụng Capcut ASR (qua libs cũ).
    """
    print(f"Bắt đầu ASR cho video: {video_path}")
    
    # process_video tạo ra file .srt cùng thư mục với video
    try:
        process_video(video_path, language)
        srt_path = os.path.splitext(video_path)[0] + ".srt"
        if os.path.exists(srt_path):
            print(f"ASR thành công: {srt_path}")
            return srt_path
        else:
            raise Exception("File SRT không được tạo ra.")
    except Exception as e:
        print(f"Lỗi khi chạy ASR: {e}")
        raise
