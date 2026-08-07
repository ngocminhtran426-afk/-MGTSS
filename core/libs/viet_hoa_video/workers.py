"""
workers.py - Background workers chạy trên QThread
Để không block UI khi thực hiện các tác vụ nặng (network, AI).
"""

import os
from PyQt5.QtCore import QThread, pyqtSignal

from browser_service import BrowserThumbnailService, build_thumbnail_prompt
from video_service import VideoService
from gemini_service import GeminiService


class FetchMetadataWorker(QThread):
    """Worker lấy metadata video từ URL."""
    
    # Signals
    finished = pyqtSignal(dict)       # Metadata dict
    thumbnail_ready = pyqtSignal(str) # Đường dẫn thumbnail đã download
    error = pyqtSignal(str)           # Error message
    progress = pyqtSignal(str)        # Status message

    def __init__(self, url: str, output_dir: str):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.video_service = VideoService()

    def run(self):
        try:
            self.progress.emit("Đang lấy thông tin video...")
            metadata = self.video_service.extract_metadata(self.url)
            self.finished.emit(metadata)

            # Download thumbnail
            if metadata.get('thumbnail_url'):
                self.progress.emit("Đang tải thumbnail...")
                thumb_path = os.path.join(self.output_dir, "thumbnail_original.jpg")
                self.video_service.download_thumbnail(
                    metadata['thumbnail_url'], thumb_path
                )
                self.thumbnail_ready.emit(thumb_path)

            self.progress.emit("Hoàn tất lấy thông tin!")

        except Exception as e:
            self.error.emit(f"Lỗi: {str(e)}")


class TranslateWorker(QThread):
    """Worker dịch mô tả và tạo thumbnail Việt hóa."""
    
    # Signals
    title_translated = pyqtSignal(str)        # Tiêu đề đã dịch
    description_translated = pyqtSignal(str)  # Mô tả đã dịch
    thumbnail_created = pyqtSignal(str)       # Đường dẫn thumbnail mới
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    step_progress = pyqtSignal(int)           # Phần trăm hoàn thành (0-100)

    def __init__(self, api_key: str, title: str, description: str,
                 thumbnail_path: str, output_dir: str, extra_prompt: str = "",
                 channel_name: str = ""):
        super().__init__()
        self.api_key = api_key
        self.title = title
        self.description = description
        self.thumbnail_path = thumbnail_path
        self.output_dir = output_dir
        self.extra_prompt = extra_prompt
        self.channel_name = channel_name

    def run(self):
        try:
            gemini = GeminiService(self.api_key)

            # Bước 1: Dịch tiêu đề
            self.progress.emit("Đang dịch tiêu đề...")
            self.step_progress.emit(10)
            translated_title = gemini.translate_title(self.title, self.channel_name)
            self.title_translated.emit(translated_title)
            self.step_progress.emit(30)

            # Bước 2: Dịch mô tả
            self.progress.emit("Đang dịch mô tả...")
            translated_desc = gemini.translate_description(self.description)
            self.description_translated.emit(translated_desc)
            self.step_progress.emit(50)

            # Bước 3: Tạo thumbnail Việt hóa qua Gemini trên trình duyệt
            if self.thumbnail_path and os.path.exists(self.thumbnail_path):
                viet_thumb_path = os.path.join(self.output_dir, "thumbnail_viet.png")
                self.progress.emit("🌐 Đang tạo thumbnail bằng Gemini trên trình duyệt...")
                self.step_progress.emit(70)

                prompt = build_thumbnail_prompt(self.title, self.extra_prompt)
                browser = BrowserThumbnailService()
                browser.create_thumbnail(
                    self.thumbnail_path,
                    prompt,
                    viet_thumb_path,
                    progress_callback=self.progress.emit
                )

                self.thumbnail_created.emit(viet_thumb_path)
                self.step_progress.emit(95)

            self.progress.emit("✅ Việt hóa hoàn tất!")
            self.step_progress.emit(100)

        except Exception as e:
            self.error.emit(f"Lỗi AI: {str(e)}")
