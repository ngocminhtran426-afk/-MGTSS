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
