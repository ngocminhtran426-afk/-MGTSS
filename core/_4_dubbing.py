import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.decorator import except_handler, check_file_exists

@except_handler(retry=2, delay=2)
def run_dubbing(video_path: str, srt_path: str, output_path: str):
    """
    Chạy Dubbing - Ghép file âm thanh mới vào video.
    """
    print(f"Bắt đầu Dubbing video {video_path} với srt {srt_path}")
    from libs.capcut_dubbing.capcut_dubber import process_srt_to_video
    
    # Using defaults for now, can be parameterized later
    process_srt_to_video(
        srt_path=srt_path,
        video_path=video_path,
        output_path=output_path,
        max_workers=4, 
        tts_method="CapCut API",
    )
    
    return output_path
