import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config import CREDENTIALS_FILE, TOKEN_FILE, SCOPES

def authenticate():
    """
    Xác thực Google API bằng OAuth2.0.
    Nếu đã có file token.json, sẽ sử dụng nó để làm mới session.
    Nếu chưa có, sẽ mở trình duyệt để người dùng đăng nhập.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Không tìm thấy file {CREDENTIALS_FILE}. Vui lòng tạo credentials trên Google Cloud Console và lưu vào thư mục hiện tại.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return creds

if __name__ == "__main__":
    print("Bắt đầu xác thực Google API...")
    creds = authenticate()
    if creds and creds.valid:
        print("Xác thực thành công! File token.json đã được lưu. Bạn có thể tắt cửa sổ này.")
    else:
        print("Xác thực thất bại.")
