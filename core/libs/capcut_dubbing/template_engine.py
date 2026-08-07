"""
Template Engine - Chuyển đổi Template JSON thành FFmpeg filter_complex strings.
Lấy cảm hứng từ OpenCut schema (timeline tracks, elements).

Hỗ trợ:
- Text overlay (drawtext) với border, shadow, biến động [[TEN_VIDEO]]
- Watermark overlay (image overlay) với opacity
- Blur region (boxblur + crop + overlay)
- Video transforms (hflip, rotate)
- BGM mixing (amix) với volume/speed control
"""

import os
import re
import json


# ============================================================
# 1. LOAD & PARSE
# ============================================================

def load_template(source):
    """
    Load template từ nhiều nguồn:
    - dict: trả về trực tiếp
    - str path đến file JSON: đọc file, trả về list templates
    - list: trả về trực tiếp
    """
    if isinstance(source, dict):
        return source
    if isinstance(source, list):
        return source
    if isinstance(source, str) and os.path.isfile(source):
        with open(source, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data  # list hoặc dict
    raise ValueError(f"Không thể load template từ: {source}")


def get_template_by_index(templates, index):
    """Lấy template theo index (0-based). Index 0 = '-- KHÔNG DÙNG TEMPLATE --'."""
    if index <= 0:
        return None
    if isinstance(templates, list):
        actual_index = index - 1  # Bỏ qua entry "không dùng template"
        if 0 <= actual_index < len(templates):
            return templates[actual_index]
    return None


# ============================================================
# 2. TEXT VARIABLE RESOLUTION
# ============================================================

def resolve_text_variables(text, variables=None):
    """
    Thay thế các biến trong text template.
    Hỗ trợ nhiều cú pháp:
    - [[TEN_BIEN]] → giá trị biến
    - [[TEN_BIEN|color]] → giá trị biến (bỏ |color)
    - [[TEN_BIEN]|color] → giá trị biến (bỏ |color])
    
    Ví dụ: "ppp [[TEN_VIDEO]|yellow]" → "ppp Tên Video Thật"
    """
    if not text or not variables:
        return text
    
    def replace_var(match):
        full = match.group(1)  # TEN_VIDEO hoặc TEN_VIDEO|yellow
        parts = full.split('|')
        var_name = parts[0].strip().rstrip(']')  # Bỏ ] nếu có
        value = variables.get(var_name, f"[{var_name}]")
        
        # Tự động dọn dẹp tên video (áp dụng cho tất cả các biến chứa TEN_VIDEO như TEN_VIDEO_VIET, TEN_VIDEO_GOC...)
        if "TEN_VIDEO" in var_name and isinstance(value, str):
            # Xóa chuỗi "review phim" (có hoặc không có ngoặc vuông, không phân biệt hoa thường)
            value = re.sub(r'(?i)\[?review phim\]?\s*', '', value)
            
            # Xóa tên kênh: Xóa tất cả mọi thứ sau dấu gạch đứng '|' hoặc gạch ngang '-' cuối cùng
            value = re.sub(r'\s*[-|]\s*[^|]*$', '', value)
            
            # Xóa khoảng trắng thừa 2 đầu
            value = value.strip()
            
        return str(value)
    
    # Pattern 1: [[VAR_NAME|color]] (standard)
    result = re.sub(r'\[\[([^\]]+)\]\]', replace_var, text)
    
    # Pattern 2: [[VAR_NAME]|color] (format DLL)
    # Ví dụ: [[TEN_VIDEO]|yellow] → value
    result = re.sub(r'\[\[([^\]]+)\]\|[^\]]*\]', replace_var, result)
    
    # Pattern 3: [VAR_NAME] (format cũ của GCS)
    # Ví dụ: [TEN_VIDEO]
    def replace_var_single(match):
        var_name = match.group(1)
        # Bỏ qua nếu là mã màu [#COLOR] hoặc tag kết thúc [-]
        if var_name.startswith('#') or var_name == '-':
            return match.group(0)
            
        value = variables.get(var_name, f"[{var_name}]")
        
        if "TEN_VIDEO" in var_name and isinstance(value, str):
            value = re.sub(r'(?i)\[?review phim\]?\s*', '', value)
            value = re.sub(r'\s*[-|]\s*[^|]*$', '', value)
            value = value.strip()
        return str(value)

    result = re.sub(r'\[([^\]\[]+)\]', replace_var_single, result)
    
    return result


def extract_colored_segments(text):
    """
    Trích xuất các đoạn text có màu riêng từ cú pháp [[text|color]].
    Trả về list các (text_segment, color_or_None).
    
    Ví dụ: "ppp [[TEN_VIDEO|yellow]]" → [("ppp ", None), ("TEN_VIDEO_VALUE", "yellow")]
    """
    segments = []
    last_end = 0
    
    for match in re.finditer(r'\[\[([^|\]]+)\|([^\]]+)\]\]', text):
        # Text trước match
        if match.start() > last_end:
            segments.append((text[last_end:match.start()], None))
        # Text trong match
        segments.append((match.group(1), match.group(2)))
        last_end = match.end()
    
    # Text còn lại
    if last_end < len(text):
        segments.append((text[last_end:], None))
    
    if not segments:
        segments = [(text, None)]
    
    return segments


# ============================================================
# 3. FFMPEG FILTER BUILDERS
# ============================================================

def _escape_drawtext(text):
    """Escape các ký tự đặc biệt cho FFmpeg drawtext filter."""
    # FFmpeg drawtext cần escape: '  :  \  ;  [  ]  ,  =
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\\\\\''")
    text = text.replace(":", "\\:")
    text = text.replace(";", "\\;")
    # Không escape [ ] vì chúng đã được xử lý khi resolve variables
    return text


def get_optimal_font_size(text, font_path, max_width, max_height, fallback_size=48):
    if not text or max_width <= 0 or max_height <= 0:
        return fallback_size
        
    try:
        from PIL import ImageFont
    except ImportError:
        # Heuristic fallback
        return int(min(max_height * 0.8, (max_width / max(1, len(text))) * 1.8))
        
    system_font_dir = "C:\\Windows\\Fonts"
    full_font_path = os.path.join(system_font_dir, font_path) if not os.path.isabs(font_path) else font_path
    
    if not os.path.exists(full_font_path):
        return int(min(max_height * 0.8, (max_width / max(1, len(text))) * 1.8))
        
    def check_size(s):
        try:
            font = ImageFont.truetype(full_font_path, s)
            bbox = font.getbbox(text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            return w, h
        except:
            return s * len(text) * 0.6, s * 1.2
            
    low = 1
    high = 800
    best = fallback_size
    
    while low <= high:
        mid = (low + high) // 2
        w, h = check_size(mid)
        # Chừa 5% margin an toàn
        if w <= max_width * 0.95 and h <= max_height * 0.95:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
            
    return max(1, best)


def build_drawtext_filter(element, video_width, video_height, variables=None):
    """
    Tạo FFmpeg drawtext filter string cho một text element.
    
    Element schema:
    {
        "type": "text",
        "x": 0.0, "y": 0.8912,      # Tỷ lệ 0.0-1.0 relative to video
        "width": 0.9771, "height": 0.107,
        "text": "ppp [[TEN_VIDEO|yellow]]",
        "fontSize": 48,
        "fontColor": "white",
        "fontName": "tahoma.ttf",
        "borderWidth": 2,            # Optional
        "borderColor": "black",      # Optional
        "shadowX": 2,                # Optional
        "shadowY": 2                 # Optional
    }
    """
    raw_text = element.get("text", "")
    
    # Resolve biến [[TEN_VIDEO]] etc. - đã xử lý cả format [[VAR]|color]
    resolved_text = resolve_text_variables(raw_text, variables)
    
    # Fallback cleanup: nếu còn sót markup nào thì bỏ đi
    clean_text = re.sub(r'\[\[([^|\]]+)\|[^\]]+\]\]', r'\1', resolved_text)  # [[VAR|color]]
    clean_text = re.sub(r'\[\[([^\]]+)\]\|[^\]]*\]', r'\1', clean_text)      # [[VAR]|color]
    clean_text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', clean_text)              # [[VAR]]
    clean_text = re.sub(r'\[#.*?\]', '', clean_text)                         # Xoá [#COLOR]
    clean_text = clean_text.replace('[-]', '')                               # Xoá [-]
    
    escaped_text = _escape_drawtext(clean_text)
    
    # Tính toạ độ pixel từ tỷ lệ
    px_x = int(element.get("x", 0) * video_width)
    px_y = int(element.get("y", 0) * video_height)
    px_w = int(element.get("width", 0) * video_width)
    px_h = int(element.get("height", 0) * video_height)
    
    font_size = element.get("fontSize", 48)
    font_color = element.get("fontColor", "white")
    
    # Map fontFamily from UI to font file
    font_family = element.get("fontFamily", "")
    font_name = element.get("fontName", "tahoma.ttf")
    if font_family:
        font_mapping = {
            "tahoma": "tahoma.ttf",
            "arial": "arial.ttf",
            "times new roman": "times.ttf",
            "verdana": "verdana.ttf",
            "calibri": "calibri.ttf",
            "segoe ui": "segoeui.ttf",
            "consolas": "consola.ttf",
            "comic sans ms": "comic.ttf",
            "microsoft yahei": "msyh.ttc",
            "simhei": "simhei.ttf"
        }
        font_name = font_mapping.get(font_family.lower(), "tahoma.ttf")

    # Auto fallback to CJK font if text contains CJK characters and selected font is a generic Western font
    if re.search(r'[\u4e00-\u9fff\u3040-\u30ff\u3130-\u318f\uac00-\ud7af]', escaped_text):
        if font_name.lower() in ["tahoma.ttf", "arial.ttf", "times.ttf", "verdana.ttf", "calibri.ttf"]:
            font_name = "msyh.ttc"  # Microsoft YaHei supports CJK
            
    # Hỗ trợ in đậm (isBold)
    is_bold = element.get("isBold", False) or element.get("bold", False)
    if is_bold:
        font_name_lower = font_name.lower()
        bold_mapping = {
            "tahoma.ttf": "tahomabd.ttf",
            "arial.ttf": "arialbd.ttf",
            "times.ttf": "timesbd.ttf",
            "verdana.ttf": "verdanab.ttf",
            "calibri.ttf": "calibrib.ttf",
            "segoeui.ttf": "segoeuib.ttf",
            "consola.ttf": "consolab.ttf",
            "msyh.ttc": "msyhbd.ttc"
        }
        if font_name_lower in bold_mapping:
            font_name = bold_mapping[font_name_lower]

    # Tính toán font size tự động để chữ nằm vừa vặn trong khung (Auto-fit)
    if px_w > 0 and px_h > 0:
        # Lấy font_size lý tưởng, dùng font_size từ JSON làm fallback
        font_size = get_optimal_font_size(clean_text, font_name, px_w, px_h, fallback_size=font_size)

    # Căn giữa chữ vào giữa box để khớp với hiển thị trên giao diện (Center alignment)
    x_expr = f"{px_x}+({px_w}-tw)/2" if px_w > 0 else f"{px_x}"
    y_expr = f"{px_y}+({px_h}-th)/2" if px_h > 0 else f"{px_y}"
    
    # Build drawtext filter
    parts = [
        f"text='{escaped_text}'",
        f"fontsize={font_size}",
        f"fontcolor={font_color}",
        f"x={x_expr}",
        f"y={y_expr}",
    ]
    
    # Enable expression (t is time relative to chunk start)
    enable_expr = element.get("_enable_expr", "")
    if enable_expr:
        parts.append(enable_expr)
    
    # Font file - thử tìm font trong system
    font_path = _resolve_font_path(font_name)
    if font_path:
        # Escape dấu hai chấm (:) trên Windows path cho FFmpeg filter
        font_path = font_path.replace(":", "\\:")
        parts.append(f"fontfile='{font_path}'")
    
    # Border (viền chữ)
    border_w = element.get("borderWidth", 0)
    if border_w > 0:
        border_color = element.get("borderColor", "black")
        parts.append(f"borderw={border_w}")
        parts.append(f"bordercolor={border_color}")
    
    # Shadow (bóng đổ)
    shadow_x = element.get("shadowX", 0)
    shadow_y = element.get("shadowY", 0)
    if shadow_x > 0 or shadow_y > 0:
        parts.append(f"shadowx={shadow_x}")
        parts.append(f"shadowy={shadow_y}")
        parts.append("shadowcolor=black@0.5")
    
    return "drawtext=" + ":".join(parts)


def _resolve_font_path(font_name):
    """Tìm đường dẫn đầy đủ cho font file."""
    if os.path.isabs(font_name) and os.path.exists(font_name):
        return font_name.replace("\\", "/")
    
    # Tìm trong thư mục Windows Fonts
    win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    candidate = os.path.join(win_fonts, font_name)
    if os.path.exists(candidate):
        return candidate.replace("\\", "/")
    
    # Tìm không có extension
    if not font_name.endswith(".ttf"):
        candidate = os.path.join(win_fonts, font_name + ".ttf")
        if os.path.exists(candidate):
            return candidate.replace("\\", "/")
    
    return None


def build_watermark_overlay_filter(element_index, video_width, video_height, element):
    """
    Tạo FFmpeg overlay filter cho watermark element.
    
    Trả về: (input_file_path, filter_string)
    
    Element schema:
    {
        "type": "watermark",
        "x": 0.0, "y": 0.888,
        "width": 1.242, "height": 0.2778,
        "logoPath": "path/to/logo.webp",
        "opacity": 1.0
    }
    """
    logo_path = element.get("logoPath", "")
    if not logo_path or not os.path.exists(logo_path):
        return None, None
    
    # Tính toạ độ và kích thước pixel
    px_x = int(element.get("x", 0) * video_width)
    px_y = int(element.get("y", 0) * video_height)
    px_w = max(2, int(element.get("width", 0.1) * video_width))
    px_h = max(2, int(element.get("height", 0.1) * video_height))
    # Đã loại bỏ opacity, sử dụng lanczos để chống mờ nhòe
    scale_filter = f"[wm_input_{element_index}]scale={px_w}:{px_h}:flags=lanczos,format=rgba"
    scale_filter += f"[{wm_label}]"
    
    # Overlay lên video
    overlay_filter = f"overlay={px_x}:{px_y}:format=auto"
    
    return logo_path, (scale_filter, overlay_filter, wm_label)


def build_blur_region_filter(element_index, video_width, video_height, element):
    """
    Tạo FFmpeg filter cho blur region.
    Kỹ thuật: crop vùng → blur → overlay lại.
    
    Element schema:
    {
        "type": "blur",
        "x": 0.0, "y": 0.0,
        "width": 1.0, "height": 0.1,
        "blurStrength": 20
    }
    """
    px_x = int(element.get("x", 0) * video_width)
    px_y = int(element.get("y", 0) * video_height)
    px_w = int(element.get("width", 0.1) * video_width)
    px_h = int(element.get("height", 0.1) * video_height)
    strength = element.get("blurStrength", 20)
    
    # Đảm bảo kích thước hợp lệ
    safe_strength = min(strength, px_w // 4, px_h // 4)
    safe_strength = max(1, safe_strength)
    
    blur_label = f"blur{element_index}"
    
    # Crop vùng → blur → overlay lại vị trí cũ
    # Sử dụng split để tránh mất source
    crop_blur = f"crop={px_w}:{px_h}:{px_x}:{px_y},boxblur={safe_strength}:2[{blur_label}]"
    overlay = f"overlay={px_x}:{px_y}"
    
    return crop_blur, overlay, blur_label


def build_video_transform_filters(template):
    """
    Tạo FFmpeg filters cho video transforms (rotate).
    Lưu ý: flipHorizontal đã được xử lý ở capcut_dubber.py qua biến flip_str.
    """
    filters = []
    
    rotate_angle = template.get("rotateAngle", 0)
    if rotate_angle and abs(rotate_angle) > 0.001:
        # FFmpeg rotate dùng radian
        import math
        rad = rotate_angle * math.pi / 180.0
        filters.append(f"rotate={rad}:fillcolor=black")
    
    return filters


# ============================================================
# 4. FULL FILTER GRAPH BUILDER
# ============================================================

def build_template_filter_graph(template, video_width, video_height, variables=None, chunk_start=0.0, chunk_duration=0.0, total_video_duration=0.0):
    """
    Tổng hợp tất cả template elements thành một filter chain hoàn chỉnh.
    
    Trả về:
    - extra_inputs: list các file path cần thêm vào FFmpeg -i (watermark images)
    - video_filter_chain: chuỗi filter cho video stream (để nối sau video_norm)
    - needs_split: True nếu có blur regions cần split video stream
    
    Cách sử dụng:
    Append video_filter_chain sau [vout] trong filter_complex hiện có.
    """
    if not template:
        return [], "", False
    
    elements = template.get("elements", [])
    if not elements and not template.get("flipHorizontal") and not template.get("rotateAngle"):
        return [], "", False
    
    extra_inputs = []  # Các file watermark cần -i
    filter_parts = []  # Các filter cần áp dụng tuần tự
    
    # Helper xác định khoảng thời gian active của element
    def get_active_interval(elem):
        anchor = elem.get("anchorType", "full")
        start_time = float(elem.get("startTime", 0.0))
        duration = float(elem.get("duration", 5.0))
        
        if anchor == "full":
            return 0.0, total_video_duration
        elif anchor == "start":
            return start_time, start_time + duration
        elif anchor == "end":
            return max(0.0, total_video_duration - duration - start_time), total_video_duration - start_time
        return 0.0, total_video_duration

    # Helper filter list by chunk
    def filter_elements_for_chunk(elem_list):
        result = []
        chunk_end = chunk_start + chunk_duration
        for elem in elem_list:
            active_start, active_end = get_active_interval(elem)
            
            # Kiểm tra xem có giao nhau với chunk này không
            if active_end <= chunk_start or active_start >= chunk_end:
                continue
                
            # Tính thời gian tương đối so với đầu chunk
            rel_start = max(0.0, active_start - chunk_start)
            rel_end = min(chunk_duration, active_end - chunk_start)
            
            # Nếu element không full toàn bộ chunk thì thêm điều kiện enable
            if rel_start > 0 or rel_end < chunk_duration:
                # Tránh các số quá sát nhau
                if (rel_end - rel_start) > 0.01:
                    elem["_enable_expr"] = f"enable='between(t,{rel_start:.3f},{rel_end:.3f})'"
            else:
                elem.pop("_enable_expr", None)
                
            result.append(elem)
        return result

    # Lọc elements theo thời gian của chunk hiện tại
    text_elements = filter_elements_for_chunk([e for e in elements if e.get("type") == "text"])
    watermark_elements = filter_elements_for_chunk([e for e in elements if e.get("type") == "watermark"])
    blur_elements = filter_elements_for_chunk([e for e in elements if e.get("type") == "blur"])
    
    # --- Video transforms (flip, rotate) ---
    transform_filters = build_video_transform_filters(template)
    filter_parts.extend(transform_filters)
    
    # --- Blur regions (Complex graph) ---
    complex_parts = []
    
    for i, elem in enumerate(blur_elements):
        strength = elem.get("blurStrength", 20)
        px_x = int(elem.get("x", 0) * video_width)
        px_y = int(elem.get("y", 0) * video_height)
        px_w = int(elem.get("width", 0.1) * video_width)
        px_h = int(elem.get("height", 0.1) * video_height)
        
        # Đảm bảo blur không lấn ra ngoài bounds video để tránh lỗi FFmpeg crop
        crop_x = max(0, min(px_x, video_width - 2))
        crop_y = max(0, min(px_y, video_height - 2))
        crop_w = max(2, min(px_w + min(0, px_x), video_width - crop_x))
        crop_h = max(2, min(px_h + min(0, px_y), video_height - crop_y))
        
        # FFmpeg boxblur yêu cầu radius <= width/2 và <= height/2, với yuv420p chroma là width/4
        safe_strength = min(strength, crop_w // 4, crop_h // 4)
        safe_strength = max(1, safe_strength)
        
        # Trả về config blur để hàm build chính xử lý bằng label graph
        elem["_blur_config"] = {
            "x": crop_x, "y": crop_y, 
            "w": crop_w, "h": crop_h, 
            "strength": safe_strength
        }
    
    # --- Text overlays ---
    for i, elem in enumerate(text_elements):
        dt_filter = build_drawtext_filter(elem, video_width, video_height, variables)
        filter_parts.append(dt_filter)
    
    # --- Watermark overlays ---
    for i, elem in enumerate(watermark_elements):
        logo_path = elem.get("logoPath", "")
        if not logo_path or not os.path.exists(logo_path):
            continue
        extra_inputs.append(logo_path)
    
    video_filter_chain = ",".join(filter_parts) if filter_parts else ""
    
    return extra_inputs, video_filter_chain, watermark_elements, blur_elements


def build_ffmpeg_filter_complex_with_template(
    template, video_width, video_height, 
    video_norm, flip_str, 
    chunk_type, factor=1.0, 
    has_tts_audio=False,
    base_video_input_index=0,
    base_tts_input_index=1,
    variables=None,
    chunk_start=0.0,
    chunk_duration=0.0,
    total_video_duration=0.0
):
    """
    Xây dựng filter_complex HOÀN CHỈNH cho một chunk, bao gồm cả template.
    
    Đây là hàm chính thay thế logic hardcode trong render_ffmpeg_chunk().
    
    Params:
        template: dict template hoặc None
        video_width, video_height: kích thước video
        video_norm: chuỗi scale filter (vd: "scale=1920:1080,setsar=1:1,format=yuv420p")
        flip_str: ",hflip" hoặc ""
        chunk_type: "gap" hoặc "sub"
        factor: tỷ lệ speed (chỉ cho "sub")
        has_tts_audio: True nếu có TTS audio input
        base_video_input_index: index của video input (thường là 0)
        base_tts_input_index: index của TTS audio input (thường là 1)
        variables: dict biến để resolve text (vd: {"TEN_VIDEO": "..."})
    
    Returns:
        (filter_complex_str, extra_input_files, output_maps)
    """
    extra_input_files = []
    
    # ---- VIDEO PIPELINE ----
    # Bắt đầu với video stream
    if chunk_type == "sub" and abs(factor - 1.0) > 0.001:
        video_chain = f"[{base_video_input_index}:v]setpts={factor}*(PTS-STARTPTS),{video_norm}{flip_str}"
    else:
        video_chain = f"[{base_video_input_index}:v]setpts=PTS-STARTPTS,{video_norm}{flip_str}"
    
    # Áp dụng template video filters (blur, transform, drawtext)
    if template:
        tpl_extra_inputs, tpl_video_filters, watermark_elems, blur_elems = build_template_filter_graph(
            template, video_width, video_height, variables, chunk_start, chunk_duration, total_video_duration
        )
        extra_input_files.extend(tpl_extra_inputs)
        
        video_chain += "[vtmp_base]"
        current_v_label = "vtmp_base"
        v_idx = 0
        
        # Blur regions processing (Complex graph)
        for elem in (blur_elems or []):
            cfg = elem.get("_blur_config")
            if not cfg: continue
            
            src = current_v_label
            dst = f"vtmp_blur{v_idx}"
            
            enable_expr = elem.get("_enable_expr", "")
            split_str = f"[{src}]split[blur_main{v_idx}][blur_src{v_idx}]"
            
            blur_type = elem.get("blurType", "box")
            if blur_type == "gaussian":
                blur_filter = f"gblur=sigma={cfg['strength']}"
            elif blur_type == "pixelate":
                # Pixelate by scaling down and then scaling up with nearest neighbor
                s = max(2, cfg['strength'])
                blur_filter = f"scale=iw/{s}:ih/{s},scale=iw*{s}:ih*{s}:flags=neighbor"
            else:
                blur_filter = f"boxblur={cfg['strength']}:2"
                
            crop_str = f"[blur_src{v_idx}]crop={cfg['w']}:{cfg['h']}:{cfg['x']}:{cfg['y']},{blur_filter}[blur_region{v_idx}]"
            overlay_args = f"{cfg['x']}:{cfg['y']}"
            if enable_expr:
                overlay_args += f":{enable_expr}"
                
            overlay_str = f"[blur_main{v_idx}][blur_region{v_idx}]overlay={overlay_args}[{dst}]"
            
            video_chain += f";{split_str};{crop_str};{overlay_str}"
            current_v_label = dst
            v_idx += 1
        
        # Xác định next input index cho watermarks
        next_input_idx = base_tts_input_index + (1 if has_tts_audio else 0)
        
        # Watermark overlays - cần thêm input files
        valid_watermarks = []
        for elem in (watermark_elems or []):
            logo_path = elem.get("logoPath", "")
            if logo_path and os.path.exists(logo_path):
                valid_watermarks.append((elem, next_input_idx))
                extra_input_files.append(logo_path)
                next_input_idx += 1
        
        if valid_watermarks:
            for wi, (elem, input_idx) in enumerate(valid_watermarks):
                px_x = int(elem.get("x", 0) * video_width)
                px_y = int(elem.get("y", 0) * video_height)
                px_w = int(elem.get("width", 0.1) * video_width)
                px_h = int(elem.get("height", 0.1) * video_height)
                
                # Xóa clamp toạ độ để watermark có thể lấn ra ngoài video (top/left)
                # Đảm bảo width/height hợp lệ tối thiểu là 2
                px_w = max(2, px_w)
                px_h = max(2, px_h)
                
                # Đã loại bỏ tùy chỉnh độ mờ (opacity) theo yêu cầu của người dùng, sử dụng lanczos để chống mờ nhòe (blurry)
                wm_scale = f"[{input_idx}:v]scale={px_w}:{px_h}:flags=lanczos,format=rgba"
                wm_label = f"wm{wi}"
                wm_scale += f"[{wm_label}]"
                
                # Overlay
                src = current_v_label
                dst = f"vtmp_wm{wi}"
                
                overlay_str = f"[{src}][{wm_label}]overlay={px_x}:{px_y}:format=auto:eof_action=repeat[{dst}]"
                
                video_chain += f";{wm_scale};{overlay_str}"
                current_v_label = dst
                
        # Áp dụng text overlays (drawtext) SAU CÙNG để không bị watermark đè lên
        if tpl_video_filters:
            dst_text = "vtmp_text"
            video_chain += f";[{current_v_label}]{tpl_video_filters}[{dst_text}]"
            current_v_label = dst_text
            
        video_chain += f";[{current_v_label}]copy[vout]"
    else:
        video_chain += "[vout]"
    
    # ---- AUDIO PIPELINE ----
    if chunk_type == "gap":
        audio_chain = f"[{base_video_input_index}:a]asetpts=PTS-STARTPTS,apad[aout]"
    else:
        # Sub chunk: mix original audio (lowered) + TTS audio
        if has_tts_audio and abs(factor - 1.0) > 0.001:
            from capcut_dubber import build_atempo_chain
            inv_factor = 1.0 / factor
            atempo_str = build_atempo_chain(inv_factor)
            audio_chain = (
                f"[{base_video_input_index}:a]asetpts=PTS-STARTPTS,{atempo_str},apad,volume=0.15[a0];"
                f"[{base_tts_input_index}:a]asetpts=PTS-STARTPTS,apad,volume=1.0[a1];"
                f"[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
            )
        elif has_tts_audio:
            audio_chain = (
                f"[{base_video_input_index}:a]asetpts=PTS-STARTPTS,apad,volume=0.15[a0];"
                f"[{base_tts_input_index}:a]asetpts=PTS-STARTPTS,apad,volume=1.0[a1];"
                f"[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
            )
        else:
            audio_chain = f"[{base_video_input_index}:a]asetpts=PTS-STARTPTS,apad[aout]"
    
    filter_complex = f"{video_chain};{audio_chain}"
    
    return filter_complex, extra_input_files


# ============================================================
# 5. BGM (Background Music) - Áp dụng sau CONCAT
# ============================================================

def build_bgm_mix_cmd(input_video, bgm_path, output_path, bgm_volume=15.0, bgm_speed=1.0):
    """
    Tạo lệnh FFmpeg để mix BGM vào video final (sau concat).
    
    BGM sẽ loop liên tục cho đến hết video.
    Volume tính bằng % (15.0 = 15% volume).
    Speed điều chỉnh tốc độ phát BGM.
    
    Returns: list cmd args cho subprocess.run()
    """
    if not bgm_path or not os.path.exists(bgm_path):
        return None
    
    # Chuyển volume % sang dB scale cho FFmpeg
    # 15% ≈ -16.5dB, 100% = 0dB
    vol_factor = max(0.01, bgm_volume / 100.0)
    
    # Build audio filter cho BGM
    bgm_filters = []
    
    # Speed adjustment
    if bgm_speed and abs(bgm_speed - 1.0) > 0.001:
        # atempo chỉ hỗ trợ 0.5-100.0
        speed = max(0.5, min(100.0, bgm_speed))
        bgm_filters.append(f"atempo={speed}")
    
    # Volume
    bgm_filters.append(f"volume={vol_factor}")
    
    bgm_filter_str = ",".join(bgm_filters)
    
    # Build filter_complex
    # [1:a] = BGM, loop vô hạn bằng -stream_loop -1
    filter_complex = (
        f"[1:a]{bgm_filter_str}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=3[aout]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-stream_loop", "-1",  # Loop BGM vô hạn
        "-i", bgm_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",  # Không re-encode video
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_path
    ]
    
    return cmd


# ============================================================
# 6. UTILITY FUNCTIONS
# ============================================================

def get_video_title_from_path(video_path):
    """Trích xuất tên video từ đường dẫn file (bỏ extension)."""
    basename = os.path.basename(video_path)
    name, _ = os.path.splitext(basename)
    return name


def build_default_variables(video_path="", custom_vars=None):
    """
    Tạo dict biến mặc định cho text template.
    
    Biến hỗ trợ:
    - TEN_VIDEO: Tên file video (không có extension)
    - NGAY_THANG: Ngày tháng hiện tại
    """
    import datetime
    
    variables = {
        "TEN_VIDEO": get_video_title_from_path(video_path) if video_path else "",
        "NGAY_THANG": datetime.datetime.now().strftime("%d/%m/%Y"),
    }
    
    if custom_vars:
        variables.update(custom_vars)
    
    return variables
