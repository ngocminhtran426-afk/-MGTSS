import sys
import os
import time

def download_models():
    try:
        import easyocr
    except ImportError:
        print("easyocr not installed")
        return

    langs_to_download = [
        ['vi', 'en'],
        ['ch_sim', 'en']
    ]

    for langs in langs_to_download:
        success = False
        attempts = 0
        while not success and attempts < 10:
            attempts += 1
            print(f"\n[{attempts}/10] Đang tải mô hình cho ngôn ngữ: {langs}...")
            try:
                reader = easyocr.Reader(langs)
                print(f"-> Tải thành công mô hình cho {langs}!")
                success = True
            except Exception as e:
                print(f"-> Lỗi tải mô hình {langs} (Có thể do mạng): {e}")
                time.sleep(5)
                
        if not success:
            print(f"KHÔNG THỂ TẢI MÔ HÌNH {langs} SAU 10 LẦN THỬ!")

if __name__ == "__main__":
    download_models()
