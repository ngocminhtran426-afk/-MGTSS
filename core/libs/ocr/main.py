import argparse
import os
import glob
from config import init_dirs
from auth import authenticate
from drive import get_drive_service
from docs import get_docs_service
from ocr import process_images_multithread
from srt import generate_srt
from extractor import process_video

def main():
    parser = argparse.ArgumentParser(description="Google Docs OCR & Hardsub Extractor")
    parser.add_argument('--video', type=str, help="Đường dẫn đến file video MP4 (Nên truyền vào nếu muốn tự động trích xuất ảnh)")
    parser.add_argument('--image_dir', type=str, help="Thư mục chứa ảnh (Nếu truyền --video, ảnh sẽ được trích xuất vào đây)")
    parser.add_argument('--out_srt', type=str, required=True, help="Đường dẫn xuất file SRT đầu ra")
    parser.add_argument('--crop', type=str, help="Tọa độ cắt ảnh: y_min,y_max,x_min,x_max (VD: 0.75,0.95,0.0,1.0)")
    
    args = parser.parse_args()
    
    input_dir = args.image_dir or os.path.join(os.path.dirname(args.out_srt), "GoogleDocsOCR_images")
    output_srt = args.out_srt
    
    # Khởi tạo các thư mục (logs,...)
    init_dirs(input_dir, os.path.dirname(output_srt))
    
    # Nếu có cờ --video, chạy trích xuất ảnh trước
    if args.video:
        print("Đang khởi động tiến trình trích xuất phụ đề (Computer Vision)...")
        # Xóa ảnh cũ nếu có
        for f in glob.glob(os.path.join(input_dir, '*.jpeg')):
            os.remove(f)
            
        crop_coords = None
        if args.crop:
            try:
                crop_coords = tuple(map(float, args.crop.split(',')))
            except:
                print("Lỗi định dạng --crop, sẽ dùng mặc định")
                
        process_video(args.video, input_dir, crop_coords=crop_coords)
    
    # Lấy tất cả ảnh JPEG/PNG
    image_files = glob.glob(os.path.join(input_dir, '*.jpeg')) + glob.glob(os.path.join(input_dir, '*.jpg')) + glob.glob(os.path.join(input_dir, '*.png'))
    if not image_files:
        print(f"Không tìm thấy file ảnh nào trong thư mục: {input_dir}")
        import sys
        sys.exit(0)
        
    # Xác thực OAuth 2.0
    print("Đang xác thực Google API...")
    creds = authenticate()
    
    # Chạy OCR đa luồng
    print(f"Bắt đầu xử lý OCR cho {len(image_files)} ảnh...")
    ocr_results = process_images_multithread(image_files, creds)
    
    # Gom nhóm và xuất file SRT
    print("Đang tạo file SRT...")
    generate_srt(ocr_results, output_srt)
    
    print("Quá trình Google Docs OCR hoàn tất!")

if __name__ == '__main__':
    main()
