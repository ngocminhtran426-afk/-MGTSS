"""
video_service.py - Trích xuất metadata video từ nhiều nền tảng
Sử dụng yt-dlp để hỗ trợ YouTube, TikTok, Facebook, Instagram, v.v.
"""

import os
import sys
import requests
import yt_dlp


class VideoService:
    """Service lấy metadata và thumbnail từ URL video."""

    def __init__(self):
        self.ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android']}},
        }
        if os.path.exists('cookies.txt'):
            self.ydl_opts['cookiefile'] = 'cookies.txt'
        elif sys.platform.startswith('win'):
            self.ydl_opts['cookiesfrombrowser'] = ('chrome',)

    def extract_metadata(self, url: str) -> dict:
        """
        Trích xuất metadata từ URL video.
        
        Returns:
            dict với các key: title, description, thumbnail_url, 
                  uploader, duration, platform, video_id
        """
        # Chuyển hướng cho TikTok, Douyin, Bilibili sang Douyin_TikTok_Download_API
        is_tiktok_douyin_bili = any(domain in url.lower() for domain in ['tiktok.com', 'douyin.com', 'bilibili.com'])
        
        if is_tiktok_douyin_bili:
            print("Đang gọi API Douyin_TikTok_Download_API để xử lý siêu tốc...")
            api_url = f"https://api.douyin.wtf/api/hybrid/video_data?url={url}&minimal=false"
            try:
                # Douyin WTF API không cần API Key, timeout 20s
                response = requests.get(api_url, timeout=20)
                data = response.json()
                
                if data.get("code") == 200:
                    video_data = data.get("data", {})
                    
                    # Lấy link mp4 không watermark chất lượng cao
                    nwm_video_url = video_data.get("video_data", {}).get("nwm_video_url_HQ")
                    if not nwm_video_url:
                         nwm_video_url = video_data.get("video_data", {}).get("nwm_video_url")
                         
                    # Lấy thông tin khác
                    title = video_data.get("desc", "Video")
                    cover = video_data.get("cover_data", {}).get("cover", {}).get("url_list", [""])[0]
                    author = video_data.get("author", {}).get("nickname", "Unknown")
                    
                    if nwm_video_url:
                        return {
                            'title': title,
                            'description': title,
                            'thumbnail_url': cover,
                            'uploader': author,
                            'duration': 0,
                            'platform': 'tiktok_douyin_api',
                            'video_id': video_data.get("aweme_id", ""),
                            'view_count': 0,
                            'url': url,
                            'direct_mp4_url': nwm_video_url
                        }
            except Exception as e:
                print(f"Lỗi khi gọi API api.douyin.wtf: {e}. Sẽ dùng yt-dlp dự phòng.")
        
        # Luồng cũ: YouTube hoặc khi API thất bại
        import subprocess
        import sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
            if 'yt_dlp' in sys.modules:
                del sys.modules['yt_dlp']
        except Exception:
            pass
            
        import yt_dlp
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Lấy thumbnail chất lượng cao nhất
            thumbnails = info.get('thumbnails', [])
            best_thumbnail = None
            if thumbnails:
                # Sắp xếp theo preference/resolution, lấy cái tốt nhất
                best_thumbnail = thumbnails[-1].get('url', '')
            
            # Fallback nếu không có list thumbnails
            if not best_thumbnail:
                best_thumbnail = info.get('thumbnail', '')

            return {
                'title': info.get('title', 'Không có tiêu đề'),
                'description': info.get('description', 'Không có mô tả'),
                'thumbnail_url': best_thumbnail,
                'uploader': info.get('uploader', 'Không rõ'),
                'duration': info.get('duration', 0),
                'platform': info.get('extractor', 'unknown'),
                'video_id': info.get('id', ''),
                'view_count': info.get('view_count', 0),
                'url': url,
            }

    def download_thumbnail(self, thumbnail_url: str, save_path: str) -> str:
        """
        Download thumbnail từ URL và lưu vào đường dẫn chỉ định.
        
        Args:
            thumbnail_url: URL của thumbnail
            save_path: Đường dẫn lưu file
            
        Returns:
            Đường dẫn file đã lưu
        """
        # Tạo thư mục nếu chưa có
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        response = requests.get(thumbnail_url, timeout=30, stream=True)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return save_path

    @staticmethod
    def format_duration(seconds: int) -> str:
        """Chuyển đổi giây thành HH:MM:SS."""
        if not seconds:
            return "0:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def format_views(count: int) -> str:
        """Format số lượt xem dễ đọc."""
        if not count:
            return "0"
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)
