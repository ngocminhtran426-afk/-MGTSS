import json

def ms_to_time(ms):
    """Chuyển đổi milliseconds sang định dạng thời gian của SRT (HH:MM:SS,mmm)"""
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def create_srt_from_chunks(chunk_results, output_path="output.srt"):
    """Gộp nhiều kết quả JSON từ các đoạn cắt và tạo thành 1 file SRT duy nhất"""
    try:
        all_utterances = []
        
        for result in chunk_results:
            offset_ms = result.get("offset_ms", 0)
            json_data = result.get("json_data", {})
            
            tasks = json_data.get("data", {}).get("tasks", [])
            if not tasks:
                continue
                
            task_info = tasks[0]
            payload_str = task_info.get("payload", "{}")
            payload = json.loads(payload_str)
            
            utterances = payload.get("utterances", [])
            
            # Cộng dồn offset vào start_time và end_time
            for u in utterances:
                u['start_time'] += offset_ms
                u['end_time'] += offset_ms
                for w in u.get('words', []):
                    w['start_time'] += offset_ms
                    w['end_time'] += offset_ms
                all_utterances.append(u)
                
        if not all_utterances:
            return False, "Không tìm thấy đoạn hội thoại nào sau khi gộp."
            
        # Sắp xếp lại theo thời gian thực (đề phòng các luồng trả về lộn xộn)
        all_utterances.sort(key=lambda x: x['start_time'])
        
        with open(output_path, "w", encoding="utf8") as f:
            for i, c in enumerate(all_utterances, 1):
                start_time = ms_to_time(c['start_time'])
                end_time = ms_to_time(c['end_time'])
                text = c.get('text', '')

                # Viết vào file SRT
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")

        return True, f"Đã xuất file thành công: {output_path}"
    except Exception as e:
        return False, f"Lỗi khi tạo file SRT: {str(e)}"
