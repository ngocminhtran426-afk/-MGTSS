import argparse
import os
import sys
import cv2
import numpy as np
from tqdm import tqdm
import re
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

def format_time_srt(ms):
    s, ms = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def is_frame_different(curr, prev, threshold=12):
    if prev is None:
        return True
    diff = cv2.absdiff(curr, prev)
    return np.mean(diff) > threshold

def init_ocr_reader(lang_list, use_gpu):
    engine_type = "easyocr"
    reader = None
    
    if "ch_sim" in lang_list:
        try:
            from rapidocr_onnxruntime import RapidOCR
            reader = RapidOCR()
            engine_type = "paddleocr"
        except Exception as e:
            print(f"Không thể tải PaddleOCR: {e}. Dự phòng sang EasyOCR...")
            import easyocr
            reader = easyocr.Reader(lang_list, gpu=use_gpu)
    else:
        import easyocr
        reader = easyocr.Reader(lang_list, gpu=use_gpu)
        
    return reader, engine_type

class BaseOcrEngine:
    def __init__(self, reader, engine_type, max_queue_size=32):
        self.reader = reader
        self.engine_type = engine_type
        self.job_queue = queue.Queue(maxsize=max_queue_size)
        self.results = []
        self.is_running = True
        
    def _do_ocr(self, img):
        text = ""
        try:
            if self.engine_type == "paddleocr":
                result, _ = self.reader(img)
                if result:
                    text_lines = [str(item[1]) for item in result if float(item[2]) > 0.4]
                    text = " ".join(text_lines)
            else:
                result = self.reader.readtext(img, detail=0)
                text = " ".join(result)
        except Exception as e:
            pass
            
        text = text.replace('\n', ' ').replace('\r', '').strip()
        # Clean garbage characters
        text = re.sub(r'[^\w\s\.\?\!,，。？！“”]', '', text).strip()
        return text

    def stop(self):
        self.is_running = False

    def get_results(self):
        return self.results

class GPUOcrEngine(BaseOcrEngine):
    def __init__(self, reader, engine_type, batch_size=8, max_queue_size=32):
        super().__init__(reader, engine_type, max_queue_size)
        self.batch_size = batch_size
        self.worker_thread = threading.Thread(target=self._worker_loop)
        self.worker_thread.start()
        
    def _worker_loop(self):
        while self.is_running or not self.job_queue.empty():
            batch = []
            try:
                # Cố gắng lấy job đầu tiên (block 0.5s để thoát vòng lặp gọn gàng)
                first_job = self.job_queue.get(timeout=0.5)
                batch.append(first_job)
                
                # Cố gắng nhặt thêm thành micro-batch nếu queue đang có sẵn
                while len(batch) < self.batch_size:
                    try:
                        job = self.job_queue.get_nowait()
                        batch.append(job)
                    except queue.Empty:
                        break
            except queue.Empty:
                continue
                
            # Xử lý batch
            # Vì rapidocr/easyocr thường không hỗ trợ array of arrays tốt từ Python API wrapper,
            # Ta fallback sang loop tối ưu (Inference siêu nhanh trên GPU)
            for timestamp, img in batch:
                text = self._do_ocr(img)
                if text:
                    self.results.append((timestamp, text))
                self.job_queue.task_done()

    def stop(self):
        super().stop()
        self.worker_thread.join()

class CPUOcrEngine(BaseOcrEngine):
    def __init__(self, reader, engine_type, workers=4, max_queue_size=32):
        super().__init__(reader, engine_type, max_queue_size)
        self.workers_count = workers
        self.executor = ThreadPoolExecutor(max_workers=self.workers_count)
        self.futures = []
        self.worker_thread = threading.Thread(target=self._dispatch_loop)
        self.worker_thread.start()

    def _dispatch_loop(self):
        while self.is_running or not self.job_queue.empty():
            try:
                job = self.job_queue.get(timeout=0.5)
                timestamp, img = job
                
                # Bắn vào ThreadPool để tận dụng Multi-core CPU
                future = self.executor.submit(self._process_single, timestamp, img)
                self.futures.append(future)
            except queue.Empty:
                continue

    def _process_single(self, timestamp, img):
        text = self._do_ocr(img)
        if text:
            # list.append là thread-safe trong CPython nhờ GIL
            self.results.append((timestamp, text))
        self.job_queue.task_done()

    def stop(self):
        super().stop()
        self.worker_thread.join()
        self.executor.shutdown(wait=True)

def main():
    parser = argparse.ArgumentParser(description="Adaptive OCR Pipeline (GPU/CPU Thích ứng)")
    parser.add_argument('--video', type=str, required=True, help="Đường dẫn đến file video")
    parser.add_argument('--out_srt', type=str, required=True, help="Đường dẫn xuất file SRT")
    parser.add_argument('--crop', type=str, help="Tọa độ cắt ảnh: y_min,y_max,x_min,x_max")
    parser.add_argument('--langs', type=str, default="vi,en", help="Ngôn ngữ OCR")
    parser.add_argument('--device', type=str, default="auto", choices=['auto', 'gpu', 'cpu'], help="Thiết bị chạy OCR")
    parser.add_argument('--workers', type=int, default=0, help="Số lượng CPU worker (0 = auto)")
    parser.add_argument('--batch_size', type=int, default=8, help="Kích thước micro-batch trên GPU")
    
    args = parser.parse_args()
    
    # 1. Phát hiện phần cứng
    use_gpu = False
    if args.device == 'auto':
        import torch
        if torch.cuda.is_available():
            use_gpu = True
            print("Phát hiện GPU CUDA! Chế độ: GPU Worker + Micro-batching")
        else:
            print("Không tìm thấy CUDA. Chế độ: CPU Workers")
    elif args.device == 'gpu':
        use_gpu = True
        import torch
        if not torch.cuda.is_available():
            print("[CẢNH BÁO] Bạn đã ép chạy GPU nhưng không tìm thấy CUDA!")
    else:
        use_gpu = False
        print("Chế độ ép buộc: CPU Workers")
        
    # 2. Khởi tạo Engine
    lang_list = args.langs.split(',')
    reader, engine_type = init_ocr_reader(lang_list, use_gpu)
    
    if use_gpu:
        ocr_engine = GPUOcrEngine(reader, engine_type, batch_size=args.batch_size, max_queue_size=32)
    else:
        workers = args.workers if args.workers > 0 else max(2, min(8, os.cpu_count() // 2))
        print(f"Khởi tạo Pool với {workers} CPU Workers.")
        ocr_engine = CPUOcrEngine(reader, engine_type, workers=workers, max_queue_size=32)
        
    # 3. Phân tích Video (Tầng 1 - Giảm thiểu OCR)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[ERROR] Không thể mở video: {args.video}")
        return
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 25.0
    frame_step = int(fps / 2)
    if frame_step == 0: frame_step = 1
    
    crop_coords = (0.75, 1.0, 0.0, 1.0)
    if args.crop:
        try:
            crop_coords = tuple(map(float, args.crop.split(',')))
        except:
            pass
    y_min, y_max, x_min, x_max = crop_coords
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"\nBắt đầu quét Video (kiểm tra mỗi {frame_step} khung hình)...")
    
    pbar = tqdm(total=total_frames // frame_step, desc="Đọc Video & Gửi OCR", file=sys.stdout)
    f_idx = 0
    prev_crop = None
    
    while True:
        ret = cap.grab()
        if not ret: break
        
        if f_idx % frame_step != 0:
            f_idx += 1
            continue
            
        ret, frame = cap.retrieve()
        if not ret: break
        
        h, w, _ = frame.shape
        y1, y2 = int(y_min * h), int(y_max * h)
        x1, x2 = int(x_min * w), int(x_max * w)
        crop_img = frame[y1:y2, x1:x2]
        
        gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
        current_time_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        
        # Debounce / Deduplicate
        if is_frame_different(gray, prev_crop, threshold=12):
            prev_crop = gray
            # Put vào Bounded Queue (Sẽ BLOCK luồng đọc video này nếu hàng đợi quá đầy)
            # Điều này tạo Backpressure tuyệt vời, tránh nổ RAM
            ocr_engine.job_queue.put((current_time_ms, crop_img))
            
        pbar.update(1)
        f_idx += 1
        
    pbar.close()
    
    # 4. Hậu xử lý (Tầng 3)
    print("\nĐang chờ các tiến trình OCR hoàn tất...")
    ocr_engine.stop() # Wait for workers to finish
    
    raw_results = ocr_engine.get_results()
    print(f"Thu thập được {len(raw_results)} kết quả OCR thô.")
    
    # Sort theo timestamp
    raw_results.sort(key=lambda x: x[0])
    
    # Merge subtitle intervals
    blocks = []
    current_text = ""
    current_start = 0
    current_end = 0
    
    for timestamp, text in raw_results:
        # Nếu câu giống hệ thống câu trước, chỉ cần nới rộng thời gian kết thúc
        if text == current_text:
            current_end = timestamp
        else:
            # Lưu câu cũ
            if current_text and len(current_text) > 1:
                blocks.append({
                    'start': current_start,
                    'end': timestamp,
                    'text': current_text
                })
            # Bắt đầu câu mới
            current_text = text
            current_start = timestamp
            current_end = timestamp
            
    # Lưu câu cuối cùng
    if current_text and len(current_text) > 1:
        blocks.append({
            'start': current_start,
            'end': current_end if current_end > current_start else current_start + 2000,
            'text': current_text
        })
        
    # Viết SRT
    print(f"Lưu kết quả SRT: {args.out_srt}")
    with open(args.out_srt, 'w', encoding='utf-8') as f:
        idx = 1
        for b in blocks:
            s_str = format_time_srt(b['start'])
            e_str = format_time_srt(b['end'])
            f.write(f"{idx}\n{s_str} --> {e_str}\n{b['text']}\n\n")
            idx += 1
            
    print("HOÀN TẤT PIIPELINE OCR THÍCH ỨNG!")

if __name__ == '__main__':
    main()
