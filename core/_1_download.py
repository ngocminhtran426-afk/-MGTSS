import os
import sys

# Ensure libs can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from libs.viet_hoa_video.video_service import VideoService
from utils.decorator import except_handler, check_file_exists
from utils.config_utils import load_key

@except_handler(retry=3, delay=2)
def download_video_metadata(url: str, download: bool = True):
    """
    Trích xuất metadata và tải video từ URL.
    Wrapper gọi VideoService từ thư viện cũ.
    """
    print(f"Bắt đầu lấy metadata cho URL: {url}")
    service = VideoService()
    metadata = service.extract_metadata(url)
    print(f"Đã lấy thông tin: {metadata.get('title')}")
    
    if download:
        import yt_dlp
        import os
        
        # Ensure download directory exists
        download_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        print(f"Đang tải video từ URL: {url}")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(download_dir, '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': True,
            'extractor_args': {'youtube': ['client=ANDROID,IOS,WEB']},
        }
        
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        else:
            ydl_opts['cookiesfrombrowser'] = ('chrome',)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download the video
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            metadata['video_path'] = video_path
            print(f"Đã tải video thành công: {video_path}")
            
    return metadata
