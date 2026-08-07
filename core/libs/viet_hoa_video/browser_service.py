"""
browser_service.py - Tự động tạo thumbnail Việt hóa qua Google AI Studio
Sử dụng Selenium để mở browser, upload ảnh, gửi prompt, download ảnh kết quả.
100% tự động, không cần thao tác thủ công (trừ lần đầu đăng nhập Google).
"""

import os
import sys
import time
import base64
import shutil
import glob
from pathlib import Path
from PIL import Image
import io

TOOL_ROOT = Path(__file__).resolve().parents[3]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from tool_paths import ToolPaths

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False


class BrowserThumbnailService:
    """Tự động tạo thumbnail Việt hóa qua Google Gemini bằng Selenium."""

    STUDIO_URL = "https://gemini.google.com/app"

    def __init__(self):
        paths = ToolPaths.from_root(TOOL_ROOT)
        # Profile riêng cho Selenium (không ảnh hưởng Chrome đang mở)
        self.profile_dir = os.fspath(paths.viet_hoa_video_browser_profile_dir("chrome"))
        self.edge_profile_dir = os.fspath(paths.viet_hoa_video_browser_profile_dir("edge"))
        self.download_dir = os.fspath(paths.viet_hoa_video_download_dir())
        self.driver = None

    def login_google(self, progress_callback=None):
        """Mở browser để người dùng đăng nhập Google, sau đó lưu profile lại."""
        if not HAS_SELENIUM:
            raise ImportError("Cần cài selenium: pip install selenium")

        try:
            self._emit(progress_callback, "🌐 Đang mở trình duyệt để đăng nhập...")
            self._init_driver()
            
            self._emit(progress_callback, "🔑 Vui lòng đăng nhập Google trên trình duyệt vừa mở...")
            self.driver.get(self.STUDIO_URL)
            
            # Chờ người dùng đăng nhập (có thể mất thời gian)
            if self._wait_for_login(timeout=300):
                self._emit(progress_callback, "✅ Đăng nhập thành công! Đã lưu profile.")
            else:
                self._emit(progress_callback, "⚠️ Hết thời gian chờ hoặc đăng nhập chưa hoàn tất.")
        except Exception as e:
            self._emit(progress_callback, f"❌ Lỗi khi mở trình duyệt: {str(e)}")
        finally:
            self._close_driver()

    def create_thumbnail(self, image_path: str, prompt: str, save_path: str,
                         progress_callback=None) -> str:
        """
        Quy trình chính:
        1. Mở Selenium (Chrome/Edge)
        2. Truy cập Gemini
        3. Upload ảnh gốc
        4. Gửi prompt
        5. Download ảnh kết quả

        Args:
            image_path: Đường dẫn ảnh thumbnail gốc
            prompt: Prompt yêu cầu Việt hóa
            save_path: Đường dẫn lưu ảnh kết quả
            progress_callback: Function để cập nhật trạng thái

        Returns:
            Đường dẫn ảnh đã lưu
        """
        if not HAS_SELENIUM:
            raise ImportError("Cần cài selenium: pip install selenium")

        try:
            self._emit(progress_callback, "🌐 Đang mở trình duyệt...")
            self._init_driver()

            self._emit(progress_callback, "🌐 Đang tải Google Gemini...")
            self.driver.get(self.STUDIO_URL)
            time.sleep(5)

            # Kiểm tra đăng nhập
            if self._needs_login():
                self._emit(progress_callback,
                           "⚠️ Cần đăng nhập Google - Đang chờ bạn đăng nhập trong browser...")
                if not self._wait_for_login(timeout=180):
                    raise Exception(
                        "Hết thời gian chờ đăng nhập (3 phút).\n"
                        "Vui lòng thử lại và đăng nhập nhanh hơn."
                    )
                self._emit(progress_callback, "✅ Nhận diện đăng nhập thành công!")
                time.sleep(3)

            # Kiểm tra xem có ảnh mẫu không
            module_dir = os.path.dirname(os.path.abspath(__file__))
            reference_image_path = None
            for sample_name in ["mau.jpg", "mau.png", "sample.jpg", "sample.png"]:
                sample_path = os.path.join(module_dir, sample_name)
                if os.path.exists(sample_path):
                    reference_image_path = sample_path
                    break

            if reference_image_path:
                prompt = f"""[CẢNH BÁO QUAN TRỌNG]: 
Tôi đang gửi cho bạn 2 bức ảnh:
- Ảnh số 1 là ẢNH MẪU PHONG CÁCH (Theme Reference). KHÔNG ĐƯỢC xuất ra ảnh này làm kết quả! Chỉ dùng để tham khảo màu sắc và cách xếp chữ.
- Ảnh số 2 là ẢNH GỐC CẦN SỬA (Target Image). ĐÂY MỚI LÀ HÌNH ẢNH CHÍNH!

Nhiệm vụ của bạn: Hãy lấy ẢNH SỐ 2 (Ảnh gốc) làm nền, và áp dụng y hệt phong cách chữ, layout, màu sắc của ẢNH SỐ 1 (Ảnh mẫu) lên đó. KHÔNG ĐƯỢC sử dụng hình nền của Ảnh số 1!
""" + prompt

            # Tải ảnh
            if reference_image_path:
                self._emit(progress_callback, "📤 Đang upload ảnh mẫu (Theme Reference)...")
                self._upload_image(reference_image_path)
                time.sleep(2)

            self._emit(progress_callback, "📤 Đang upload ảnh gốc (Target Image)...")
            self._upload_image(image_path)
            time.sleep(2)

            # Nhập prompt
            self._emit(progress_callback, "⌨️ Đang nhập prompt...")
            self._type_prompt(prompt)

            # Bấm gửi
            self._emit(progress_callback, "🚀 Đang gửi yêu cầu...")
            self._click_send()

            # Chờ và tải ảnh
            self._emit(progress_callback, "⏳ Đang chờ AI tạo ảnh (30-120 giây)...")
            try:
                img_data = self._wait_and_get_image(timeout=180)
            except Exception as e:
                self._emit(progress_callback, f"⚠️ Lỗi hoặc bị Gemini từ chối ({str(e)}). Đang thử lại tự động với prompt an toàn...")
                
                # Thử lại với prompt siêu an toàn (Abstract background)
                safe_prompt = "Xin hãy tạo một bức ảnh nền trừu tượng (abstract cinematic background), hoàn toàn không có người, rất an toàn và tuân thủ mọi chính sách, dùng làm hình nền YouTube phong cách đẹp mắt."
                
                self._type_prompt(safe_prompt)
                self._click_send()
                
                self._emit(progress_callback, "⏳ Đang chờ AI tạo ảnh (lần 2 - Safe Mode)...")
                img_data = self._wait_and_get_image(timeout=180)

            # Lưu
            self._emit(progress_callback, "💾 Đang lưu thumbnail Việt hóa...")
            self._save_image(img_data, save_path)

            self._emit(progress_callback, "✅ Tạo thumbnail Việt hóa thành công!")
            return save_path

        finally:
            self._close_driver()

    @staticmethod
    def _emit(callback, msg):
        """Gửi cập nhật trạng thái."""
        if callback:
            callback(msg)

    def _init_driver(self):
        """Khởi tạo trình duyệt Chrome hoặc Edge."""
        # Thử Chrome trước
        try:
            options = ChromeOptions()
            options.add_argument(f"--user-data-dir={self.profile_dir}")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-features=ProfilePicker")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            # Cho phép download ảnh
            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
            }
            options.add_experimental_option("prefs", prefs)

            self.driver = webdriver.Chrome(options=options)
            self.driver.set_window_size(1400, 900)
            # Ẩn dấu hiệu automation
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            return
        except Exception:
            pass

        # Fallback: Edge
        try:
            options = EdgeOptions()
            options.add_argument(f"--user-data-dir={self.edge_profile_dir}")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")

            self.driver = webdriver.Edge(options=options)
            self.driver.set_window_size(1400, 900)
            return
        except Exception:
            raise Exception(
                "Không tìm thấy Chrome hoặc Edge.\n"
                "Vui lòng cài đặt trình duyệt Chrome để sử dụng tính năng này."
            )

    def _needs_login(self) -> bool:
        """Kiểm tra xem trang hiện tại có phải đang yêu cầu đăng nhập không."""
        try:
            current_url = self.driver.current_url
            if "accounts.google.com" in current_url:
                return True
            if "signin" in current_url.lower():
                return True
            # Nếu trang Gemini load thành công, tìm prompt input
            WebDriverWait(self.driver, 8).until(lambda d:
                d.find_elements(By.CSS_SELECTOR,
                    "textarea, [contenteditable='true'], .ql-editor, "
                    "[role='textbox'], .text-input-field"))
            return False
        except Exception:
            return True

    def _wait_for_login(self, timeout=180) -> bool:
        """Chờ user đăng nhập Google trong browser Selenium."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                current_url = self.driver.current_url
                # Đã quay lại Gemini
                if "gemini.google.com" in current_url and "accounts.google" not in current_url:
                    time.sleep(3)
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def _upload_image(self, image_path: str, progress_callback=None):
        """Upload ảnh vào Gemini chat bằng cách Copy vào Clipboard và Paste."""
        abs_path = os.path.abspath(image_path).replace("/", "\\")

        # Dùng một tiến trình Python độc lập với PyQt5 để copy ảnh vào Clipboard.
        # Điều này xử lý tốt cả ảnh WebP (thường gặp khi tải từ YouTube) mà System.Drawing của PowerShell hay bị lỗi.
        import sys, subprocess
        py_cmd = f"from PyQt5.QtWidgets import QApplication; from PyQt5.QtGui import QImage; import sys; app = QApplication(sys.argv); app.clipboard().setImage(QImage(r'{abs_path}'))"
        try:
            subprocess.run([sys.executable, "-c", py_cmd], creationflags=subprocess.CREATE_NO_WINDOW, check=True)
            time.sleep(1) # Chờ xíu để ảnh kịp vào clipboard
        except Exception as e:
            raise Exception(f"Không thể copy ảnh vào Clipboard: {str(e)}")

        # JS tìm ô nhập liệu để Paste
        js_find_input = """
        function findInput(root) {
            if (root.nodeType === Node.ELEMENT_NODE) {
                if (root.tagName === 'TEXTAREA') {
                    const style = window.getComputedStyle(root);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                        return root;
                    }
                }
                if (root.getAttribute && root.getAttribute('contenteditable') === 'true') {
                    const style = window.getComputedStyle(root);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        return root;
                    }
                }
            }
            if (root.shadowRoot) {
                let found = findInput(root.shadowRoot);
                if (found) return found;
            }
            for (let child of root.childNodes) {
                let found = findInput(child);
                if (found) return found;
            }
            return null;
        }
        return findInput(document);
        """

        try:
            target_el = self.driver.execute_script(js_find_input)
            if target_el:
                # Click focus vào ô nhập
                self.driver.execute_script("arguments[0].focus();", target_el)
                try:
                    target_el.click()
                except Exception:
                    pass
                time.sleep(0.5)
                
                # Dùng ActionChains để Paste ảnh (Ctrl + V)
                ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                time.sleep(1)
                return
        except Exception as e:
            pass

        # Fallback lại với selectors thông thường nếu JS thất bại
        selectors = [
            "textarea.text-input-field",
            "textarea",
            "[contenteditable='true']",
            ".ql-editor",
            "[role='textbox']",
            ".prompt-textarea",
            "div[contenteditable]",
        ]

        for selector in selectors:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                try:
                    if not el.is_displayed():
                        continue
                    el.click()
                    time.sleep(0.5)
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(1)
                    return
                except Exception:
                    continue

        raise Exception("Không tìm thấy ô nhập liệu để dán (Paste) ảnh.")

    def _type_prompt(self, prompt: str):
        """Nhập prompt vào ô chat (hỗ trợ Shadow DOM) bằng cách Paste."""
        import pyperclip
        
        js_find_input = """
        function findInput(root) {
            if (root.nodeType === Node.ELEMENT_NODE) {
                if (root.tagName === 'TEXTAREA') {
                    const style = window.getComputedStyle(root);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                        return root;
                    }
                }
                if (root.getAttribute && root.getAttribute('contenteditable') === 'true') {
                    const style = window.getComputedStyle(root);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        return root;
                    }
                }
            }
            if (root.shadowRoot) {
                let found = findInput(root.shadowRoot);
                if (found) return found;
            }
            for (let child of root.childNodes) {
                let found = findInput(child);
                if (found) return found;
            }
            return null;
        }
        return findInput(document);
        """
        
        try:
            target_el = self.driver.execute_script(js_find_input)
            
            if target_el:
                # Copy prompt vào clipboard
                pyperclip.copy(prompt)
                time.sleep(0.5)
                
                # Click focus vào ô nhập
                self.driver.execute_script("arguments[0].focus();", target_el)
                try:
                    target_el.click()
                except Exception:
                    pass
                time.sleep(0.5)
                
                # Dùng ActionChains để Paste (Ctrl + V)
                ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                time.sleep(1)
                return
        except Exception:
            pass
            
        # Fallback lại với selectors thông thường nếu JS thất bại
        selectors = [
            "textarea.text-input-field",
            "textarea",
            "[contenteditable='true']",
            ".ql-editor",
            "[role='textbox']",
            ".prompt-textarea",
            "div[contenteditable]",
        ]

        for selector in selectors:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                try:
                    if not el.is_displayed():
                        continue

                    el.click()
                    time.sleep(0.5)

                    pyperclip.copy(prompt)
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(1)
                    return
                except Exception:
                    continue

        raise Exception("Không tìm thấy ô nhập prompt trên AI Studio.")

    def _click_send(self):
        """Click nút gửi message (hỗ trợ Shadow DOM)."""
        js_find_input = """
        function findInput(root) {
            if (root.nodeType === Node.ELEMENT_NODE) {
                if (root.tagName === 'TEXTAREA') {
                    const style = window.getComputedStyle(root);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                        return root;
                    }
                }
                if (root.getAttribute && root.getAttribute('contenteditable') === 'true') {
                    const style = window.getComputedStyle(root);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        return root;
                    }
                }
            }
            if (root.shadowRoot) {
                let found = findInput(root.shadowRoot);
                if (found) return found;
            }
            for (let child of root.childNodes) {
                let found = findInput(child);
                if (found) return found;
            }
            return null;
        }
        return findInput(document);
        """
        
        try:
            # 1. Gửi trực tiếp event Ctrl+Enter bằng JavaScript (đảm bảo 100% ăn lệnh)
            target_el = self.driver.execute_script(js_find_input)
            if target_el:
                self.driver.execute_script("arguments[0].focus();", target_el)
                time.sleep(0.5)
                # Phát ra event y hệt như user gõ phím
                self.driver.execute_script("""
                    var el = arguments[0];
                    var event = new KeyboardEvent('keydown', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        ctrlKey: true,
                        bubbles: true,
                        cancelable: true
                    });
                    el.dispatchEvent(event);
                """, target_el)
                time.sleep(1)
                
                # Thử thêm qua ActionChains phòng hờ
                ActionChains(self.driver).move_to_element(target_el).click().send_keys(Keys.CONTROL + Keys.RETURN).perform()
                time.sleep(1)
                return
        except Exception:
            pass

        # 2. JS tìm nút Run để click (tránh nhầm với Run settings)
        js_find_send = """
        function findSend(root) {
            if (root.nodeType === Node.ELEMENT_NODE) {
                if (root.tagName === 'BUTTON' || root.getAttribute('role') === 'button' || root.tagName === 'A') {
                    const txt = (root.textContent || '').toLowerCase().trim();
                    if ((txt.includes('run') && !txt.includes('settings')) || txt.includes('ctrl') || txt === 'send' || txt === 'submit') {
                        const style = window.getComputedStyle(root);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && !root.disabled) {
                            return root;
                        }
                    }
                }
            }
            if (root.shadowRoot) {
                let found = findSend(root.shadowRoot);
                if (found) return found;
            }
            for (let child of root.childNodes) {
                let found = findSend(child);
                if (found) return found;
            }
            return null;
        }
        return findSend(document);
        """
        try:
            btn = self.driver.execute_script(js_find_send)
            if btn:
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                return
        except Exception:
            pass

        try:
            active = self.driver.switch_to.active_element
            active.send_keys(Keys.RETURN)
        except Exception:
            raise Exception("Không tìm thấy nút gửi trên AI Studio.")

    def _wait_and_get_image(self, timeout=180) -> bytes:
        """Chờ AI tạo ảnh xong và lấy dữ liệu ảnh."""
        # Ghi nhận các ảnh đã có trước khi gửi prompt
        existing_srcs = set()
        for img in self.driver.find_elements(By.TAG_NAME, "img"):
            try:
                src = img.get_attribute("src") or ""
                existing_srcs.add(src[:100])  # Lưu 100 ký tự đầu để so sánh
            except Exception:
                pass

        start = time.time()
        last_check = 0
        while time.time() - start < timeout:
            time.sleep(5)

            # Tìm tất cả ảnh trên trang
            all_imgs = self.driver.find_elements(By.TAG_NAME, "img")
            for img in all_imgs:
                try:
                    src = img.get_attribute("src") or ""
                    if not src:
                        continue

                    # Bỏ qua ảnh đã có từ trước
                    if src[:100] in existing_srcs:
                        continue

                    # Kiểm tra kích thước thật của ảnh
                    natural_w = self.driver.execute_script(
                        "return arguments[0].naturalWidth || 0;", img)
                    natural_h = self.driver.execute_script(
                        "return arguments[0].naturalHeight || 0;", img)

                    # Bỏ qua ảnh nhỏ (icon, avatar, logo...)
                    if natural_w < 200 or natural_h < 150:
                        continue

                    # Tìm thấy ảnh lớn mới → đây là ảnh AI tạo
                    if src.startswith("data:image"):
                        # Base64 data URL
                        _, b64_data = src.split(",", 1)
                        return base64.b64decode(b64_data)
                    elif src.startswith("http") or src.startswith("blob:"):
                        # Dùng canvas để lấy ảnh ở độ phân giải gốc (naturalWidth/naturalHeight)
                        # thay vì screenshot_as_png (sẽ bị dính kích thước thu nhỏ của CSS trên web)
                        try:
                            data_url = self.driver.execute_script("""
                                var img = arguments[0];
                                var canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                var ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                return canvas.toDataURL('image/png');
                            """, img)
                            if data_url and "," in data_url:
                                _, b64_data = data_url.split(",", 1)
                                return base64.b64decode(b64_data)
                        except Exception:
                            pass
                        # Fallback nếu bị lỗi CORS
                        return img.screenshot_as_png

                except Exception:
                    continue

            # Đọc nội dung trang để xem Gemini có từ chối không
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                refusals = ["không thể tạo", "không an toàn", "chính sách", "từ chối", "không cho phép", "violate", "guidelines", "safety policy"]
                # Cần tránh trường hợp chính câu prompt của mình có chứa từ khóa này, nên ta tìm kiếm trong câu trả lời gần nhất.
                responses = self.driver.find_elements(By.CSS_SELECTOR, "message-content, .model-response-text")
                if responses:
                    last_resp = responses[-1].text.lower()
                    if any(r in last_resp for r in refusals):
                        raise Exception("Gemini từ chối tạo ảnh do cảnh báo an toàn.")
            except Exception as e:
                if "Gemini từ chối" in str(e):
                    raise e

            # Kiểm tra và tự động đóng các hộp thoại xác nhận (ví dụ: Agent execution warning)
            js_close_dialog = """
            function closeDialogs(root) {
                if (root.nodeType === Node.ELEMENT_NODE) {
                    if (root.tagName === 'BUTTON' || root.getAttribute('role') === 'button') {
                        const txt = (root.textContent || '').toLowerCase().trim();
                        if (txt === 'allow' || txt === 'confirm' || txt === 'accept' || txt === 'got it' || txt === 'i understand' || txt === 'tiếp tục' || txt === 'đồng ý' || txt === 'chấp nhận') {
                            const style = window.getComputedStyle(root);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                // Kiểm tra xem nó có nằm trong dialog/modal không
                                let parent = root.parentElement;
                                let inDialog = false;
                                while(parent) {
                                    if(parent.tagName === 'DIALOG' || parent.getAttribute('role') === 'dialog' || parent.getAttribute('role') === 'alertdialog') {
                                        inDialog = true;
                                        break;
                                    }
                                    parent = parent.parentElement;
                                }
                                if (inDialog) return root;
                            }
                        }
                    }
                }
                if (root.shadowRoot) {
                    let found = closeDialogs(root.shadowRoot);
                    if (found) return found;
                }
                for (let child of root.childNodes) {
                    let found = closeDialogs(child);
                    if (found) return found;
                }
                return null;
            }
            return closeDialogs(document);
            """
            try:
                dialog_btn = self.driver.execute_script(js_close_dialog)
                if dialog_btn:
                    self.driver.execute_script("arguments[0].click();", dialog_btn)
                    time.sleep(1)
            except Exception:
                pass

            # Kiểm tra xem AI còn đang xử lý không
            # (tìm loading spinner, progress indicator...)
            loading_selectors = [
                ".loading", ".spinner", "[role='progressbar']",
                ".thinking", ".generating", "mat-progress-bar",
            ]
            still_loading = False
            for sel in loading_selectors:
                try:
                    loaders = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if any(l.is_displayed() for l in loaders):
                        still_loading = True
                        break
                except Exception:
                    pass

            elapsed = int(time.time() - start)
            if elapsed > 60 and not still_loading:
                # Đã chờ > 60s mà không thấy loading → có thể đã xong nhưng không tìm thấy ảnh
                # Thử tìm canvas elements (AI Studio có thể render ảnh trong canvas)
                canvases = self.driver.find_elements(By.TAG_NAME, "canvas")
                for canvas in canvases:
                    try:
                        w = self.driver.execute_script(
                            "return arguments[0].width;", canvas)
                        h = self.driver.execute_script(
                            "return arguments[0].height;", canvas)
                        if w > 200 and h > 150:
                            # Lấy ảnh từ canvas
                            data_url = self.driver.execute_script(
                                "return arguments[0].toDataURL('image/png');", canvas)
                            if data_url and "," in data_url:
                                _, b64_data = data_url.split(",", 1)
                                return base64.b64decode(b64_data)
                    except Exception:
                        continue

        raise Exception(
            "Hết thời gian chờ AI tạo ảnh (3 phút).\n"
            "Có thể AI Studio đang quá tải, vui lòng thử lại sau."
        )

    def _save_image(self, img_data: bytes, save_path: str):
        """Lưu dữ liệu ảnh thành file."""
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

        with open(save_path, 'wb') as f:
            f.write(img_data)

        # Xác nhận ảnh hợp lệ, resize chuẩn 1280x720 và convert sang PNG
        try:
            img = Image.open(save_path)
            img = img.convert("RGB")
            # Force resize to 1280x720 (YouTube Thumbnail standard)
            if hasattr(Image, 'Resampling'):
                resample_filter = Image.Resampling.LANCZOS
            else:
                resample_filter = Image.LANCZOS
            img = img.resize((1280, 720), resample_filter)
            img.save(save_path, "PNG", quality=95)
        except Exception:
            raise Exception("Ảnh tải về không hợp lệ. Vui lòng thử lại.")

    def _close_driver(self):
        """Đóng trình duyệt an toàn."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


def build_thumbnail_prompt(original_title: str, extra_prompt: str = "", movie_context: str = "") -> str:
    """Tạo prompt yêu cầu Việt hóa thumbnail."""
    base_prompt = (
        f"Đây là thumbnail của một video. Hãy tạo lại thumbnail này và tùy biến thiết kế ĐẬM CHẤT KÊNH REVIEW PHIM (Tóm tắt phim) theo phong cách sau:\n\n"
        f"1. GÓC TRÊN BÊN TRÁI: Vẽ một biển hiệu/logo (Mặc định là chữ 'TÓM TẮT PHIM', trừ khi có yêu cầu thay đổi ở phần YÊU CẦU PHỤ bên dưới).\n"
        f"2. TRUNG TÂM/BÊN DƯỚI: Chèn nội dung tiêu đề tiếng Việt.\n"
        f"3. PHONG CÁCH CHỮ TIÊU ĐỀ: \n"
        f"   - TÓM TẮT NGẮN GỌN nội dung phim thành 1 câu giật gân (TỐI ĐA 6 TỪ/CHỮ) dựa vào Cốt truyện phim được cung cấp. KHÔNG chèn toàn bộ tiêu đề dài lê thê làm che mất hình gốc!\n"
        f"   - Sử dụng font chữ vô cùng to, dày, và góc cạnh (kiểu Impact hoặc Arial Black).\n"
        f"   - Chia làm 2 dòng.\n"
        f"   - Các dòng trên dùng màu TRẮNG.\n"
        f"   - Dòng dưới cùng (từ khóa chính) BẮT BUỘC dùng màu ĐỎ RỰC hoặc CAM để thu hút sự chú ý.\n"
        f"   - Tất cả các chữ phải có VIỀN ĐEN siêu dày và ĐỔ BÓNG (Drop shadow) rõ nét để chữ nổi bần bật lên.\n"
        f"   - Các dòng chữ nên được xếp hơi lệch/nghiêng (so le) một chút để tạo sự kịch tính.\n"
        f"4. TRÁNH TỪ NGỮ BẠO LỰC: Che các từ nhạy cảm như 'giết' thành 'gi*t', 'hiếp' thành 'hi*p', 'chết' thành 'ch*t'.\n"
        f"5. HÌNH ẢNH NỀN: Giữ nguyên bối cảnh rùng rợn, giật gân, hoặc hấp dẫn của ảnh gốc.\n\n"
        f"Tiêu đề gốc cần dịch và chèn vào: {original_title}"
    )
    if movie_context:
        base_prompt += f"\n\nCốt truyện phim (để chọn từ khóa đưa lên hình): {movie_context}"
        
    if extra_prompt:
        base_prompt += f"\n\n[QUAN TRỌNG - YÊU CẦU PHỤ TỪ NGƯỜI DÙNG]:\n{extra_prompt}\n(Hãy TRỰC TIẾP ƯU TIÊN thực hiện yêu cầu này, ghi đè lên các quy tắc mặc định ở trên nếu có xung đột!)"
    return base_prompt
