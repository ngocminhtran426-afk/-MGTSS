import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication


class VietHoaAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_validate_url_normalizes_common_input(self):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "modules", "viet_hoa_video")))
        from app import MainWindow

        window = MainWindow()
        self.assertEqual(window._validate_url("youtube.com/watch?v=123"), "https://youtube.com/watch?v=123")
        self.assertEqual(window._validate_url(" https://youtu.be/abc "), "https://youtu.be/abc")
        with self.assertRaises(ValueError):
            window._validate_url("not a valid url")
        window.close()


if __name__ == "__main__":
    unittest.main()
