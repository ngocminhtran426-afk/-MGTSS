"""
app.py - Giao diện chính Tool Việt Hóa Video
Desktop app với PyQt5 + dark theme.
"""

import os
import sys
import json
import shutil
import webbrowser
import re
from datetime import datetime
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[3]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from tool_paths import ToolPaths
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QProgressBar,
    QGroupBox, QFileDialog, QMessageBox, QSplitter, QFrame,
    QSizePolicy, QApplication
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont, QIcon, QFontDatabase

from workers import FetchMetadataWorker, TranslateWorker


PATHS = ToolPaths.from_root(TOOL_ROOT)


class MainWindow(QMainWindow):
    """Cửa sổ chính của Tool Việt Hóa Video."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 Tool Việt Hóa Video")
        self.setMinimumSize(950, 750)
        self.resize(1050, 850)

        # State
        self.current_metadata = None
        self.original_thumb_path = None
        self.viet_thumb_path = None
        self.output_dir = os.fspath(PATHS.viet_hoa_video_output_dir())
        os.makedirs(self.output_dir, exist_ok=True)

        # Config file path (lưu API key)
        self.config_path = os.fspath(PATHS.viet_hoa_video_config_file())

        # Workers
        self.fetch_worker = None
        self.translate_worker = None

        # Build UI
        self._setup_fonts()
        self._build_ui()
        self._load_config()
        self._apply_custom_styles()

    def _setup_fonts(self):
        """Thiết lập font chữ."""
        self.title_font = QFont("Segoe UI", 11, QFont.Bold)
        self.label_font = QFont("Segoe UI", 10)
        self.small_font = QFont("Segoe UI", 9)

    def _build_ui(self):
        """Xây dựng giao diện."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 16, 20, 16)

        # === HEADER ===
        header = self._create_header()
        main_layout.addWidget(header)

        # === API KEY SECTION ===
        api_group = self._create_api_section()
        main_layout.addWidget(api_group)

        # === URL INPUT SECTION ===
        url_group = self._create_url_section()
        main_layout.addWidget(url_group)

        # === CONTENT AREA (Thumbnails + Text) ===
        content_splitter = QSplitter(Qt.Vertical)

        # Thumbnail comparison
        thumb_group = self._create_thumbnail_section()
        content_splitter.addWidget(thumb_group)

        # Text sections (title + description)
        text_group = self._create_text_section()
        content_splitter.addWidget(text_group)

        content_splitter.setStretchFactor(0, 2)
        content_splitter.setStretchFactor(1, 3)
        main_layout.addWidget(content_splitter, 1)

        # === BOTTOM BAR (Progress + Actions) ===
        bottom = self._create_bottom_bar()
        main_layout.addWidget(bottom)

    def _create_header(self) -> QWidget:
        """Tạo header."""
        frame = QFrame()
        frame.setObjectName("headerFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)

        title = QLabel("🎬 Tool Việt Hóa Video")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setObjectName("headerTitle")
        layout.addWidget(title)

        layout.addStretch()

        subtitle = QLabel("Tải metadata • Dịch mô tả • Tạo thumbnail Việt")
        subtitle.setFont(self.small_font)
        subtitle.setObjectName("headerSubtitle")
        layout.addWidget(subtitle)

        return frame

    def _create_api_section(self) -> QGroupBox:
        """Tạo section nhập API key."""
        group = QGroupBox("🔑 Gemini API Key")
        group.setFont(self.label_font)
        layout = QHBoxLayout(group)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Nhập API key từ Google AI Studio...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setFont(self.label_font)
        layout.addWidget(self.api_key_input, 1)

        self.toggle_key_btn = QPushButton("👁")
        self.toggle_key_btn.setFixedWidth(40)
        self.toggle_key_btn.setToolTip("Hiện/Ẩn API key")
        self.toggle_key_btn.clicked.connect(self._toggle_api_key_visibility)
        layout.addWidget(self.toggle_key_btn)

        self.save_key_btn = QPushButton("💾 Lưu Key")
        self.save_key_btn.setFont(self.label_font)
        self.save_key_btn.setObjectName("accentButton")
        self.save_key_btn.clicked.connect(self._save_config)
        layout.addWidget(self.save_key_btn)

        self.test_key_btn = QPushButton("🔍 Test")
        self.test_key_btn.setFont(self.label_font)
        self.test_key_btn.clicked.connect(self._test_api_key)
        layout.addWidget(self.test_key_btn)

        self.login_gg_btn = QPushButton("🌐 Đăng nhập Google")
        self.login_gg_btn.setFont(self.label_font)
        self.login_gg_btn.setToolTip("Đăng nhập Google cho trình duyệt ẩn của Selenium")
        self.login_gg_btn.clicked.connect(self._login_google_selenium)
        layout.addWidget(self.login_gg_btn)

        return group

    def _create_url_section(self) -> QGroupBox:
        """Tạo section nhập URL video."""
        group = QGroupBox("🔗 URL Video")
        group.setFont(self.label_font)
        layout = QHBoxLayout(group)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Dán link YouTube, Douyin, TikTok, Facebook... vào đây")
        self.url_input.setFont(self.label_font)
        self.url_input.returnPressed.connect(self._fetch_metadata)
        layout.addWidget(self.url_input, 1)

        self.fetch_btn = QPushButton("🚀 Tải thông tin")
        self.fetch_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.fetch_btn.setObjectName("primaryButton")
        self.fetch_btn.setMinimumWidth(150)
        self.fetch_btn.setToolTip("Tải metadata và thumbnail từ URL")
        self.fetch_btn.clicked.connect(self._fetch_metadata)
        layout.addWidget(self.fetch_btn)

        return group

    def _create_thumbnail_section(self) -> QGroupBox:
        """Tạo section hiển thị thumbnail."""
        group = QGroupBox("🖼️ Thumbnail")
        group.setFont(self.label_font)
        layout = QHBoxLayout(group)
        layout.setSpacing(20)

        # Thumbnail gốc
        left_box = QVBoxLayout()
        left_label = QLabel("📷 Thumbnail Gốc")
        left_label.setFont(self.title_font)
        left_label.setAlignment(Qt.AlignCenter)
        left_box.addWidget(left_label)

        self.original_thumb_label = QLabel("Chưa có thumbnail")
        self.original_thumb_label.setFixedSize(400, 225)
        self.original_thumb_label.setAlignment(Qt.AlignCenter)
        self.original_thumb_label.setObjectName("thumbnailPlaceholder")
        self.original_thumb_label.setScaledContents(False)
        left_box.addWidget(self.original_thumb_label, alignment=Qt.AlignCenter)
        layout.addLayout(left_box)

        # Arrow
        arrow = QLabel("  ➡️  ")
        arrow.setFont(QFont("Segoe UI", 24))
        arrow.setAlignment(Qt.AlignCenter)
        layout.addWidget(arrow)

        # Thumbnail Việt hóa
        right_box = QVBoxLayout()
        right_label = QLabel("🇻🇳 Thumbnail Việt Hóa")
        right_label.setFont(self.title_font)
        right_label.setAlignment(Qt.AlignCenter)
        right_box.addWidget(right_label)

        self.viet_thumb_label = QLabel("Chờ Việt hóa...")
        self.viet_thumb_label.setFixedSize(400, 225)
        self.viet_thumb_label.setAlignment(Qt.AlignCenter)
        self.viet_thumb_label.setObjectName("thumbnailPlaceholder")
        self.viet_thumb_label.setScaledContents(False)
        right_box.addWidget(self.viet_thumb_label, alignment=Qt.AlignCenter)

        # Buttons dưới thumbnail Việt hóa
        viet_btn_layout = QHBoxLayout()
        self.open_studio_btn = QPushButton("🌐 Tạo trên AI Studio")
        self.open_studio_btn.setFont(self.small_font)
        self.open_studio_btn.setObjectName("accentButton")
        self.open_studio_btn.setToolTip("Mở Google AI Studio để tạo thumbnail thủ công")
        self.open_studio_btn.setEnabled(False)
        self.open_studio_btn.clicked.connect(self._open_ai_studio)
        viet_btn_layout.addWidget(self.open_studio_btn)

        self.import_thumb_btn = QPushButton("📂 Import Thumbnail")
        self.import_thumb_btn.setFont(self.small_font)
        self.import_thumb_btn.setObjectName("accentButton")
        self.import_thumb_btn.setToolTip("Import ảnh thumbnail đã tạo từ AI Studio")
        self.import_thumb_btn.clicked.connect(self._import_thumbnail)
        viet_btn_layout.addWidget(self.import_thumb_btn)

        right_box.addLayout(viet_btn_layout)
        layout.addLayout(right_box)

        return group

    def _create_text_section(self) -> QWidget:
        """Tạo section tiêu đề + mô tả."""
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setSpacing(10)

        # Row 0: Tiêu đề
        layout.addWidget(self._make_label("📝 Tiêu đề gốc:"), 0, 0)
        self.title_original = QLineEdit()
        self.title_original.setFont(self.label_font)
        self.title_original.setReadOnly(True)
        self.title_original.setPlaceholderText("Tiêu đề video sẽ hiện ở đây...")
        layout.addWidget(self.title_original, 0, 1)

        layout.addWidget(self._make_label("🇻🇳 Tiêu đề Việt:"), 1, 0)
        self.title_viet = QLineEdit()
        self.title_viet.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.title_viet.setPlaceholderText("Tiêu đề tiếng Việt sẽ hiện ở đây...")
        layout.addWidget(self.title_viet, 1, 1)

        # Row 2-3: Mô tả
        layout.addWidget(self._make_label("📄 Mô tả gốc:"), 2, 0, Qt.AlignTop)
        self.desc_original = QTextEdit()
        self.desc_original.setFont(self.small_font)
        self.desc_original.setReadOnly(True)
        self.desc_original.setPlaceholderText("Mô tả video sẽ hiện ở đây...")
        self.desc_original.setMaximumHeight(100)
        layout.addWidget(self.desc_original, 2, 1)

        layout.addWidget(self._make_label("🇻🇳 Mô tả Việt:"), 3, 0, Qt.AlignTop)
        self.desc_viet = QTextEdit()
        self.desc_viet.setFont(self.small_font)
        self.desc_viet.setPlaceholderText("Mô tả tiếng Việt sẽ hiện ở đây...")
        self.desc_viet.setMaximumHeight(100)
        layout.addWidget(self.desc_viet, 3, 1)

        # Row 4: Extra prompt
        layout.addWidget(self._make_label("📝 Prompt phụ (Tùy chọn):"), 4, 0, Qt.AlignTop)
        self.extra_prompt = QTextEdit()
        self.extra_prompt.setPlaceholderText("Ví dụ: đổi chữ 'ken review phim' thành 'min review phim'...")
        self.extra_prompt.setFont(self.small_font)
        self.extra_prompt.setPlaceholderText("VD: đổi chữ 'ken review phim' thành 'min review phim'...")
        self.extra_prompt.setMaximumHeight(50)
        layout.addWidget(self.extra_prompt, 4, 1)

        # Row 5: Channel Name
        layout.addWidget(self._make_label("📺 Tên kênh (Tùy chọn):"), 5, 0)
        self.channel_name = QLineEdit()
        self.channel_name.setFont(self.label_font)
        self.channel_name.setPlaceholderText("Nhập tên kênh (nếu có)")
        layout.addWidget(self.channel_name, 5, 1)

        # Info row
        self.info_label = QLabel("Chưa có dữ liệu video. Hãy dán URL và bấm Tải thông tin.")
        self.info_label.setFont(self.small_font)
        self.info_label.setObjectName("infoLabel")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label, 6, 0, 1, 2)

        layout.setColumnStretch(1, 1)
        return widget

    def _create_bottom_bar(self) -> QWidget:
        """Tạo thanh bottom với progress bar và buttons."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 0)

        # Progress bar
        progress_layout = QHBoxLayout()
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setFont(self.small_font)
        self.status_label.setObjectName("statusLabel")
        progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(22)
        progress_layout.addWidget(self.progress_bar, 1)
        layout.addLayout(progress_layout)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.vietnamize_btn = QPushButton("Việt hóa")
        self.vietnamize_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.vietnamize_btn.setObjectName("primaryButton")
        self.vietnamize_btn.setMinimumSize(170, 42)
        self.vietnamize_btn.setEnabled(False)
        self.vietnamize_btn.clicked.connect(self._start_translate)
        btn_layout.addWidget(self.vietnamize_btn)

        self.save_btn = QPushButton("💾 Lưu Kết Quả")
        self.save_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.save_btn.setObjectName("accentButton")
        self.save_btn.setMinimumSize(160, 42)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_results)
        btn_layout.addWidget(self.save_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    def _make_label(self, text: str) -> QLabel:
        """Tạo label với font chuẩn."""
        label = QLabel(text)
        label.setFont(self.label_font)
        label.setMinimumWidth(120)
        return label

    # ==================== STYLES ====================

    def _apply_custom_styles(self):
        """Apply custom CSS styles cho giao diện đẹp hơn."""
        self.setStyleSheet("""
            /* Header */
            #headerFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f3460);
                border-radius: 10px;
                margin-bottom: 4px;
            }
            #headerTitle {
                color: #e94560;
                letter-spacing: 1px;
            }
            #headerSubtitle {
                color: #a0a0b0;
            }

            /* Thumbnail placeholders */
            #thumbnailPlaceholder {
                background-color: #1a1a2e;
                border: 2px dashed #333355;
                border-radius: 8px;
                color: #666688;
                font-size: 13px;
            }

            /* Primary button */
            #primaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #e94560, stop:1 #c23152);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
            }
            #primaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ff5577, stop:1 #e94560);
            }
            #primaryButton:pressed {
                background: #a02040;
            }
            #primaryButton:disabled {
                background: #444455;
                color: #888899;
            }

            /* Accent button */
            #accentButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f3460, stop:1 #16213e);
                color: #e0e0ff;
                border: 1px solid #334477;
                border-radius: 8px;
                padding: 8px 20px;
            }
            #accentButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a4580, stop:1 #1a3050);
                border-color: #5566aa;
            }
            #accentButton:disabled {
                background: #333344;
                color: #666677;
                border-color: #333344;
            }

            /* Input fields */
            QLineEdit, QTextEdit {
                border: 1px solid #333355;
                border-radius: 6px;
                padding: 6px 10px;
                background-color: #12121e;
                color: #e0e0f0;
                selection-background-color: #e94560;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #e94560;
            }

            /* Group boxes */
            QGroupBox {
                font-weight: bold;
                border: 1px solid #2a2a44;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 16px;
                background-color: rgba(20, 20, 35, 0.5);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                color: #e0e0f0;
            }

            /* Progress bar */
            QProgressBar {
                border: 1px solid #333355;
                border-radius: 6px;
                text-align: center;
                background-color: #12121e;
                color: #e0e0f0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e94560, stop:1 #ff6b81);
                border-radius: 5px;
            }

            /* Status label */
            #statusLabel {
                color: #a0a0c0;
            }

            /* Info label */
            #infoLabel {
                color: #8aa6c7;
                font-style: italic;
                padding-top: 2px;
            }

            /* Scrollbar */
            QScrollBar:vertical {
                background: #12121e;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #333355;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #e94560;
            }
        """)

    # ==================== CONFIG ====================

    def _load_config(self):
        """Load cấu hình đã lưu."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    api_key = config.get('api_key', '')
                    if api_key:
                        self.api_key_input.setText(api_key)
        except Exception:
            pass

    def _save_config(self):
        """Lưu cấu hình."""
        try:
            config = {
                'api_key': self.api_key_input.text().strip()
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self._set_status("💾 Đã lưu API key!")
        except Exception as e:
            self._set_status(f"❌ Lỗi lưu config: {e}")

    # ==================== ACTIONS ====================

    def _toggle_api_key_visibility(self):
        """Toggle hiện/ẩn API key."""
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setText("🔒")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setText("👁")

    def _test_api_key(self):
        """Test API key."""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Thiếu API Key", "Vui lòng nhập API key trước!")
            return

        self._set_status("🔍 Đang test API key...")
        QApplication.processEvents()

        from gemini_service import GeminiService
        service = GeminiService(api_key)
        if service.test_connection():
            self._set_status("✅ API key hợp lệ!")
            QMessageBox.information(self, "Thành công", "API key hoạt động tốt! ✅")
        else:
            self._set_status("❌ API key không hợp lệ!")
            QMessageBox.critical(self, "Lỗi", "API key không hợp lệ hoặc đã hết hạn!")

    def _validate_url(self, raw_url: str) -> str:
        """Normalize and validate a user-supplied media URL."""
        cleaned = (raw_url or "").strip()
        if not cleaned:
            raise ValueError("Vui lòng nhập URL video!")

        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
            cleaned = f"https://{cleaned}"

        if any(domain in cleaned.lower() for domain in ["youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "douyin.com"]):
            return cleaned

        raise ValueError("URL không được hỗ trợ hoặc không hợp lệ.")

    def _fetch_metadata(self):
        """Bắt đầu lấy metadata video."""
        try:
            url = self._validate_url(self.url_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Thiếu URL", str(exc))
            return

        self.url_input.setText(url)
        self._reset_results()
        self.fetch_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._set_status("🔎 Đang lấy thông tin video...")

        self.fetch_worker = FetchMetadataWorker(url, self.output_dir)
        self.fetch_worker.finished.connect(self._on_metadata_received)
        self.fetch_worker.thumbnail_ready.connect(self._on_thumbnail_downloaded)
        self.fetch_worker.error.connect(self._on_fetch_error)
        self.fetch_worker.progress.connect(self._set_status)
        self.fetch_worker.start()

    def _on_metadata_received(self, metadata: dict):
        """Callback khi nhận được metadata."""
        self.current_metadata = metadata
        self.title_original.setText(metadata.get('title', ''))
        self.desc_original.setPlainText(metadata.get('description', ''))

        # Info
        from video_service import VideoService
        duration = VideoService.format_duration(metadata.get('duration', 0))
        views = VideoService.format_views(metadata.get('view_count', 0))
        platform = metadata.get('platform', 'unknown').capitalize()
        uploader = metadata.get('uploader', '')
        self.info_label.setText(
            f"📺 {platform}  •  👤 {uploader}  •  ⏱️ {duration}  •  👁️ {views} lượt xem"
        )

        self.vietnamize_btn.setEnabled(True)
        self.open_studio_btn.setEnabled(True)
        self.fetch_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

    def _on_thumbnail_downloaded(self, path: str):
        """Callback khi thumbnail đã download xong."""
        self.original_thumb_path = path
        self._display_thumbnail(self.original_thumb_label, path)
        
        # Tự động bắt đầu Việt Hóa ngay lập tức (1-click flow)
        self._start_translate()

    def _on_fetch_error(self, error_msg: str):
        """Callback khi lấy metadata lỗi."""
        self.fetch_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._set_status(f"❌ {error_msg}")
        QMessageBox.critical(self, "Lỗi", error_msg)

    def _start_translate(self):
        """Bắt đầu dịch và tạo thumbnail Việt hóa."""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Thiếu API Key",
                                "Vui lòng nhập Gemini API key trước!")
            return

        if not self.current_metadata:
            QMessageBox.warning(self, "Thiếu thông tin",
                                "Vui lòng lấy thông tin video trước!")
            return

        # Disable buttons
        self.vietnamize_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Start worker
        self.translate_worker = TranslateWorker(
            api_key=api_key,
            title=self.current_metadata.get('title', ''),
            description=self.current_metadata.get('description', ''),
            thumbnail_path=self.original_thumb_path,
            output_dir=self.output_dir,
            extra_prompt=self.extra_prompt.toPlainText().strip(),
            channel_name=self.channel_name.text().strip()
        )
        self.translate_worker.title_translated.connect(self._on_title_translated)
        self.translate_worker.description_translated.connect(self._on_desc_translated)
        self.translate_worker.thumbnail_created.connect(self._on_viet_thumbnail_created)
        self.translate_worker.error.connect(self._on_translate_error)
        self.translate_worker.progress.connect(self._set_status)
        self.translate_worker.step_progress.connect(self.progress_bar.setValue)
        self.translate_worker.start()

    def _on_title_translated(self, title: str):
        """Callback khi tiêu đề đã dịch."""
        self.title_viet.setText(title)

    def _on_desc_translated(self, desc: str):
        """Callback khi mô tả đã dịch."""
        self.desc_viet.setPlainText(desc)
        self.save_btn.setEnabled(True)

    def _on_viet_thumbnail_created(self, path: str):
        """Callback khi thumbnail Việt hóa đã tạo."""
        self.viet_thumb_path = path
        self._display_thumbnail(self.viet_thumb_label, path)
        self.vietnamize_btn.setEnabled(True)

    def _on_translate_error(self, error_msg: str):
        """Callback khi dịch lỗi."""
        self.vietnamize_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._set_status(f"❌ {error_msg}")
        browser_hint = (
            "\n\nNếu lỗi xảy ra ở bước tạo thumbnail, hãy kiểm tra đăng nhập Google "
            "trong trình duyệt Selenium rồi thử lại."
        )
        QMessageBox.critical(self, "Lỗi AI", f"{error_msg}{browser_hint}")

    def _save_results(self):
        """Lưu kết quả ra thư mục người dùng chọn."""
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu kết quả", os.path.expanduser("~")
        )
        if not folder:
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_dir = os.path.join(folder, f"viethoa_{timestamp}")
            os.makedirs(save_dir, exist_ok=True)

            # Lưu thumbnail gốc
            if self.original_thumb_path and os.path.exists(self.original_thumb_path):
                shutil.copy2(self.original_thumb_path,
                             os.path.join(save_dir, "thumbnail_original.jpg"))

            # Lưu thumbnail Việt hóa
            if self.viet_thumb_path and os.path.exists(self.viet_thumb_path):
                shutil.copy2(self.viet_thumb_path,
                             os.path.join(save_dir, "thumbnail_viet.png"))

            # Lưu text info
            info = {
                'url': self.current_metadata.get('url', '') if self.current_metadata else '',
                'title_original': self.title_original.text(),
                'title_viet': self.title_viet.text(),
                'description_original': self.desc_original.toPlainText(),
                'description_viet': self.desc_viet.toPlainText(),
                'platform': self.current_metadata.get('platform', '') if self.current_metadata else '',
                'saved_at': timestamp,
            }
            with open(os.path.join(save_dir, "info.json"), 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)

            # Lưu mô tả dạng text dễ đọc
            with open(os.path.join(save_dir, "mo_ta_viet.txt"), 'w', encoding='utf-8') as f:
                f.write(f"TIÊU ĐỀ: {self.title_viet.text()}\n\n")
                f.write(f"MÔ TẢ:\n{self.desc_viet.toPlainText()}\n")

            self._set_status(f"💾 Đã lưu vào: {save_dir}")
            QMessageBox.information(self, "Thành công",
                                    f"Đã lưu kết quả vào:\n{save_dir}")

        except Exception as e:
            QMessageBox.critical(self, "Lỗi lưu file", str(e))

    # ==================== AI STUDIO & IMPORT ====================

    def _open_ai_studio(self):
        """Tự động tạo thumbnail qua AI Studio bằng Selenium."""
        if not self.original_thumb_path or not os.path.exists(self.original_thumb_path):
            QMessageBox.warning(self, "Thiếu thumbnail",
                                "Vui lòng lấy thông tin video trước!")
            return

        title = self.title_original.text() or "video"

        # Disable buttons
        self.open_studio_btn.setEnabled(False)
        self.vietnamize_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        # Start browser worker
        from browser_service import BrowserThumbnailService, build_thumbnail_prompt

        extra_prompt = self.extra_prompt.toPlainText().strip()

        self._browser_worker = BrowserThumbnailWorker(
            image_path=self.original_thumb_path,
            prompt=build_thumbnail_prompt(title, extra_prompt),
            save_path=os.path.join(self.output_dir, "thumbnail_viet.png"),
        )
        self._browser_worker.finished.connect(self._on_browser_thumbnail_done)
        self._browser_worker.error.connect(self._on_browser_thumbnail_error)
        self._browser_worker.progress.connect(self._set_status)
        self._browser_worker.start()

    def _on_browser_thumbnail_done(self, path: str):
        """Callback khi browser automation tạo thumbnail xong."""
        self.viet_thumb_path = path
        self._display_thumbnail(self.viet_thumb_label, path)
        self.save_btn.setEnabled(True)
        self.open_studio_btn.setEnabled(True)
        self.vietnamize_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._set_status("✅ Tạo thumbnail Việt hóa qua AI Studio thành công!")

    def _on_browser_thumbnail_error(self, error_msg: str):
        """Callback khi browser automation lỗi."""
        self.open_studio_btn.setEnabled(True)
        self.vietnamize_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._set_status(f"❌ {error_msg}")
        QMessageBox.critical(self, "Lỗi Browser", error_msg)

    def _login_google_selenium(self):
        """Mở browser để đăng nhập Google và lưu session."""
        self.login_gg_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self._login_worker = BrowserLoginWorker()
        self._login_worker.finished.connect(self._on_login_done)
        self._login_worker.error.connect(self._on_login_error)
        self._login_worker.progress.connect(self._set_status)
        self._login_worker.start()

    def _on_login_done(self):
        self.login_gg_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        QMessageBox.information(self, "Thành công", "Đã lưu đăng nhập Google cho Selenium!")

    def _on_login_error(self, error_msg: str):
        self.login_gg_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self._set_status(f"❌ Lỗi đăng nhập: {error_msg}")
        QMessageBox.warning(self, "Lỗi đăng nhập", error_msg)

    def _import_thumbnail(self):
        """Import thumbnail Việt hóa từ file đã tải về (thủ công)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh thumbnail Việt hóa",
            os.path.expanduser("~/Downloads"),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not file_path:
            return

        save_path = os.path.join(self.output_dir, "thumbnail_viet.png")
        shutil.copy2(file_path, save_path)

        self.viet_thumb_path = save_path
        self._display_thumbnail(self.viet_thumb_label, save_path)
        self.save_btn.setEnabled(True)
        self._set_status("✅ Đã import thumbnail Việt hóa!")

    # ==================== HELPERS ====================

    def _display_thumbnail(self, label: QLabel, path: str):
        """Hiển thị ảnh thumbnail trên QLabel."""
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label.setPixmap(scaled)
        else:
            label.setText("⚠️ Không thể hiển thị ảnh")

    def _set_status(self, message: str):
        """Cập nhật status bar."""
        self.status_label.setText(message)
        QApplication.processEvents()

    def _reset_results(self):
        """Reset tất cả kết quả."""
        self.current_metadata = None
        self.original_thumb_path = None
        self.viet_thumb_path = None
        self.title_original.clear()
        self.title_viet.clear()
        self.desc_original.clear()
        self.desc_viet.clear()
        self.extra_prompt.clear()
        self.channel_name.clear()
        self.info_label.clear()
        self.original_thumb_label.setText("Chưa có thumbnail")
        self.original_thumb_label.setPixmap(QPixmap())
        self.viet_thumb_label.setText("Chờ Việt hóa...")
        self.viet_thumb_label.setPixmap(QPixmap())
        self.vietnamize_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.progress_bar.setValue(0)


class BrowserThumbnailWorker(QThread):
    """Worker chạy Selenium browser automation ở background."""

    finished = pyqtSignal(str)   # Đường dẫn thumbnail đã tạo
    error = pyqtSignal(str)      # Error message
    progress = pyqtSignal(str)   # Status message

    def __init__(self, image_path: str, prompt: str, save_path: str):
        super().__init__()
        self.image_path = image_path
        self.prompt = prompt
        self.save_path = save_path

    def run(self):
        try:
            from browser_service import BrowserThumbnailService
            browser = BrowserThumbnailService()
            result = browser.create_thumbnail(
                self.image_path,
                self.prompt,
                self.save_path,
                progress_callback=self.progress.emit
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class BrowserLoginWorker(QThread):
    """Worker mở browser cho user đăng nhập Google."""
    
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    
    def run(self):
        try:
            from browser_service import BrowserThumbnailService
            browser = BrowserThumbnailService()
            browser.login_google(progress_callback=self.progress.emit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
