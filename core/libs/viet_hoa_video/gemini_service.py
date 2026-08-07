"""
gemini_service.py - Tích hợp Google Gemini AI
Dịch mô tả video và tạo thumbnail Việt hóa.
"""

import os
import io
import base64
from PIL import Image
from google import genai
from google.genai import types


class GeminiService:
    """Service tích hợp Gemini AI để dịch và tạo ảnh."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.text_model = "gemini-3.1-flash-lite"
        self.image_model = "gemini-2.5-flash-image"

    def set_api_key(self, api_key: str):
        """Cập nhật API key mới."""
        self.client = genai.Client(api_key=api_key)

    def summarize_srt_chunk(self, text_chunk: str) -> str:
        """Tóm tắt một đoạn phụ đề."""
        if not text_chunk.strip():
            return ""
        prompt = f"""Dưới đây là một phần của phụ đề phim. Hãy tóm tắt ngắn gọn (3-5 câu) các sự kiện chính và bối cảnh diễn ra trong đoạn này:
{text_chunk}"""
        try:
            response = self.client.models.generate_content(
                model=self.text_model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception:
            return ""

    def summarize_overall_context(self, chunk_summaries: list) -> str:
        """Tổng hợp cốt truyện từ các tóm tắt cục bộ."""
        if not chunk_summaries:
            return ""
        combined_text = "\n\n".join(chunk_summaries)
        prompt = f"""Dựa vào danh sách tóm tắt của từng phân đoạn phim dưới đây, hãy viết một đoạn tóm tắt tổng thể toàn bộ cốt truyện, điểm hấp dẫn và nhân vật chính của phim:
{combined_text}"""
        try:
            response = self.client.models.generate_content(
                model=self.text_model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception:
            return ""

    def translate_title(self, title: str, channel_name: str = "", movie_context: str = "") -> str:
        """
        Dịch tiêu đề video sang tiếng Việt và tối ưu SEO dựa trên ngữ cảnh phim.
        Định dạng: [Review Phim] Tên Video Tối Ưu SEO | Tên Kênh
        """
        prompt = f"""Bạn là chuyên gia SEO YouTube và chuyên gia đặt tiêu đề video hấp dẫn.

Hãy tạo một tiêu đề tiếng Việt chuẩn SEO cho video này. Yêu cầu BẮT BUỘC:
1. Viết hoa chữ cái đầu tiên của mỗi từ (Capitalize Each Word) để chuẩn SEO và thu hút.
2. Dịch tự nhiên, không dịch máy.
3. Tối ưu hóa SEO cho YouTube (chọn từ khóa có lượng tìm kiếm cao, gây tò mò, hấp dẫn).
4. Phải dựa sát vào Nội dung/Cốt truyện phim được cung cấp bên dưới để đặt một cái tên giật gân, cuốn hút nhất.
5. TRÁNH CÁC TỪ NGỮ BẠO LỰC NHẠY CẢM: Hãy tự động che dấu hoa thị (*) vào các từ nhạy cảm như "giết" thành "gi*t", "hiếp" thành "hi*p", "chết" thành "ch*t", v.v. để không bị vi phạm chính sách của YouTube.
6. KHÔNG giải thích thêm, CHỈ in ra ĐÚNG 1 DÒNG kết quả.
7. Định dạng kết quả BẮT BUỘC PHẢI LÀ:
"""
        if channel_name:
            prompt += f"[Review Phim] <Tiêu đề đã dịch và tối ưu SEO> | {channel_name}\n"
        else:
            prompt += f"[Review Phim] <Tiêu đề đã dịch và tối ưu SEO>\n"

        prompt += f"\nTiêu đề gốc: {title}"
        if movie_context:
            prompt += f"\nNội dung/Cốt truyện phim (tham khảo): {movie_context}"

        response = self.client.models.generate_content(
            model=self.text_model,
            contents=prompt,
        )
        return response.text.strip()

    def shorten_title_for_thumbnail(self, title: str) -> str:
        """
        Rút gọn tiêu đề thành một câu rất ngắn (3-6 chữ) giật gân để chèn vào Thumbnail.
        """
        if not title:
            return ""
            
        prompt = f"""Bạn là một YouTuber chuyên nghiệp.
Hãy rút gọn tiêu đề sau thành MỘT CÂU DUY NHẤT thật ngắn gọn, giật gân, siêu thu hút để in to lên Thumbnail (Ảnh bìa video).
Yêu cầu:
- TỐI ĐA 6 TỪ (chữ). Càng ngắn càng tốt.
- Phải mang tính tò mò, giật gân (Ví dụ: "NUỐT CHỬNG MẶT TRỜI!", "QUÁ KHỦNG KHIẾP!", "BÍ ẨN KINH HOÀNG!").
- TRÁNH CÁC TỪ NGỮ BẠO LỰC NHẠY CẢM: Tự động dùng dấu sao (*) để che các từ nhạy cảm như "giết" (thành "GI*T"), "hiếp" (thành "HI*P"), "chết" (thành "CH*T") để tránh vi phạm.
- KHÔNG thêm dấu ngoặc kép hay giải thích. Chỉ in ra kết quả.

Tiêu đề gốc: {title}"""

        try:
            response = self.client.models.generate_content(
                model=self.text_model,
                contents=prompt,
            )
            return response.text.strip().replace('"', '').upper()
        except:
            # Fallback nếu lỗi: Lấy 5 từ đầu tiên + "..."
            words = title.split()
            return " ".join(words[:5]).upper() + ("..." if len(words) > 5 else "")

    def translate_description(self, description: str, movie_context: str = "") -> str:
        """
        Dịch mô tả video sang tiếng Việt.
        """
        if not description or description.strip() == '':
            return "Không có mô tả"

        # Giới hạn độ dài mô tả để tránh token limit
        max_chars = 5000
        truncated = description[:max_chars]
        if len(description) > max_chars:
            truncated += "..."

        prompt = f"""Bạn là chuyên gia review phim và dịch nội dung video.

Dựa vào mô tả gốc của video dưới đây, hãy tìm thông tin tên phim, năm phát hành, thể loại và tạo ra một phần MÔ TẢ CHUẨN THEO ĐÚNG MẪU SAU ĐÂY.
Yêu cầu BẮT BUỘC:
- CHỈ xuất ra nội dung theo đúng mẫu dưới đây, KHÔNG giải thích thêm.
- Tự động tìm tên phim và điền vào [Tên phim] và [TênPhimViếtLiềnKhôngDấu] ở phần hashtag.
- Tự động tìm năm phát hành điền vào [Năm phát hành]. Nếu không thấy, có thể bỏ qua phần năm.
- Chọn ra 1 đến 4 thể loại phù hợp nhất với phim này (ví dụ: Hành động, Tâm lý, Kinh dị...) và liệt kê ở phần Thể loại.

=== MẪU BẮT BUỘC ===
🎬 **Tên phim:** [Tên phim] ([Năm phát hành])

Trong video hôm nay, chúng ta sẽ cùng khám phá toàn bộ nội dung của **[Tên phim]** – từ cốt truyện, các tình tiết quan trọng, những cú twist bất ngờ cho đến ý nghĩa mà bộ phim muốn truyền tải. Nếu bạn yêu thích những bộ phim có chiều sâu hoặc muốn nắm được toàn bộ nội dung trước khi xem, đây sẽ là video dành cho bạn.

⚠️ **Lưu ý:** Video có tiết lộ nội dung (Spoiler).

Nếu thấy video hữu ích, đừng quên:
👍 Like
💬 Bình luận cảm nhận của bạn
🔔 Đăng ký kênh để không bỏ lỡ những video review phim mới nhất.

━━━━━━━━━━━━━━

📚 Thể loại:
• [Thể loại 1]
• [Thể loại 2]
• [Thể loại 3]

━━━━━━━━━━━━━━
📢 Đây là video mang tính chất tóm tắt, phân tích và bình luận nhằm mục đích chia sẻ góc nhìn về tác phẩm.

#ReviewPhim #TomTatPhim #[TênPhimViếtLiềnKhôngDấu] #MovieReview #Recap
=====================
"""
        
        if movie_context:
            prompt += f"\n\nTHAM KHẢO CỐT TRUYỆN PHIM TỪ PHỤ ĐỀ (giúp xác định tên và thể loại chuẩn xác hơn):\n{movie_context}"

        prompt += f"\n\nMô tả gốc của video:\n{truncated}"

        response = self.client.models.generate_content(
            model=self.text_model,
            contents=prompt,
        )
        return response.text.strip()

    def create_vietnamese_thumbnail(self, image_path: str, original_title: str,
                                     vietnamese_title: str, save_path: str) -> str:
        """
        Tạo thumbnail mới với text tiếng Việt dựa trên thumbnail gốc.
        Thử Gemini trước, nếu lỗi quota thì dùng Pillow fallback.
        
        Args:
            image_path: Đường dẫn ảnh thumbnail gốc
            original_title: Tiêu đề gốc (để hiểu ngữ cảnh)
            vietnamese_title: Tiêu đề đã dịch sang tiếng Việt
            save_path: Đường dẫn lưu thumbnail mới
            
        Returns:
            Đường dẫn file thumbnail mới
        """
        # Thử dùng Gemini image generation trước
        try:
            return self._create_thumbnail_gemini(image_path, original_title, save_path)
        except Exception as e:
            error_msg = str(e)
            # Nếu lỗi quota hoặc model không tìm thấy → dùng Pillow fallback
            if any(kw in error_msg for kw in ['RESOURCE_EXHAUSTED', 'NOT_FOUND', '429', '404', 'quota']):
                return self._create_thumbnail_pillow(image_path, vietnamese_title, save_path)
            raise

    def _create_thumbnail_gemini(self, image_path: str, original_title: str, save_path: str, extra_prompt: str = "") -> str:
        """Tạo thumbnail bằng Gemini AI (image-to-image), có hỗ trợ ảnh mẫu."""
        input_image = Image.open(image_path)
        
        # Tìm ảnh mẫu (reference image)
        module_dir = os.path.dirname(os.path.abspath(__file__))
        reference_image = None
        for sample_name in ["mau.jpg", "mau.png", "sample.jpg", "sample.png"]:
            sample_path = os.path.join(module_dir, sample_name)
            if os.path.exists(sample_path):
                reference_image = Image.open(sample_path)
                break

        prompt = f"""Đây là ảnh bìa (thumbnail) gốc của một video. Hãy tạo lại thumbnail này và tùy biến thiết kế ĐẬM CHẤT KÊNH REVIEW PHIM (Tóm tắt phim) theo phong cách sau:

1. GÓC TRÊN BÊN TRÁI: Vẽ biển hiệu/logo (Mặc định là chữ "TÓM TẮT PHIM", trừ khi có yêu cầu thay đổi ở phần YÊU CẦU PHỤ bên dưới).
2. TRUNG TÂM/BÊN DƯỚI: Chèn nội dung tiêu đề tiếng Việt.
3. PHONG CÁCH CHỮ TIÊU ĐỀ: 
   - TÓM TẮT NGẮN GỌN tiêu đề thành 1 câu giật gân (TỐI ĐA 6 TỪ/CHỮ). KHÔNG chèn toàn bộ tiêu đề dài lê thê làm che mất hình gốc!
   - Sử dụng font chữ vô cùng to, dày, và góc cạnh (kiểu Impact hoặc Arial Black).
   - Chia làm 2 dòng.
   - Các dòng trên dùng màu TRẮNG.
   - Dòng dưới cùng (từ khóa chính) BẮT BUỘC dùng màu ĐỎ RỰC hoặc CAM để thu hút sự chú ý.
   - Tất cả các chữ phải có VIỀN ĐEN siêu dày và ĐỔ BÓNG (Drop shadow) rõ nét để chữ nổi bần bật lên.
   - Các dòng chữ nên được xếp hơi lệch/nghiêng (so le) một chút để tạo sự kịch tính.
4. HÌNH ẢNH NỀN: Giữ nguyên bối cảnh rùng rợn, giật gân, hoặc hấp dẫn của ảnh gốc.

Tiêu đề gốc của video: {original_title}"""

        # Nếu có ảnh mẫu, cập nhật câu lệnh
        if reference_image:
            prompt = f"""[CẢNH BÁO QUAN TRỌNG]: 
Tôi đang gửi cho bạn 2 bức ảnh:
- Ảnh số 1 là ẢNH MẪU PHONG CÁCH (Theme Reference). KHÔNG ĐƯỢC xuất ra ảnh này làm kết quả! Chỉ dùng để tham khảo màu sắc và cách xếp chữ.
- Ảnh số 2 là ẢNH GỐC CẦN SỬA (Target Image). ĐÂY MỚI LÀ HÌNH ẢNH CHÍNH!

Nhiệm vụ của bạn: Hãy lấy ẢNH SỐ 2 (Ảnh gốc) làm nền, và áp dụng y hệt phong cách chữ, layout, màu sắc của ẢNH SỐ 1 (Ảnh mẫu) lên đó. KHÔNG ĐƯỢC sử dụng hình nền của Ảnh số 1!
""" + prompt

        if extra_prompt:
            prompt += f"\n\n[QUAN TRỌNG - YÊU CẦU PHỤ TỪ NGƯỜI DÙNG]:\n{extra_prompt}\n(Hãy TRỰC TIẾP ƯU TIÊN thực hiện yêu cầu này, ghi đè lên các quy tắc mặc định ở trên nếu có xung đột!)"

        contents = [input_image, prompt]
        if reference_image:
            contents = [reference_image, input_image, prompt]

        response = self.client.models.generate_content(
            model=self.image_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                image = Image.open(io.BytesIO(image_data))
                image = image.convert("RGB")
                if hasattr(Image, 'Resampling'):
                    resample_filter = Image.Resampling.LANCZOS
                else:
                    resample_filter = Image.LANCZOS
                image = image.resize((1280, 720), resample_filter)
                image.save(save_path, quality=95)
                return save_path

        raise Exception("Gemini không trả về ảnh.")

    def _create_thumbnail_pillow(self, image_path: str, vietnamese_title: str, save_path: str) -> str:
        """
        Tạo thumbnail bằng Pillow (fallback khi không có Gemini image quota).
        Chèn tiêu đề tiếng Việt lên ảnh gốc với hiệu ứng đẹp.
        """
        from PIL import ImageDraw, ImageFont, ImageFilter
        import os

        img = Image.open(image_path).convert("RGBA")
        width, height = img.size

        # Cải thiện: Gradient đen đậm hơn ở dưới cùng để nổi text
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        gradient_start = int(height * 0.4)
        for y in range(gradient_start, height):
            alpha = int(230 * (y - gradient_start) / (height - gradient_start)) # Đậm hơn (230 thay vì 200)
            draw_overlay.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, overlay)

        draw = ImageDraw.Draw(img)

        # Tìm font - Ưu tiên Impact cho chuẩn YouTube Thumbnail
        font = None
        font_size = max(int(height * 0.1), 32) # To hơn (10% thay vì 6.5%)
        font_paths = [
            "C:/Windows/Fonts/impact.ttf",      # Impact
            "C:/Windows/Fonts/arialbd.ttf",     # Arial Bold
            "C:/Windows/Fonts/segoeuib.ttf",    # Segoe UI Bold
            "C:/Windows/Fonts/tahoma.ttf",      # Tahoma
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, font_size)
                    break
                except Exception:
                    continue
        if font is None:
            font = ImageFont.load_default()

        # Word wrap tiêu đề và chuyển thành CHỮ HOA
        title = (vietnamese_title or "TIÊU ĐỀ VIDEO").upper()
        max_width = int(width * 0.9)
        lines = self._wrap_text(draw, title, font, max_width)

        # Vẽ huy hiệu "TÓM TẮT PHIM" ở góc trái trên
        badge_font_size = max(int(height * 0.05), 18)
        badge_font = font # Mặc định dùng luôn font Impact/ArialBold
        try:
            badge_font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", badge_font_size)
        except Exception:
            pass

        # Box 1: TÓM TẮT (Chữ Vàng, viền đen dày, KHÔNG NỀN)
        text_tt = "TÓM TẮT"
        bbox_tt = draw.textbbox((0, 0), text_tt, font=badge_font)
        w_tt = bbox_tt[2] - bbox_tt[0]
        h_tt = bbox_tt[3] - bbox_tt[1]
        x_tt, y_tt = int(width * 0.05), int(height * 0.05)
        
        # Vẽ viền cho chữ TÓM TẮT
        outline_w = max(int(badge_font_size * 0.05), 2)
        for dx in range(-outline_w, outline_w + 1):
            for dy in range(-outline_w, outline_w + 1):
                if dx*dx + dy*dy <= outline_w*outline_w:
                    draw.text((x_tt + dx, y_tt + dy), text_tt, fill=(0, 0, 0, 255), font=badge_font)
        draw.text((x_tt, y_tt), text_tt, fill=(255, 223, 0, 255), font=badge_font)

        # Box 2: PHIM (Nền Vàng, chữ Đen)
        text_phim = "PHIM"
        bbox_p = draw.textbbox((0, 0), text_phim, font=badge_font)
        w_p = bbox_p[2] - bbox_p[0] + int(width * 0.02)
        h_p = bbox_p[3] - bbox_p[1] + int(height * 0.02)
        x_p = x_tt + int(w_tt * 0.2) # Thụt vào 1 xíu so với chữ TÓM TẮT
        y_p = y_tt + h_tt + int(height * 0.02)
        
        # Vẽ nền vàng cho PHIM
        draw.rectangle([x_p, y_p, x_p + w_p, y_p + h_p], fill=(255, 223, 0, 255))
        # Vẽ chữ đen PHIM
        draw.text((x_p + int(width * 0.01), y_p + int(height * 0.005)), text_phim, fill=(0, 0, 0, 255), font=badge_font)

        # Tính vị trí text (căn giữa dưới)
        line_height = font_size + int(height * 0.01)
        total_text_height = len(lines) * line_height
        y_start = height - total_text_height - int(height * 0.05)

        # Cấu hình màu viền và bóng
        outline_fill = (0, 0, 0, 255)  # Viền đen
        shadow_fill = (0, 0, 0, 180)   # Bóng đen mờ

        # Vẽ text với stroke và shadow chuyên nghiệp
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            
            # So le trái/phải một chút để tạo sự kịch tính (không thẳng tắp)
            offset_x = int(width * 0.02)
            if len(lines) > 1:
                if i % 2 == 0:
                    x = (width - text_width) // 2 - offset_x
                else:
                    x = (width - text_width) // 2 + offset_x
            else:
                x = (width - text_width) // 2
                
            y = y_start + i * line_height

            # 1. Đổ bóng (Drop shadow) lệch xuống dưới bên phải
            shadow_offset = max(int(font_size * 0.08), 3)
            draw.text((x + shadow_offset, y + shadow_offset), line, fill=shadow_fill, font=font)

            # 2. Viền đen dày (Thick Stroke)
            stroke_width = max(int(font_size * 0.05), 2)
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx*dx + dy*dy <= stroke_width*stroke_width: # Viền bo tròn đẹp hơn
                        draw.text((x + dx, y + dy), line, fill=outline_fill, font=font)
            
            # 3. Đổ màu chuẩn Tóm Tắt Phim (Trên trắng, dưới cùng đỏ cam)
            if i == len(lines) - 1:
                current_fill = (255, 69, 0, 255)     # Đỏ cam (Orange Red)
            else:
                current_fill = (255, 255, 255, 255) # Trắng tinh
                
            draw.text((x, y), line, fill=current_fill, font=font)

        # Lưu
        img = img.convert("RGB")
        if hasattr(Image, 'Resampling'):
            resample_filter = Image.Resampling.LANCZOS
        else:
            resample_filter = Image.LANCZOS
        img = img.resize((1280, 720), resample_filter)
        img.save(save_path, quality=95)
        return save_path

    @staticmethod
    def _wrap_text(draw, text: str, font, max_width: int) -> list:
        """Tách text thành nhiều dòng để vừa chiều rộng."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        # Giới hạn tối đa 3 dòng
        if len(lines) > 3:
            lines = lines[:3]
            lines[2] = lines[2][:len(lines[2])-3] + "..."

        return lines

    def test_connection(self) -> bool:
        """Kiểm tra kết nối API key có hợp lệ không."""
        try:
            response = self.client.models.generate_content(
                model=self.text_model,
                contents="Trả lời 'OK' nếu bạn nhận được tin nhắn này.",
            )
            return bool(response.text)
        except Exception:
            return False
