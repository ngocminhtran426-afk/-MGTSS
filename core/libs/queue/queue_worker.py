import os
import sys
import time
import json
import uuid
import subprocess
from datetime import datetime

# Đảm bảo có thể import các module hiện tại
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'viet_hoa_video')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'capcut_dubbing')))

from modules.queue.excel_manager import ExcelQueueManager
from modules.viet_hoa_video.viethoa_preprocess import run_viethoa_preprocess
from modules.capcut_dubbing.capcut_dubber import process_srt_to_video

# Đường dẫn cài đặt
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
DOWNLOAD_DIR = os.path.join(STORAGE_DIR, 'downloads')
TEMP_DIR = os.path.join(STORAGE_DIR, 'temp')

EXCEL_QUEUE_PATH = os.path.join(BASE_DIR, 'DanhSach_Video.xlsx')

def load_config():
    config_path = os.path.join(STORAGE_DIR, 'queue_config.json')
    if not os.path.exists(config_path):
        default_cfg = {
            "gemini_api_key": "",
            "tts_api_key": "",
            "vieneu_api_key": ""
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_cfg, f, indent=4)
        return default_cfg
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def download_video(url, output_folder, cookies_browser=None):
    """Sử dụng yt-dlp để tải video"""
    print(f"[DOWNLOAD] Đang tải video từ {url}...")
    import shlex
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--write-subs", "--write-auto-subs", "--sub-langs", "en,vi,zh",
        "--cookies-from-browser", "chrome",
        "--file-access-retries", "20",
        "--windows-filenames",
        "--output", os.path.join(output_folder, "%(title)s.%(ext)s"),
        url
    ]
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"[DOWNLOAD LỖI] {e}. Đang thử khôi phục file tải dở...")
    
    # Dù thành công hay lỗi (như WinError 32), vẫn tìm file mp4 hoặc .temp.mp4
    import time
    time.sleep(2) # Đợi một chút để Windows nhả file
    
    # 1. Tìm file mp4 chính thức
    for f in os.listdir(output_folder):
        if f.endswith(".mp4") and not f.endswith(".temp.mp4"):
            return os.path.join(output_folder, f)
            
    # 2. Nếu không có mp4, tìm file .temp.mp4 và đổi tên
    for f in os.listdir(output_folder):
        if f.endswith(".temp.mp4"):
            temp_path = os.path.join(output_folder, f)
            final_path = temp_path.replace(".temp.mp4", ".mp4")
            try:
                # Cố gắng đổi tên nhiều lần
                for _ in range(5):
                    try:
                        os.rename(temp_path, final_path)
                        print(f"[DOWNLOAD] Đã khôi phục và đổi tên file thành công: {final_path}")
                        return final_path
                    except OSError:
                        time.sleep(2)
                # Nếu vẫn không đổi tên được, dùng luôn file temp
                print(f"[DOWNLOAD] Không thể đổi tên file temp, dùng luôn: {temp_path}")
                return temp_path
            except Exception as ex:
                print(f"[DOWNLOAD] Lỗi khi xử lý file temp: {ex}")
                return temp_path
                
    return None

def process_task(task, manager, config):
    row_idx = task["row_index"]
    url = task["link"]
    
    print(f"[INFO] Bắt đầu xử lý dòng {row_idx}: {url}")
    manager.update_status(row_idx, "Đang tải")
    
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:4]
    output_dir = os.path.join(DOWNLOAD_DIR, f"queue_{session_id}")
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # 1. Download
        video_path = download_video(url, output_dir)
        if not video_path:
            raise RuntimeError("Tải video thất bại (yt-dlp lỗi hoặc không tìm thấy file mp4).")
            
        video_name = os.path.basename(video_path)
        base_name = os.path.splitext(video_name)[0]
        
        # Cập nhật tạm thư mục output
        manager.update_outputs(row_idx, title=base_name, out_dir=out_folder, video=video_path)

        # 2. Đang nhận diện & Dịch (Việt hoá)
        manager.update_status(row_idx, "Đang nhận diện & Dịch")
        viethoa_out_dir = os.path.join(out_folder, f"{base_name}_viet_hoa")
        
        viethoa_result = run_viethoa_preprocess(
            source_url=url,
            output_dir=viethoa_out_dir,
            gemini_api_key=config.get("gemini_api_key", ""),
            channel_name=task.get("source", ""),
            extra_prompt="Dịch theo văn phong review phim.",
            progress_callback=lambda msg: print(f"[VIET_HOA] {msg}")
        )
        
        translated_title = viethoa_result.get("translated_title", base_name)
        srt_path = viethoa_result.get("srt_viet_path", "")
        desc_path = os.path.join(viethoa_out_dir, "mo_ta_viet.txt")
        
        if not srt_path or not os.path.exists(srt_path):
            # Fallback nếu viethoa_preprocess không trả về srt (có thể do thiếu whisper)
            raise RuntimeError("Không tạo được file SRT tiếng Việt.")

        # Cập nhật SRT và Title
        manager.update_outputs(row_idx, title=translated_title, srt=srt_path, desc=desc_path)

        # 3. Đang tạo giọng đọc & Render
        manager.update_status(row_idx, "Đang tạo giọng & Render")
        final_video_path = os.path.join(out_folder, f"{base_name}_dubbed.mp4")
        
        process_srt_to_video(
            srt_path=srt_path,
            video_path=video_path,
            output_path=final_video_path,
            max_workers=2,
            voice="BV074_streaming",
            tts_method="CapCut API",
            tts_api_key=config.get("tts_api_key", ""),
            vieneu_api_key=config.get("vieneu_api_key", ""),
            speed_factor=1.05,
            video_title=translated_title,
            source_url=url,
            gemini_api_key=config.get("gemini_api_key", ""),
            viethoa_output_dir=viethoa_out_dir
        )

        if not os.path.exists(final_video_path):
            raise RuntimeError("Lỗi ở bước Render cuối cùng (không tìm thấy file dubbed).")

        # Hoàn thành
        manager.update_outputs(row_idx, video=final_video_path)
        manager.update_status(row_idx, "Hoàn thành")
        print(f"[XONG] Đã hoàn thành xử lý dòng {row_idx}: {translated_title}")

    except Exception as e:
        manager.update_status(row_idx, "Lỗi", str(e))
        print(f"[LỖI] Dòng {row_idx}: {e}")

def main():
    print("="*50)
    print(" BẮT ĐẦU LOCAL EXCEL QUEUE WORKER")
    print("="*50)

    config = load_config()

    try:
        manager = ExcelQueueManager(EXCEL_QUEUE_PATH)
        print(f"[OK] Đã sẵn sàng đọc file Excel tại: {EXCEL_QUEUE_PATH}")
    except Exception as e:
        print(f"[LỖI KẾT NỐI EXCEL] {e}")
        return

    print("Bắt đầu quét danh sách Excel...")
    while True:
        try:
            task = manager.get_next_pending_task()
            if task:
                print(f"\n[PHÁT HIỆN TASK MỚI] Dòng {task['row_index']} - Link: {task['link']}")
                process_task(task, manager, config)
            else:
                print("Đã xử lý xong toàn bộ danh sách. Hàng đợi trống!")
                break
        except Exception as e:
            print(f"[LỖI SYSTEM] Lỗi vòng lặp chính: {e}")
            break

if __name__ == "__main__":
    main()
