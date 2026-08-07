import asyncio
import json
from typing import List, Dict
from .db import TranslationDB
from .provider import LLMProvider, TranslationValidator
import os

class TranslationPipeline:
    def __init__(self, db: TranslationDB, provider: LLMProvider, jsonl_path: str, src_lang: str, dst_lang: str, concurrency: int = 10):
        self.db = db
        self.provider = provider
        self.jsonl_path = jsonl_path
        self.concurrency = concurrency
        self.queue = asyncio.Queue()
        self.src_lang = src_lang
        self.dst_lang = dst_lang
        self.active_tasks = []

    async def worker(self, worker_id: int):
        while True:
            try:
                job = await self.queue.get()
            except asyncio.CancelledError:
                break
                
            group_id = job['group_id']
            source = job['source']
            source_ids = job['source_ids']
            
            # Đánh dấu đang xử lý trong SQLite
            self.db.mark_job_processing(group_id)
            
            # 1. Check Translation Memory (TM) first
            cached = self.db.check_translation_memory(source)
            if cached:
                print(f"[Worker {worker_id}] CACHE HIT cho {group_id}")
                self._save_success(group_id, source, cached)
                self.queue.task_done()
                continue
                
            # 2. Cache MISS -> Gọi API
            success = False
            error_msg = ""
            
            # Tự implement backoff đơn giản (2s, 4s, 8s, 16s, 32s)
            for attempt in range(1, 6):
                try:
                    response_text = await self.provider.translate_batch(source, self.src_lang, self.dst_lang)
                    
                    # Validate cấu trúc JSON/SRT để không lưu dữ liệu rác
                    is_last_attempt = (attempt == 5)
                    result_dict = TranslationValidator.validate_and_parse(response_text, source_ids, source, is_last_attempt)
                    
                    # Ghép lại thành chuỗi đúng định dạng [ID] nội dung
                    final_translation = ""
                    for k in sorted(result_dict.keys()):
                        final_translation += f"[{k}] {result_dict[k]}\n"
                        
                    self._save_success(group_id, source, final_translation.strip())
                    success = True
                    break
                except Exception as e:
                    error_msg = str(e)
                    print(f"[Worker {worker_id}] Lỗi {group_id} lần {attempt}: {e}")
                    if attempt < 5:
                        await asyncio.sleep(2 ** attempt) 
                    
            if not success:
                print(f"[Worker {worker_id}] THẤT BẠI HOÀN TOÀN {group_id} sau 5 lần thử.")
                self.db.update_job_failed(group_id, error_msg, max_retries=5)
                
            self.queue.task_done()
            
    def _save_success(self, group_id: str, source: str, translation: str):
        # 1. Update SQLite
        self.db.update_job_success(group_id, translation)
        # 2. Update Translation Memory
        self.db.save_translation_memory(source, translation)
        # 3. Append vào JSONL trung gian
        with open(self.jsonl_path, 'a', encoding='utf-8') as f:
            record = {
                "group_id": group_id,
                "translation": translation
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def run(self, jobs: List[Dict]):
        if not jobs:
            return
            
        for job in jobs:
            self.queue.put_nowait(job)
            
        print(f"Bắt đầu pipeline đa luồng với {len(jobs)} jobs, {self.concurrency} workers.")
        
        self.active_tasks = []
        for i in range(self.concurrency):
            task = asyncio.create_task(self.worker(i + 1))
            self.active_tasks.append(task)
            
        # Block until all queue elements have been processed
        await self.queue.join()
        
        for task in self.active_tasks:
            task.cancel()
            
        print("Hoàn tất pipeline đa luồng.")
