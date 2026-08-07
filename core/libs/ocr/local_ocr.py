import argparse
import os
import glob
import time
import sys
import warnings
import ssl
import cv2
import numpy as np

ssl._create_default_https_context = ssl._create_unverified_context

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

warnings.filterwarnings("ignore")
import easyocr
from tqdm import tqdm
from extractor import process_video
from srt import generate_srt

def main():
    parser = argparse.ArgumentParser(description="Local OCR using EasyOCR")
    parser.add_argument('--video', type=str, help="Đường dẫn đến file video MP4 (để trích xuất ảnh)")
    parser.add_argument('--image_dir', type=str, help="Thư mục chứa ảnh đã trích xuất")
    parser.add_argument('--out_srt', type=str, required=True, help="Đường dẫn xuất file SRT")
    parser.add_argument('--crop', type=str, help="Tọa độ cắt ảnh: y_min,y_max,x_min,x_max")
    parser.add_argument('--langs', type=str, default="vi,en", help="Ngôn ngữ OCR, ví dụ: vi,en,ko,ja")
    
    args = parser.parse_args()
    
    input_dir = args.image_dir or os.path.join(os.path.dirname(args.out_srt), "LocalOCR_images")
    output_srt = args.out_srt
    
    if args.video:
        print("Đang khởi động tiến trình trích xuất phụ đề bằng VideoSubFinder...")
        if not os.path.exists(input_dir):
            os.makedirs(input_dir)
        else:
            for f in glob.glob(os.path.join(input_dir, '*.jpeg')) + glob.glob(os.path.join(input_dir, '*.jpg')):
                os.remove(f)
                
        crop_coords = None
        if args.crop:
            try:
                crop_coords = tuple(map(float, args.crop.split(',')))
            except:
                print("Lỗi định dạng --crop, sẽ dùng mặc định")
                
        process_video(args.video, input_dir, crop_coords=crop_coords)
        
    image_files = glob.glob(os.path.join(input_dir, '*.jpeg')) + glob.glob(os.path.join(input_dir, '*.jpg')) + glob.glob(os.path.join(input_dir, '*.png'))
    if not image_files:
        print(f"Không tìm thấy file ảnh nào trong thư mục: {input_dir}")
        sys.exit(0)
        
    lang_list = args.langs.split(',')
    reader = None
    engine_type = "easyocr"
    
    if "ch_sim" in lang_list:
        print(f"Phát hiện tiếng Trung: Đang tải mô hình PaddleOCR (RapidOCR) cực mạnh...")
        try:
            from rapidocr_onnxruntime import RapidOCR
            reader = RapidOCR()
            engine_type = "paddleocr"
            print("Đã tải mô hình PaddleOCR thành công.")
        except Exception as e:
            print(f"Lỗi khởi tạo PaddleOCR: {e}. Đang fallback về EasyOCR...")
            import easyocr
            reader = easyocr.Reader(lang_list, gpu=True)
    else:
        print(f"Ngôn ngữ: {args.langs} -> Đang tải mô hình EasyOCR...")
        import easyocr
        try:
            reader = easyocr.Reader(lang_list, gpu=True)
            print("Đã tải mô hình EasyOCR (GPU).")
        except Exception as e:
            print(f"Lỗi khởi tạo GPU, thử dùng CPU: {e}")
            reader = easyocr.Reader(lang_list, gpu=False)
            print("Đã tải mô hình EasyOCR (CPU).")

    print(f"Bắt đầu xử lý OCR cho {len(image_files)} ảnh bằng {engine_type}...")
    ocr_results = {}
    
    for img_path in tqdm(image_files, desc="OCR Progress", file=sys.stdout):
        filename = os.path.basename(img_path)
        try:
            text = ""
            # Read image using numpy to bypass Windows Unicode path limitation
            img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise Exception("Không thể đọc được ảnh (cv2.imdecode trả về None)")
                
            if engine_type == "paddleocr":
                result, elapse = reader(img)
                if result:
                    # Lọc các dòng có độ tin cậy > 30%
                    text_lines = [str(item[1]) for item in result if float(item[2]) > 0.3]
                    text = " ".join(text_lines)
            else:
                result = reader.readtext(img, detail=0)
                text = " ".join(result)
            ocr_results[filename] = text
        except Exception as e:
            print(f"\n[Lỗi] OCR thất bại trên ảnh {filename}: {e}")
            ocr_results[filename] = ""
            
    print("Đang tạo file SRT...")
    generate_srt(ocr_results, output_srt)
    print("Quá trình Local OCR hoàn tất!")

if __name__ == '__main__':
    main()
