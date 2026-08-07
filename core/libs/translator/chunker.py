import srt
import hashlib
from typing import List, Dict

class SRTChunker:
    def __init__(self, srt_path: str, max_chars: int = 1500):
        """
        max_chars: Giới hạn ký tự mỗi batch. 
        Mặc định 1500 chars (khoảng 30-50 dòng SRT), tương đương khoảng 500-1000 tokens tùy ngôn ngữ.
        """
        self.srt_path = srt_path
        self.max_chars = max_chars

    def parse_and_chunk(self) -> List[Dict]:
        """
        Đọc file SRT và chia thành các nhóm ngữ nghĩa (semantic groups / batches).
        Trả về danh sách các Dictionary cấu trúc cho Database.
        """
        with open(self.srt_path, 'r', encoding='utf-8') as f:
            subs = list(srt.parse(f.read()))
            
        jobs = []
        current_group = []
        current_ids = []
        current_length = 0
        
        for idx, sub in enumerate(subs):
            clean_content = str(sub.content).replace('\n', ' ').strip()
            line_str = f"[{idx}] {clean_content}\n"
            line_len = len(line_str)
            
            if current_length + line_len > self.max_chars and current_group:
                jobs.append(self._create_job(current_ids, current_group))
                current_group = []
                current_ids = []
                current_length = 0
                
            current_group.append(line_str)
            current_ids.append(idx)
            current_length += line_len
            
        if current_group:
            jobs.append(self._create_job(current_ids, current_group))
            
        return jobs

    def _create_job(self, source_ids: List[int], source_lines: List[str]) -> Dict:
        """
        Đóng gói một batch thành một Job record hoàn chỉnh.
        Tạo ID duy nhất dựa trên index và mã băm để idempotent (chống trùng lặp nếu chạy lại pipeline).
        """
        source_text = "".join(source_lines)
        # Sử dụng MD5 của nội dung làm định danh phụ để luôn đảm bảo tính Unique & Idempotent
        h = hashlib.md5(source_text.encode('utf-8')).hexdigest()[:8]
        group_id = f"g_{source_ids[0]:05d}_{source_ids[-1]:05d}_{h}"
        
        return {
            'group_id': group_id,
            'source_ids': source_ids,
            'source': source_text
        }
