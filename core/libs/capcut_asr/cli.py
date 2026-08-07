import sys
import os
import argparse
import time
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the directory to sys.path so we can import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import CapCutAPI
from converter import create_srt_from_chunks

def log(msg):
    print(msg, flush=True)

def process_video(video_path, language):
    log("Bắt đầu xử lý...")
    log(f"Video: {video_path}")
    log(f"Ngôn ngữ: {language}")
    
    # Map ngôn ngữ
    lang_map = {
        "Việt Nam": "vi-VN",
        "Tiếng Việt": "vi-VN",
        "Trung Quốc": "zh-CN",
        "Tiếng Anh": "en-US",
        "Nhật Bản": "ja-JP",
        "Hàn Quốc": "ko-KR",
        "Tự động phát hiện": "auto" # Or whatever default CapCut supports, maybe vi-VN
    }
    lang_code = lang_map.get(language, "vi-VN")
    
    api = CapCutAPI()
    
    log("1. Đang quét siêu tốc video để tìm khoảng lặng (dùng FFmpeg)...")
    
    # Quét khoảng lặng bằng FFmpeg
    cmd_silence = [
        "ffmpeg", "-i", video_path, "-vn", 
        "-af", "silencedetect=noise=-30dB:d=0.5", 
        "-f", "null", "-"
    ]
    
    # Hide window on Windows
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    result = subprocess.run(cmd_silence, capture_output=True, text=True, encoding="utf-8", startupinfo=startupinfo)
    output = result.stderr
    
    # Lấy thời lượng tổng
    dur_match = re.search(r"Duration:\s+(\d+):(\d+):([\d\.]+)", output)
    total_duration_s = 0
    if dur_match:
        h, m, s = dur_match.groups()
        total_duration_s = int(h)*3600 + int(m)*60 + float(s)
    
    if total_duration_s == 0:
        raise Exception("Không thể đọc được thời lượng video. Có thể file bị lỗi.")
    
    # Lấy khoảng lặng
    starts = re.findall(r"silence_start:\s+([\d\.]+)", output)
    ends = re.findall(r"silence_end:\s+([\d\.]+)", output)
    silences = [(float(s), float(e)) for s, e in zip(starts, ends)]
    
    chunk_target_s = 300 # 5 phút
    chunks = []
    
    log("2. Đang tính toán nhát cắt...")
    if total_duration_s <= chunk_target_s:
        chunks.append({"start_s": 0.0, "end_s": total_duration_s})
    else:
        current_start = 0.0
        while current_start < total_duration_s:
            target_cut = current_start + chunk_target_s
            if target_cut >= total_duration_s:
                chunks.append({"start_s": current_start, "end_s": total_duration_s})
                break
                
            best_cut = target_cut
            if silences:
                min_diff = float('inf')
                for s, e in silences:
                    mid = (s + e) / 2
                    if current_start < mid < total_duration_s:
                        diff = abs(mid - target_cut)
                        if diff < min_diff:
                            min_diff = diff
                            best_cut = mid
            
            # Nếu không tìm thấy khoảng lặng phù hợp (hoặc không có khoảng lặng nào)
            # thì ép buộc cắt ngay tại mốc 5 phút
            if best_cut - current_start < 60:
                best_cut = target_cut
                
            chunks.append({"start_s": current_start, "end_s": best_cut})
            current_start = best_cut
    
    log(f"   -> Đã tính xong: cắt thành {len(chunks)} đoạn nhỏ.")
    
    # Hàm xử lý 1 chunk
    def process_chunk(idx, chunk_data):
        start_s = chunk_data["start_s"]
        end_s = chunk_data["end_s"]
        
        chunk_file = os.path.splitext(video_path)[0] + f"_chunk_{idx}.mp3"
        
        # Trích xuất đoạn mp3 nhỏ từ video gốc
        log(f"   [Đoạn {idx+1}] Bắt đầu tách âm thanh ({end_s - start_s:.1f}s)...")
        cmd_extract = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", str(start_s), "-to", str(end_s),
            "-vn", "-acodec", "libmp3lame", "-q:a", "5",
            chunk_file
        ]
        subprocess.run(cmd_extract, capture_output=True, startupinfo=startupinfo)
        
        if not os.path.exists(chunk_file):
            raise Exception(f"Lỗi khi tách MP3 đoạn {idx+1}")
        
        log(f"   [Đoạn {idx+1}] Đã tách xong, tải lên CapCut...")
        upload_info = api.process_audio_file(chunk_file)
        
        log(f"   [Đoạn {idx+1}] Ra lệnh AI...")
        submit_resp = api.create_caption_task(upload_info, lang_code)
        tasks = submit_resp.get("data", {}).get("tasks", [])
        if not tasks:
            raise Exception(f"Submit đoạn {idx+1} thất bại")
        
        task_id = tasks[0]["id"]
        token = tasks[0]["token"]
        
        for i in range(120): # Tối đa 10 phút chờ
            query_resp = api.get_caption_result(task_id, token)
            task_list = query_resp.get("data", {}).get("tasks", [])
            if task_list:
                status = task_list[0].get("status")
                if status in ["succeed", "success"]:
                    log(f"   [Đoạn {idx+1}] ✅ AI xử lý xong!")
                    try: os.remove(chunk_file)
                    except: pass
                    # Converter yêu cầu offset_ms (milliseconds)
                    return {"offset_ms": int(start_s * 1000), "json_data": query_resp}
                elif status == "failed":
                    raise Exception(f"AI xử lý đoạn {idx+1} thất bại")
            time.sleep(5)
        raise Exception(f"Hết thời gian chờ đoạn {idx+1}")

    log("3. Bắt đầu đẩy nhiều luồng xử lý song song lên server...")
    chunk_results = []
    has_error = False
    error_msg = ""
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for i, c in enumerate(chunks):
            futures.append(executor.submit(process_chunk, i, c))
        
        for future in as_completed(futures):
            try:
                chunk_results.append(future.result())
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
    
    if has_error:
        raise Exception(f"Quá trình đa luồng thất bại: {error_msg}")
    
    log("4. Đang gộp phụ đề...")
    out_path = os.path.splitext(video_path)[0] + ".srt"
    success, msg = create_srt_from_chunks(chunk_results, out_path)
    
    if success:
        log("✅ HOÀN THÀNH:")
        log(f"SRT_PATH={out_path}")
    else:
        raise Exception(f"Lỗi khi gộp phụ đề: {msg}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='CapCut ASR Tool CLI')
    parser.add_argument('--video', required=True, help='Path to the video file')
    parser.add_argument('--language', required=True, help='Language for ASR (e.g., Tiếng Việt)')
    
    args = parser.parse_args()
    
    # Ensure stdout handles UTF-8 correctly
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        
    try:
        process_video(args.video, args.language)
    except Exception as e:
        log("❌ LỖI:")
        log(str(e))
        sys.exit(1)
