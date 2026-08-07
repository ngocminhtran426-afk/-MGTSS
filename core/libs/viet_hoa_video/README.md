# 🎬 Tool Việt Hóa Video (Tự Động & Chuẩn SEO)

Phần mềm Desktop (PyQt5) giúp các nhà sáng tạo nội dung tự động hóa quy trình Việt hóa video từ YouTube, Facebook, TikTok,... Phục vụ tối đa cho các kênh **Review Phim / Tóm Tắt Phim**.

## ✨ Tính Năng Nổi Bật

1. **Lấy Thông Tin Video (1-Click):**
   - Chỉ cần dán URL video, phần mềm tự động phân tích và tải về ảnh Thumbnail gốc độ phân giải cao (1280x720).
   - Trích xuất tự động Tiêu đề, Mô tả, Lượt xem, Thời lượng.

2. **Dịch Thuật & Tối Ưu SEO (Gemini AI):**
   - Dịch tiêu đề sang tiếng Việt tự động Viết Hoa Chữ Cái Đầu (Title Case) và tối ưu từ khóa SEO giật gân, thu hút.
   - Định dạng tiêu đề cực chuẩn: `[Review Phim] <Tiêu đề Video> | <Tên Kênh>`.
   - Dịch Mô tả video bám sát theo mẫu cố định chuẩn của kênh Review Phim, tự động quét và phân loại thể loại phim (Hành động, Viễn tưởng, Tâm lý,...).

3. **Tự Động Tạo Thumbnail Việt Hóa (3 Cấp Độ):**
   - **Cấp 1 (Gemini API):** Sử dụng `gemini-2.5-flash-image` kết hợp ảnh gốc và ảnh mẫu (`mau.png`) để áp dụng phong cách thiết kế sang ảnh mới.
   - **Cấp 2 (Trình duyệt ngầm Selenium):** Vượt giới hạn Quota của API bằng cách tự động mở trình duyệt Chrome/Edge ẩn, dán ảnh vào Google AI Studio, nhập prompt, chờ AI xử lý và bóc tách dữ liệu ảnh độ phân giải gốc cao nhất bằng Canvas HTML5.
   - **Cấp 3 (Pillow Fallback):** Nếu mạng lỗi hoặc AI từ chối, tự động vẽ chữ "TÓM TẮT PHIM", thêm viền (stroke), đổ bóng (drop shadow) và chèn tiêu đề tiếng Việt chuẩn màu kênh Review trực tiếp lên ảnh.
   - Kích thước luôn đảm bảo đúng chuẩn **1280x720** trước khi lưu.

4. **Tùy Chỉnh Nâng Cao:**
   - **Tên Kênh:** Tự do điền tên kênh để AI nối vào tiêu đề video.
   - **Prompt Phụ:** Cung cấp ghi đè lệnh cho AI (Ví dụ: "Thay logo chữ trên cùng bên trái thành MIN REVIEW PHIM"). Hệ thống sẽ ưu tiên lệnh này lên trên quy tắc mặc định.

5. **Lưu Trữ Tự Động:**
   - Đóng gói file văn bản `.txt`, file ảnh `.png` gọn gàng vào thư mục ngày giờ tự động.

## 🚀 Hướng Dẫn Cài Đặt

1. **Yêu cầu hệ thống:** Python 3.8+ và trình duyệt Google Chrome (hoặc Microsoft Edge).
2. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Các thư viện chính: PyQt5, google-genai, pillow, selenium, yt-dlp...)*

## 🖥️ Hướng Dẫn Sử Dụng

1. Chạy phần mềm:
   ```bash
   python main.py
   ```
2. Mở trình duyệt truy cập [Google AI Studio](https://aistudio.google.com/), lấy API Key và dán vào phần mềm (Phần mềm sẽ tự động lưu Key).
3. (Tùy chọn) Bấm nút **"Đăng nhập Google"** để đăng nhập sẵn tài khoản cho Chrome ẩn của Selenium nếu muốn dùng tính năng AI Studio Automation.
4. Dán link Video cần Việt hóa vào thanh URL.
5. Nhập Prompt phụ hoặc Tên Kênh nếu cần.
6. Nhấn **"Auto Việt Hóa (1-Click)"** hoặc "Việt Hóa" và chờ kết quả.
7. Nhấn **"Lưu Kết Quả"** để xuất file ra thư mục mong muốn.

## ⚙️ Tùy Chỉnh Ảnh Mẫu

Để AI tạo Thumbnail chuẩn phong cách kênh của bạn, hãy thiết kế một file ảnh mang tên `mau.png` hoặc `mau.jpg` lưu vào cùng thư mục chứa code (để AI tham khảo cách bố trí chữ, phối màu, logo...).

## 🛑 Lưu Ý
- **Giới hạn API:** Các mô hình tạo ảnh miễn phí của Google có thể giới hạn số lượng tạo. Hệ thống đã cài sẵn chế độ Selenium Automation và Pillow Fallback để không làm gián đoạn công việc của bạn.
