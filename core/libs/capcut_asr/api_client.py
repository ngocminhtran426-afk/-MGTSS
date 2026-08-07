import os
import json
import requests
from capcut_common_task_client import (
    DEFAULT_DEVICE, upload_audio_file, build_request, checked_json_response
)

class CapCutAPI:
    def __init__(self):
        self.device = DEFAULT_DEVICE.copy()
        # Thay đổi region và language theo ý muốn
        self.device["region"] = "VN"
        self.device["loc"] = "VN"
        self.device["lan"] = "vi-VN"

    def process_audio_file(self, audio_path, language="vi-VN"):
        """Tải file âm thanh lên, trả về vid và md5"""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Không tìm thấy file: {audio_path}")
            
        return upload_audio_file(audio_path, self.device)

    def create_caption_task(self, upload_info, language="vi-VN"):
        """Gửi lệnh AI tạo phụ đề (STT)"""
        import argparse
        
        args = argparse.Namespace()
        args.mode = "stt-new"
        args.device_json = None
        args.audio_vid = upload_info["vid"]
        args.audio_md5 = upload_info["md5"]
        args.duration_ms = upload_info.get("duration_ms", 10000)
        args.language = language
        args.translation_language = "vi-VN"
        args.use_translation = False
        
        url, headers, body_text = build_request(args)
        
        resp = requests.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        return resp.json()

    def get_caption_result(self, task_id, token):
        """Kiểm tra tiến độ và lấy kết quả phụ đề"""
        import argparse
        
        args = argparse.Namespace()
        args.mode = "stt-query"
        args.device_json = None
        args.task_id = task_id
        args.token = token
        args.bind_id = ""
        
        url, headers, body_text = build_request(args)
        
        resp = requests.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60)
        return resp.json()
