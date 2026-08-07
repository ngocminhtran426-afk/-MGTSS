import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from converter import create_srt_from_chunks
import os

# Đây là Class chạy ngầm để gọi API (tránh đơ UI)
class APITaskThread(QThread):
    finished_signal = Signal(bool, str)
    log_signal = Signal(str)

    def __init__(self, video_path, language):
        super().__init__()
        self.video_path = video_path
        self.language = language

    def run(self):
        self.log_signal.emit("Bắt đầu xử lý...")
        self.log_signal.emit(f"Video: {self.video_path}")
        self.log_signal.emit(f"Ngôn ngữ: {self.language}")
        
        try:
            self.log_signal.emit(f"Bắt đầu xử lý...\nVideo: {self.video_path}\nNgôn ngữ: {self.language}")
            
            # Map ngôn ngữ
            lang_map = {
                "Việt Nam": "vi-VN",
                "Trung Quốc": "zh-CN",
                "Tiếng Anh": "en-US",
                "Nhật Bản": "ja-JP",
                "Hàn Quốc": "ko-KR"
            }
            lang_code = lang_map.get(self.language, "vi-VN")
            
            from api_client import CapCutAPI
            from converter import create_srt_from_chunks
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import subprocess
            import time
            import os
            import re
            
            api = CapCutAPI()
            
            self.log_signal.emit("1. Đang quét siêu tốc video để tìm khoảng lặng (dùng FFmpeg)...")
            
            # Quét khoảng lặng bằng FFmpeg (Rất nhanh, không cần load lên RAM)
            cmd_silence = [
                "ffmpeg", "-i", self.video_path, "-vn", 
                "-af", "silencedetect=noise=-30dB:d=0.5", 
                "-f", "null", "-"
            ]
            # Cần chạy ẩn cửa sổ console trên Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            result = subprocess.run(cmd_silence, capture_output=True, text=True, encoding="utf-8", startupinfo=startupinfo)
            output = result.stderr
            
            # Lấy thời lượng tổng
            dur_match = re.search(r"Duration:\s+(\d+):(\d+):([\d\.]+)", output)
            total_duration_s = 0
            if dur_match:
                h, m, s = dur_match.groups()
                total_duration_s = int(h)*3600 + int(m)*60 + float(s)
            
            if total_duration_s == 0:
                raise Exception("Không thể đọc được thời lượng video. Có thể file bị lỗi.")
            
            # Lấy khoảng lặng
            starts = re.findall(r"silence_start:\s+([\d\.]+)", output)
            ends = re.findall(r"silence_end:\s+([\d\.]+)", output)
            silences = [(float(s), float(e)) for s, e in zip(starts, ends)]
            
            chunk_target_s = 300 # 5 phút
            chunks = []
            
            self.log_signal.emit("2. Đang tính toán nhát cắt...")
            if total_duration_s <= chunk_target_s:
                chunks.append({"start_s": 0.0, "end_s": total_duration_s})
            else:
                current_start = 0.0
                while current_start < total_duration_s:
                    target_cut = current_start + chunk_target_s
                    if target_cut >= total_duration_s:
                        chunks.append({"start_s": current_start, "end_s": total_duration_s})
                        break
                        
                    best_cut = target_cut
                    if silences:
                        min_diff = float('inf')
                        for s, e in silences:
                            mid = (s + e) / 2
                            if current_start < mid < total_duration_s:
                                diff = abs(mid - target_cut)
                                if diff < min_diff:
                                    min_diff = diff
                                    best_cut = mid
                    
                    # Nếu không tìm thấy khoảng lặng phù hợp (hoặc không có khoảng lặng nào)
                    # thì ép buộc cắt ngay tại mốc 5 phút
                    if best_cut - current_start < 60:
                        best_cut = target_cut
                        
                    chunks.append({"start_s": current_start, "end_s": best_cut})
                    current_start = best_cut
            
            self.log_signal.emit(f"   -> Đã tính xong: cắt thành {len(chunks)} đoạn nhỏ.")
            
            # 3. Hàm xử lý 1 chunk
            def process_chunk(idx, chunk_data):
                start_s = chunk_data["start_s"]
                end_s = chunk_data["end_s"]
                
                chunk_file = os.path.splitext(self.video_path)[0] + f"_chunk_{idx}.mp3"
                
                # Trích xuất đoạn mp3 nhỏ từ video gốc
                self.log_signal.emit(f"   [Đoạn {idx+1}] Bắt đầu tách âm thanh ({end_s - start_s:.1f}s)...")
                cmd_extract = [
                    "ffmpeg", "-y", "-i", self.video_path,
                    "-ss", str(start_s), "-to", str(end_s),
                    "-vn", "-acodec", "libmp3lame", "-q:a", "5",
                    chunk_file
                ]
                subprocess.run(cmd_extract, capture_output=True, startupinfo=startupinfo)
                
                if not os.path.exists(chunk_file):
                    raise Exception(f"Lỗi khi tách MP3 đoạn {idx+1}")
                
                self.log_signal.emit(f"   [Đoạn {idx+1}] Đã tách xong, tải lên CapCut...")
                upload_info = api.process_audio_file(chunk_file)
                
                self.log_signal.emit(f"   [Đoạn {idx+1}] Ra lệnh AI...")
                submit_resp = api.create_caption_task(upload_info, lang_code)
                tasks = submit_resp.get("data", {}).get("tasks", [])
                if not tasks:
                    raise Exception(f"Submit đoạn {idx+1} thất bại")
                
                task_id = tasks[0]["id"]
                token = tasks[0]["token"]
                
                for i in range(120): # Tối đa 10 phút chờ
                    query_resp = api.get_caption_result(task_id, token)
                    task_list = query_resp.get("data", {}).get("tasks", [])
                    if task_list:
                        status = task_list[0].get("status")
                        if status in ["succeed", "success"]:
                            self.log_signal.emit(f"   [Đoạn {idx+1}] ✅ AI xử lý xong!")
                            try: os.remove(chunk_file)
                            except: pass
                            # Converter yêu cầu offset_ms (milliseconds)
                            return {"offset_ms": int(start_s * 1000), "json_data": query_resp}
                        elif status == "failed":
                            raise Exception(f"AI xử lý đoạn {idx+1} thất bại")
                    time.sleep(5)
                raise Exception(f"Hết thời gian chờ đoạn {idx+1}")

            # 4. Chạy song song
            self.log_signal.emit("3. Bắt đầu đẩy nhiều luồng xử lý song song lên server...")
            chunk_results = []
            has_error = False
            error_msg = ""
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for i, c in enumerate(chunks):
                    futures.append(executor.submit(process_chunk, i, c))
                
                for future in as_completed(futures):
                    try:
                        chunk_results.append(future.result())
                    except Exception as exc:
                        has_error = True
                        error_msg = str(exc)
            
            if has_error:
                raise Exception(f"Quá trình đa luồng thất bại: {error_msg}")
            
            self.log_signal.emit("4. Đang gộp phụ đề...")
            out_path = os.path.splitext(self.video_path)[0] + ".srt"
            success, msg = create_srt_from_chunks(chunk_results, out_path)
            
            if success:
                self.finished_signal.emit(True, msg)
            else:
                self.finished_signal.emit(False, msg)
                
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CapCut ASR Tool - Auto Subtitle")
        self.resize(500, 400)

        # Biến lưu trữ
        self.video_path = ""

        # Giao diện chính
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        main_widget.setLayout(layout)

        # 1. Chọn Video
        video_layout = QHBoxLayout()
        self.lbl_video = QLabel("Chưa chọn video")
        btn_browse = QPushButton("Chọn video...")
        btn_browse.clicked.connect(self.browse_video)
        video_layout.addWidget(btn_browse)
        video_layout.addWidget(self.lbl_video, stretch=1)
        layout.addLayout(video_layout)

        # 2. Chọn Ngôn ngữ
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Ngôn ngữ video:"))
        self.cb_language = QComboBox()
        self.cb_language.addItems(["Trung Quốc", "Tiếng Anh", "Tiếng Việt", "Tự động phát hiện"])
        lang_layout.addWidget(self.cb_language, stretch=1)
        layout.addLayout(lang_layout)

        # 3. Log
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        # 4. Nút Tạo phụ đề
        self.btn_generate = QPushButton("Tạo phụ đề (SRT)")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.clicked.connect(self.generate_subtitle)
        layout.addWidget(self.btn_generate)

        self.apply_style()

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f2f5;
            }
            QPushButton {
                background-color: #1890ff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #40a9ff;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #d9d9d9;
                border-radius: 4px;
                padding: 4px;
            }
            QLabel {
                font-size: 13px;
            }
        """)

    def browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn Video", "", "Video Files (*.mp4 *.mkv *.avi *.mov)"
        )
        if file_path:
            self.video_path = file_path
            self.lbl_video.setText(os.path.basename(file_path))

    def log(self, message):
        self.log_box.append(message)

    def generate_subtitle(self):
        if not self.video_path:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn video trước!")
            return

        self.btn_generate.setEnabled(False)
        self.log_box.clear()
        
        language = self.cb_language.currentText()
        
        # Khởi chạy luồng gọi API
        self.api_thread = APITaskThread(self.video_path, language)
        self.api_thread.log_signal.connect(self.log)
        self.api_thread.finished_signal.connect(self.on_api_finished)
        self.api_thread.start()

    def on_api_finished(self, success, message):
        self.btn_generate.setEnabled(True)
        if success:
            self.log("✅ HOÀN THÀNH:")
            self.log(message)
            QMessageBox.information(self, "Thành công", message)
        else:
            self.log("❌ LỖI:")
            self.log(message)
            QMessageBox.critical(self, "Lỗi", message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
