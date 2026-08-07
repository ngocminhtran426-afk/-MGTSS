import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.decorator import except_handler, check_file_exists

@except_handler(retry=2, delay=2)
def run_tts(text_file: str, output_audio: str):
    """
    Chạy Text-to-Speech (Sử dụng thư viện TTS trong libs).
    """
    print(f"Bắt đầu TTS từ {text_file} ra {output_audio}")
    # TODO: Tích hợp gọi vào libs/VieNeu-TTS-main
    return output_audio
