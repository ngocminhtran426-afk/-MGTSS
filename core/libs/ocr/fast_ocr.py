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
import difflib
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

def compare_text_presence(img, ref_img):
    """
    Sử dụng Canny Edge Detection và IoU để xác định xem khung hình hiện tại 
    có chứa dòng chữ giống với khung hình tham chiếu (ref_img) hay không.
    Rất hiệu quả chống lại background chuyển động.
    """
    edges_img = cv2.Canny(img, 100, 200)
    edges_ref = cv2.Canny(ref_img, 100, 200)
    
    # Số lượng pixel cạnh của chữ mẫu
    ref_edge_pixels = np.sum(edges_ref > 0)
    if ref_edge_pixels < 10:
        return 0.0 # Không có chữ hoặc quá mờ
        
    # Tính phần giao nhau (Intersection)
    intersection = cv2.bitwise_and(edges_img, edges_ref)
    intersection_pixels = np.sum(intersection > 0)
    
    # Tỷ lệ khớp (0.0 đến 1.0)
    match_score = intersection_pixels / ref_edge_pixels
    return match_score

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
                first_job = self.job_queue.get(timeout=0.5)
                batch.append(first_job)
                while len(batch) < self.batch_size:
                    try:
                        job = self.job_queue.get_nowait()
                        batch.append(job)
                    except queue.Empty:
                        break
            except queue.Empty:
                continue
                
            for timestamp, img in batch:
                text = self._do_ocr(img)
                if text:
                    self.results.append((timestamp, text, img))
                self.job_queue.task_done()

    def stop(self):
        super().stop()
        self.worker_thread.join()

class CPUOcrEngine(BaseOcrEngine):
    def __init__(self, reader, engine_type, workers=1, max_queue_size=32):
        super().__init__(reader, engine_type, max_queue_size)
        self.worker_thread = threading.Thread(target=self._worker_loop)
        self.worker_thread.start()

    def _worker_loop(self):
        while self.is_running or not self.job_queue.empty():
            try:
                job = self.job_queue.get(timeout=0.5)
                timestamp, img = job
                
                text = self._do_ocr(img)
                if text:
                    self.results.append((timestamp, text, img))
                    
                self.job_queue.task_done()
            except queue.Empty:
                continue

    def stop(self):
        super().stop()
        self.worker_thread.join()

def main():
    parser = argparse.ArgumentParser(description="Multi-Pass Frame-Perfect OCR Pipeline")
    parser.add_argument('--video', type=str, required=True, help="Đường dẫn đến file video")
    parser.add_argument('--out_srt', type=str, required=True, help="Đường dẫn xuất file SRT")
    parser.add_argument('--crop', type=str, help="Tọa độ cắt ảnh: y_min,y_max,x_min,x_max")
    parser.add_argument('--langs', type=str, default="vi,en", help="Ngôn ngữ OCR")
    parser.add_argument('--device', type=str, default="auto", choices=['auto', 'gpu', 'cpu'])
    parser.add_argument('--workers', type=int, default=0)
    parser.add_argument('--batch_size', type=int, default=8)
    
    args = parser.parse_args()
    
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
    else:
        use_gpu = False
        
    lang_list = args.langs.split(',')
    reader, engine_type = init_ocr_reader(lang_list, use_gpu)
    
    if use_gpu:
        ocr_engine = GPUOcrEngine(reader, engine_type, batch_size=args.batch_size, max_queue_size=64)
    else:
        workers = args.workers if args.workers > 0 else max(2, min(8, os.cpu_count() // 2))
        ocr_engine = CPUOcrEngine(reader, engine_type, workers=workers, max_queue_size=64)
        
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[ERROR] Không thể mở video: {args.video}")
        return
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30.0
    
    # PASS 1: Sparse Scan (3 FPS)
    sparse_fps = 3.0
    frame_step = max(1, int(fps / sparse_fps))
    
    crop_coords = (0.75, 1.0, 0.0, 1.0)
    if args.crop:
        try:
            crop_coords = tuple(map(float, args.crop.split(',')))
        except:
            pass
    y_min, y_max, x_min, x_max = crop_coords
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_dur_ms = (total_frames / fps) * 1000.0
    print(f"\n[PASS 1] Bắt đầu quét thưa Video ({sparse_fps} FPS) để tìm nội dung phụ đề...")
    
    pbar = tqdm(total=total_frames // frame_step, desc="Sparse OCR Scan", file=sys.stdout)
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
        current_time_ms = (f_idx / fps) * 1000.0 # BẢO MẬT: Tính thời gian bằng toán học, tránh lỗi OpenCV trả về rác
        
        if is_frame_different(gray, prev_crop, threshold=10):
            prev_crop = gray
            ocr_engine.job_queue.put((current_time_ms, gray))
            
        pbar.update(1)
        f_idx += 1
        
    pbar.close()
    
    print("\nĐang chờ các luồng OCR hoàn tất (Pass 1)...")
    ocr_engine.stop()
    
    raw_results = ocr_engine.get_results()
    raw_results.sort(key=lambda x: x[0])
    
    # Temporal Grouping (Gộp các cụm giống nhau bằng difflib)
    blocks = []
    for ts, text, img in raw_results:
        if len(text) < 2: continue
        if not blocks:
            blocks.append({'text': text, 'start': ts, 'end': ts, 'ref_img': img})
        else:
            prev = blocks[-1]
            ratio = difflib.SequenceMatcher(None, text, prev['text']).ratio()
            if ratio > 0.8:
                prev['end'] = ts
                if len(text) > len(prev['text']):
                    prev['text'] = text
                    prev['ref_img'] = img # Cập nhật ảnh tham chiếu nét hơn
            else:
                # Nếu cách nhau quá xa (vô lý), không nối
                if ts - prev['end'] < 2000:
                    blocks.append({'text': text, 'start': ts, 'end': ts, 'ref_img': img})
                else:
                    blocks.append({'text': text, 'start': ts, 'end': ts, 'ref_img': img})

    # PASS 2: Dense Frame Alignment (Native FPS)
    print(f"\n[PASS 2] Khớp khung hình chuẩn xác (Dense Scan - {fps} FPS) cho {len(blocks)} câu phụ đề...")
    
    final_blocks = []
    pbar2 = tqdm(total=len(blocks), desc="Frame Alignment", file=sys.stdout)
    
    for block in blocks:
        # Tìm START chính xác
        search_start_ms = max(0, block['start'] - 1500)
        cap.set(cv2.CAP_PROP_POS_MSEC, search_start_ms)
        
        exact_start = block['start']
        exact_end = block['end']
        
        # Quét tới để tìm khung hình đầu tiên khớp
        while True:
            # Fix lỗi timestamp ảo của OpenCV
            curr_ms = (cap.get(cv2.CAP_PROP_POS_FRAMES) / fps) * 1000.0
            if curr_ms > block['start'] + 500: # Vượt quá ngưỡng an toàn
                break
            ret, frame = cap.read()
            if not ret: break
            
            crop_img = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            
            score = compare_text_presence(gray, block['ref_img'])
            if score > 0.35: # Ngưỡng khớp cạnh (Edge Match)
                exact_start = min(curr_ms, total_dur_ms)
                break
                
        # Tìm END chính xác
        search_end_start_ms = max(exact_start + 500, block['end'] - 1000)
        cap.set(cv2.CAP_PROP_POS_MSEC, search_end_start_ms)
        
        while True:
            # Fix lỗi timestamp ảo của OpenCV
            curr_ms = (cap.get(cv2.CAP_PROP_POS_FRAMES) / fps) * 1000.0
            if curr_ms > block['end'] + 1500:
                break
            ret, frame = cap.read()
            if not ret: break
            
            crop_img = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            
            score = compare_text_presence(gray, block['ref_img'])
            if score < 0.2: # Chữ đã biến mất
                exact_end = min(curr_ms, total_dur_ms)
                break
            else:
                exact_end = min(curr_ms, total_dur_ms) # Cập nhật liên tục khi vẫn còn chữ
                
        final_blocks.append({
            'start': exact_start,
            'end': exact_end,
            'text': block['text']
        })
        pbar2.update(1)
        
    pbar2.close()
    cap.release()
    
    print(f"\n[PASS 3] Lưu kết quả SRT siêu chuẩn xác: {args.out_srt}")
    with open(args.out_srt, 'w', encoding='utf-8') as f:
        idx = 1
        for b in final_blocks:
            s_str = format_time_srt(b['start'])
            e_str = format_time_srt(b['end'])
            f.write(f"{idx}\n{s_str} --> {e_str}\n{b['text']}\n\n")
            idx += 1
            
    print("HOÀN TẤT PIIPELINE OCR THÍCH ỨNG!")

if __name__ == '__main__':
    main()
