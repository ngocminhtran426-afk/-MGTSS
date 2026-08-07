import os
import re

def parse_time_from_filename(filename):
    """
    VideoSubFinder tạo tên file theo format: 0_00_01_100__0_00_03_500.jpeg
    Hàm này chuyển chuỗi đó thành định dạng SRT: 00:00:01,100 --> 00:00:03,500
    """
    # Xóa phần mở rộng (ví dụ .jpeg)
    name = os.path.splitext(filename)[0]
    
    # Format của VideoSubFinder: h_mm_ss_ms__h_mm_ss_ms
    parts = name.split('__')
    if len(parts) != 2:
        return "00:00:00,000 --> 00:00:00,000"
    
    def format_time(t_str):
        # Ví dụ: 0_00_01_100
        t_parts = t_str.split('_')
        if len(t_parts) >= 4:
            h, m, s, ms = t_parts[0:4]
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(ms):03d}"
        return "00:00:00,000"
    
    start_time = format_time(parts[0])
    end_time = format_time(parts[1])
    return f"{start_time} --> {end_time}"

def generate_srt(ocr_results, output_path):
    """
    Gom các dòng OCR liên tiếp giống nhau và xuất ra file SRT.
    ocr_results là một dictionary: { filename: text, ... }
    """
    # Sắp xếp theo tên file (VideoSubFinder đã đặt tên theo thứ tự thời gian)
    sorted_files = sorted(ocr_results.keys())
    
    blocks = []
    current_text = None
    current_start = None
    current_end = None
    
    def add_block(text, start, end):
        if text and text.strip():
            # Thay thế các ký tự newline lỗi thành dấu cách
            clean_text = text.replace('\n', ' ').replace('\r', '').strip()
            # Lọc bỏ các ký tự đặc biệt vô nghĩa (chỉ giữ lại chữ, số và dấu câu cơ bản)
            clean_text = re.sub(r'[^\w\s\.\?\!,]', '', clean_text).strip()
            
            if clean_text:
                blocks.append({
                    'time': f"{start.split(' --> ')[0]} --> {end.split(' --> ')[1]}",
                    'text': clean_text
                })

    for filename in sorted_files:
        text = ocr_results[filename]
        time_str = parse_time_from_filename(filename)
        
        # Bỏ qua nếu OCR không ra chữ
        if not text or not text.strip():
            continue
            
        # Thêm mỗi ảnh thành 1 dòng (không gộp)
        add_block(text, time_str, time_str)
        
    # Ghi ra file SRT
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, block in enumerate(blocks, 1):
            f.write(f"{i}\n")
            f.write(f"{block['time']}\n")
            f.write(f"{block['text']}\n\n")
            
    print(f"\n[Thành công] Đã xuất file SRT tại: {output_path}")
