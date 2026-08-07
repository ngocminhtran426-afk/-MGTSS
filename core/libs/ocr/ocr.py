import os
import json
import time
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from config import PROGRESS_FILE, MAX_WORKERS, MAX_RETRIES
from drive import upload_image_as_doc, delete_file, get_drive_service
from docs import read_doc_text, get_docs_service

thread_local = threading.local()

def get_services(creds):
    if not hasattr(thread_local, "drive_service"):
        thread_local.drive_service = get_drive_service(creds)
        thread_local.docs_service = get_docs_service(creds)
    return thread_local.drive_service, thread_local.docs_service

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=4)

def process_single_image(image_path, creds):
    """
    Xử lý 1 ảnh: Upload -> Đọc Text -> Xóa
    Có cơ chế retry nếu gặp lỗi (ví dụ: Rate Limit 429 hoặc Network Error).
    """
    drive_service, docs_service = get_services(creds)
    for attempt in range(1, MAX_RETRIES + 1):
        file_id = None
        try:
            # 1. Upload & Convert to Docs
            file_id = upload_image_as_doc(drive_service, image_path)
            
            # 2. Đọc nội dung
            text = read_doc_text(docs_service, file_id)
            
            # 3. Xóa file trên Drive
            delete_file(drive_service, file_id)
            
            return text
        except Exception as e:
            if file_id:
                # Cố gắng dọn dẹp nếu đã upload nhưng lỗi lúc đọc
                delete_file(drive_service, file_id)
            
            if attempt == MAX_RETRIES:
                print(f"\n[Lỗi] Không thể xử lý {os.path.basename(image_path)} sau {MAX_RETRIES} lần thử: {e}")
                return ""
            
            # Exponential backoff (đợi 2s, 4s, 8s...)
            time.sleep(2 ** attempt)
    return ""

def process_images_multithread(image_files, creds):
    """
    Chạy đa luồng xử lý danh sách ảnh. Tự động lưu tiến độ.
    """
    progress = load_progress()
    results = {}
    
    # Lọc ra các file chưa được xử lý
    files_to_process = [f for f in image_files if os.path.basename(f) not in progress]
    
    if not files_to_process:
        print("Tất cả ảnh đã được OCR từ trước.")
        return progress

    print(f"Cần OCR {len(files_to_process)} ảnh. Khởi tạo {MAX_WORKERS} luồng...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit tasks
        future_to_file = {
            executor.submit(process_single_image, img, creds): img 
            for img in files_to_process
        }
        
        # Nhận kết quả với thanh tiến trình
        for future in tqdm(as_completed(future_to_file), total=len(files_to_process), desc="OCR Progress", file=sys.stdout, mininterval=2.0):
            img_path = future_to_file[future]
            filename = os.path.basename(img_path)
            try:
                text = future.result()
                progress[filename] = text
                # Lưu file tiến độ liên tục để đề phòng crash
                save_progress(progress)
            except Exception as e:
                print(f"\n[Lỗi nghiêm trọng] {filename} sinh ra exception: {e}")
                
    return progress
