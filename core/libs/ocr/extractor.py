import cv2
import numpy as np
import os
import sys
import subprocess
import time
import shutil
import glob

def process_video(video_path, output_dir, crop_coords=None):
    """
    Wrap VideoSubFinderWXW.exe (C++) để cắt ảnh.
    Tránh in log rác ra Console, giúp C# không bị treo.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    is_linux = sys.platform.startswith('linux')
    
    if is_linux:
        vsf_exe = os.path.join(os.path.dirname(__file__), "VideoSubFinderCli")
    else:
        vsf_exe = os.path.join(os.path.dirname(__file__), "VideoSubFinderWXW.exe")
        
    if not os.path.exists(vsf_exe):
        print(f"[ERROR] Không tìm thấy {vsf_exe}!")
        if is_linux:
            print("\n" + "="*60)
            print("GỢI Ý CÀI ĐẶT VIDEOSUBFINDER TRÊN GOOGLE COLAB (LINUX):")
            print("Bạn cần tải bản VideoSubFinderCli cho Linux về thư mục này.")
            print("Chạy các lệnh sau trong Colab:")
            print(f"!wget https://github.com/eritpchy/videosubfinder-cli/releases/download/v1.0.0/VideoSubFinderCli-Ubuntu-20.04.tar.gz -O vsf.tar.gz")
            print(f"!tar -xvf vsf.tar.gz -C {os.path.dirname(__file__)}")
            print(f"!chmod +x {vsf_exe}")
            print("="*60 + "\n")
        return

    # Xóa ảnh cũ trong thư mục TXTImages và RGBImages của VSF nếu có
    vsf_dir = os.path.dirname(vsf_exe)
    for folder in ["TXTImages", "RGBImages"]:
        tgt = os.path.join(vsf_dir, folder)
        if os.path.exists(tgt):
            shutil.rmtree(tgt)
        os.makedirs(tgt)

    # Tính toán tham số cắt cho VSF
    # crop_coords = [yMinPct (từ trên), yMaxPct (từ trên), xMinPct (từ trái), xMaxPct (từ trái)]
    if crop_coords:
        # VSF: -te và -be tính từ ĐÁY (bottom) lên! (ví dụ: yMin=0.8 từ trên => 0.2 từ đáy)
        te = 1.0 - crop_coords[0]
        be = 1.0 - crop_coords[1]
        # VSF: -le và -re tính từ TRÁI (left) sang!
        le = crop_coords[2]
        re = crop_coords[3]
    else:
        # Mặc định: Y từ 0.75 đến 0.95 (tính từ trên) => Từ đáy là 0.25 đến 0.05
        te = 0.25
        be = 0.05
        le = 0.0
        re = 1.0

    # Lệnh chạy VSF
    cmd = [
        vsf_exe,
        "-c", "-r",
        "-i", video_path,
        "-te", str(round(te, 3)),
        "-be", str(round(be, 3)),
        "-le", str(round(le, 3)),
        "-re", str(round(re, 3))
    ]

    print(f"Bắt đầu chạy VideoSubFinder C++ (Chạy ngầm)...")
    print(f"Vùng quét: Top {te*100:.1f}%, Bottom {be*100:.1f}%, Left {le*100:.1f}%, Right {re*100:.1f}%")
    print(f"[VSF] Phần mềm đang chạy ngầm bằng CPU. Xin vui lòng không tắt Tool...")
    print(f"[VSF] (Lưu ý: Quá trình này có thể tốn 5-15 phút tùy độ dài video)")
    
    # Chạy VSF
    process = subprocess.Popen(cmd, cwd=vsf_dir)
    
    # Do VSF tự động ẩn GUI khi có tham số dòng lệnh, ta phải in log định kỳ để báo cho người dùng
    start_wait = time.time()
    while process.poll() is None:
        elapsed = int(time.time() - start_wait)
        if elapsed > 0 and elapsed % 15 == 0:
            print(f"[VSF] Vẫn đang xử lý... ({elapsed} giây trôi qua)")
        time.sleep(1)
        
    print(f"[VSF] Đã hoàn thành quá trình xử lý C++!")
    
    # Copy ảnh từ RGBImages qua output_dir
    rgb_images = glob.glob(os.path.join(vsf_dir, "RGBImages", "*.jpeg")) + glob.glob(os.path.join(vsf_dir, "RGBImages", "*.jpg"))
    if not rgb_images:
        print("[WARN] VideoSubFinder không tìm thấy ảnh phụ đề nào, hoặc có lỗi xảy ra.")
    else:
        for img in rgb_images:
            shutil.copy(img, output_dir)
        print(f"Đã trích xuất xong {len(rgb_images)} ảnh màu (RGBImages) vào {output_dir}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Sử dụng: python extractor.py <video_path> <output_dir>")
    else:
        process_video(sys.argv[1], sys.argv[2])
