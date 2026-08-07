import os
import srt
import re
from typing import Optional, List
from .db import TranslationDB
from .provider import GeminiProvider
from .chunker import SRTChunker
from .pipeline import TranslationPipeline

class TranslatorEngine:
    def __init__(self, api_keys: List[str], srt_path: str, src_lang: str, dst_lang: str, max_concurrency: int = 10):
        self.srt_path = srt_path
        self.src_lang = src_lang
        self.dst_lang = dst_lang
        
        # Xác định thư mục lưu trữ state
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # core/
        tool_packaged_dir = os.path.dirname(base_dir) # Tool_Packaged/
        data_dir = os.path.join(tool_packaged_dir, "storage", "data", "translation_state")
        os.makedirs(data_dir, exist_ok=True)
        
        # Khởi tạo đường dẫn DB và JSONL
        db_path = os.path.join(data_dir, "state.sqlite")
        self.jsonl_path = os.path.join(data_dir, "translations.jsonl")
        
        self.db = TranslationDB(db_path)
        self.provider = GeminiProvider(api_keys=api_keys)
        self.concurrency = max_concurrency

    async def run_async(self) -> str:
        """Thực thi pipeline hoàn chỉnh một cách bất đồng bộ."""
        # 1. Parse SRT thành các khối semantic groups
        chunker = SRTChunker(self.srt_path)
        all_jobs_data = chunker.parse_and_chunk()
        
        # 2. Đưa các job vào DB (sẽ được bỏ qua an toàn nếu đã có nhờ `INSERT OR IGNORE`)
        self.db.add_jobs(all_jobs_data)
        
        # 3. Resume: Kéo tất cả các job chưa hoàn thành (PENDING hoặc RETRY)
        pending_jobs = self.db.get_pending_jobs(limit=1000000)
        
        progress = self.db.get_progress()
        print(f"Tổng quan tiến trình: {progress}")
        
        # 4. Kích hoạt Async Pipeline nếu có job cần chạy
        if pending_jobs:
            pipeline = TranslationPipeline(
                db=self.db,
                provider=self.provider,
                jsonl_path=self.jsonl_path,
                src_lang=self.src_lang,
                dst_lang=self.dst_lang,
                concurrency=self.concurrency
            )
            await pipeline.run(pending_jobs)
        else:
            print("Không có job nào cần chạy (Tất cả đã hoàn thành hoặc thất bại vượt quá số lần cho phép).")
            
        # 5. Lắp ráp lại thành file SRT cuối cùng từ các job DONE
        return self._assemble_srt()
        
    def _assemble_srt(self) -> str:
        with open(self.srt_path, 'r', encoding='utf-8') as f:
            subs = list(srt.parse(f.read()))
            
        # Lấy TẤT CẢ các job (DONE, FAILED, PENDING) từ DB
        # Nếu job DONE thì lấy translation, nếu chưa DONE thì lấy source để fallback (không làm hỏng SRT)
        all_jobs = self.db.get_all_jobs()
        
        # Map kết quả vào file SRT gốc
        for job in all_jobs:
            content_to_use = job['translation'] if job['status'] == 'DONE' and job['translation'] else job['source']
            lines = content_to_use.split('\n')
            for line in lines:
                # Regex [ID] Nội dung
                match = re.search(r'^\[(\d+)\]\s*(.*)', line.strip())
                if match:
                    idx = int(match.group(1))
                    content = match.group(2).strip()
                    if 0 <= idx < len(subs):
                        subs[idx].content = content
                        
        # Kiểm tra chống lỗi định dạng (đảm bảo không rỗng)
        for sub in subs:
            if not sub.content or sub.content.isspace():
                sub.content = "..."
                
        safe_dst = self.dst_lang.replace(" ", "")
        out_srt = os.path.splitext(self.srt_path)[0] + f"_{safe_dst}.srt"
        with open(out_srt, "w", encoding="utf-8") as f:
            f.write(srt.compose(subs))
            
        print(f"✅ Lắp ráp hoàn tất, file SRT dịch đã lưu tại: {out_srt}")
        return out_srt
