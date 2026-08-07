import os

# Thư mục cơ bản
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')
PROGRESS_FILE = os.path.join(BASE_DIR, 'logs', 'progress.json')

# Google API Scopes
SCOPES = ['https://www.googleapis.com/auth/drive']

# Cấu hình đa luồng và tải
MAX_WORKERS = 5 # Số luồng OCR đồng thời (để 5 để tránh rate limit của Google)
MAX_RETRIES = 3 # Số lần thử lại nếu gặp lỗi mạng

# Hàm khởi tạo các thư mục cần thiết
def init_dirs(input_dir, output_dir):
    log_dir = os.path.join(BASE_DIR, 'logs')
    for d in [input_dir, output_dir, log_dir]:
        if not os.path.exists(d):
            os.makedirs(d)
