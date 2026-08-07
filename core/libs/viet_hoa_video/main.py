"""
main.py - Entry point cho Tool Việt Hóa Video
Khởi tạo app, apply dark theme, hiển thị main window.
"""

import sys
import os

# Đảm bảo import được các module trong cùng thư mục
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

try:
    import qdarktheme
    HAS_DARK_THEME = True
except ImportError:
    HAS_DARK_THEME = False

from app import MainWindow


def main():
    """Khởi chạy ứng dụng."""
    app = QApplication(sys.argv)

    # Set app metadata
    app.setApplicationName("Tool Việt Hóa Video")
    app.setOrganizationName("VietHoa")

    # Apply dark theme
    if HAS_DARK_THEME:
        app.setStyleSheet(qdarktheme.load_stylesheet())
    else:
        # Fallback dark palette nếu không có pyqtdarktheme
        app.setStyleSheet("""
            QWidget {
                background-color: #0d0d1a;
                color: #e0e0f0;
            }
        """)

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
