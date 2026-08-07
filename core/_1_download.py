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
    import subprocess
    import sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
        if 'yt_dlp' in sys.modules:
            del sys.modules['yt_dlp']
    except Exception as e:
        print(f"Warning: Không thể cập nhật yt-dlp: {e}")

    print(f"Bắt đầu lấy metadata cho URL: {url}")
    service = VideoService()
    metadata = service.extract_metadata(url)
    print(f"Đã lấy thông tin: {metadata.get('title')}")
    
    if download:
        download_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        # Nếu metadata trả về có link tải trực tiếp từ Douyin_TikTok_Download_API
        if metadata.get('direct_mp4_url'):
            print(f"Đã lấy được link tải trực tiếp từ API. Tiến hành tải file bằng requests...")
            direct_url = metadata['direct_mp4_url']
            video_id = metadata.get('video_id', 'video_tiktok')
            out_filepath = os.path.join(download_dir, f"{video_id}.mp4")
            
            try:
                import requests
                response = requests.get(direct_url, stream=True, timeout=30)
                response.raise_for_status()
                
                with open(out_filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f"Tải file thành công: {out_filepath}")
                metadata['video_path'] = out_filepath
                return metadata
            except Exception as e:
                print(f"Lỗi khi tải file qua API trực tiếp: {e}. Đang thử lại bằng yt-dlp...")
        
        print(f"Tiến hành tải file bằng yt-dlp...")
        import subprocess
        import sys
        import yt_dlp
        
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
            if 'yt_dlp' in sys.modules:
                del sys.modules['yt_dlp']
        except Exception as e:
            print(f"Warning: Không thể cập nhật yt-dlp: {e}")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(download_dir, '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android']}},
        }
        
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        elif sys.platform.startswith('win'):
            ydl_opts['cookiesfrombrowser'] = ('chrome',)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download the video
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            metadata['video_path'] = video_path
            print(f"Đã tải video thành công: {video_path}")
            
    return metadata
