"""
Tien xu ly Viet hoa de goi truoc pipeline render video.
Khong phu thuoc vao PyQt GUI, co the dung truc tiep tu capcut_dubber.
"""

import json
import os
import sys
from pathlib import Path

from browser_service import BrowserThumbnailService, build_thumbnail_prompt
from gemini_service import GeminiService
from video_service import VideoService

TOOL_ROOT = Path(__file__).resolve().parents[3]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from tool_paths import ToolPaths


PATHS = ToolPaths.from_root(TOOL_ROOT)


def _emit(progress_callback, message):
    if progress_callback:
        progress_callback(message)
    else:
        print(message)


def _candidate_api_key_paths():
    return [os.fspath(PATHS.api_keys_file())]


def resolve_api_key(provider, explicit_key=""):
    if explicit_key and explicit_key.strip():
        return explicit_key.strip(), "explicit"

    for path in _candidate_api_key_paths():
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        if not isinstance(payload, list):
            continue

        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("provider") != provider:
                continue
            key_value = str(item.get("key", "")).strip()
            if key_value:
                return key_value, path

    return "", ""


import re

def _normalize_title(title):
    t = str(title or "")
    # Xoá từ "review phim" (bao gồm cả trong ngoặc vuông, tròn nếu có)
    t = re.sub(r'(?i)\[?\(?review phim\)?\]?', '', t)
    # Loại bỏ phần đuôi sau dấu gạch đứng (thường là tên kênh)
    if '|' in t:
        t = t.split('|')[0]
    return " ".join(t.split())


def _fallback_short_title(title):
    words = _normalize_title(title).split()
    return " ".join(words[:6]).upper()


def _write_text_outputs(output_dir, metadata, translated_title, translated_description, video_title_with_prefix):
    info = {
        "url": metadata.get("url", ""),
        "platform": metadata.get("platform", ""),
        "uploader": metadata.get("uploader", ""),
        "title_original": metadata.get("title", ""),
        "description_original": metadata.get("description", ""),
        "title_viet": translated_title,
        "video_title_with_prefix": video_title_with_prefix,
        "description_viet": translated_description,
        "thumbnail_url": metadata.get("thumbnail_url", ""),
        "duration": metadata.get("duration", 0),
        "view_count": metadata.get("view_count", 0),
    }

    with open(os.path.join(output_dir, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "title_viet.txt"), "w", encoding="utf-8") as f:
        f.write(translated_title or "")

    with open(os.path.join(output_dir, "mo_ta_viet.txt"), "w", encoding="utf-8") as f:
        f.write(translated_description or "")


def _extract_text_from_srt(srt_path):
    import re
    if not os.path.exists(srt_path):
        return ""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Tách theo block
    blocks = re.split(r'\n\s*\n', content.strip())
    text_lines = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # Dòng 1: STT, Dòng 2: Timecode, Dòng 3+: Nội dung
            text_lines.append(" ".join(lines[2:]))
    return " ".join(text_lines)

def run_viethoa_preprocess(
    source_url,
    output_dir,
    srt_path="",
    gemini_api_key="",
    channel_name="",
    extra_prompt="",
    progress_callback=None,
):
    source_url = (source_url or "").strip()
    if not source_url:
        raise ValueError("Thieu source_url de chay Viet hoa.")

    os.makedirs(output_dir, exist_ok=True)

    api_key, api_key_source = resolve_api_key("gemini", gemini_api_key)
    if not api_key:
        raise RuntimeError(
            "Khong tim thay Gemini API key. Hay truyen --gemini_api_key hoac them key vao apiKeys.json."
        )

    thumb_original_path = os.path.join(output_dir, "thumbnail_original.jpg")
    thumb_viet_path = os.path.join(output_dir, "thumbnail_viet.png")

    video_service = VideoService()
    gemini = GeminiService(api_key)

    _emit(progress_callback, "Dang lay metadata video nguon...")
    metadata = video_service.extract_metadata(source_url)

    if metadata.get("thumbnail_url"):
        _emit(progress_callback, "Dang tai thumbnail goc...")
        video_service.download_thumbnail(metadata["thumbnail_url"], thumb_original_path)

    original_title = _normalize_title(metadata.get("title", ""))

    overall_context = ""
    if srt_path and os.path.exists(srt_path):
        _emit(progress_callback, "Dang trich xuat va tom tat ngu canh tu SRT...")
        srt_text = _extract_text_from_srt(srt_path)
        if srt_text:
            # Map: Split into chunks of ~3000 chars
            chunk_size = 3000
            chunks = [srt_text[i:i+chunk_size] for i in range(0, len(srt_text), chunk_size)]
            summaries = []
            for i, chunk in enumerate(chunks):
                _emit(progress_callback, f"  Tom tat phan {i+1}/{len(chunks)}...")
                summary = gemini.summarize_srt_chunk(chunk)
                if summary:
                    summaries.append(summary)
            
            # Reduce
            if summaries:
                _emit(progress_callback, "  Tong hop ngu canh tong extreme...")
                overall_context = gemini.summarize_overall_context(summaries)

    _emit(progress_callback, "Dang dich tieu de sang tieng Viet...")
    translated_title = _normalize_title(
        gemini.translate_title(original_title, channel_name=channel_name, movie_context=overall_context)
    )

    _emit(progress_callback, "Dang dich mo ta sang tieng Viet...")
    translated_description = gemini.translate_description(
        metadata.get("description", ""), movie_context=overall_context
    ).strip()

    short_title = ""
    try:
        _emit(progress_callback, "Dang rut gon tieu de cho template...")
        short_title = _normalize_title(gemini.shorten_title_for_thumbnail(translated_title))
    except Exception:
        short_title = _fallback_short_title(translated_title)

    video_title_with_prefix = f"[Review Phim] {translated_title}"

    _emit(progress_callback, "Da tat tinh nang tao thumbnail (tach rieng tool). Bo qua tao thumbnail Viet hoa.")

    _write_text_outputs(output_dir, metadata, translated_title, translated_description, video_title_with_prefix)

    result = {
        "source_url": source_url,
        "output_dir": os.path.abspath(output_dir),
        "api_key_source": api_key_source,
        "original_title": original_title,
        "translated_title": translated_title,
        "video_title_with_prefix": video_title_with_prefix,
        "short_title": short_title,
        "translated_description": translated_description,
        "thumbnail_original_path": thumb_original_path if os.path.exists(thumb_original_path) else "",
        "thumbnail_viet_path": thumb_viet_path if os.path.exists(thumb_viet_path) else "",
        "metadata": metadata,
    }

    _emit(progress_callback, f"Da hoan tat tien xu ly Viet hoa tai: {result['output_dir']}")
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Viet Hoa Thumbnail & Metadata")
    parser.add_argument("--url", type=str, required=True, help="URL video YouTube")
    parser.add_argument("--out_dir", type=str, required=True, help="Thu muc luu ket qua")
    parser.add_argument("--srt", type=str, default="", help="Duong dan file SRT goc de lam ngu canh")
    parser.add_argument("--api_key", type=str, default="", help="Gemini API Key")
    parser.add_argument("--prompt", type=str, default="", help="Prompt bo sung cho Thumbnail")
    
    args = parser.parse_args()
    
    def log_print(msg):
        print(f"[VIET_HOA] {msg}", flush=True)
        
    try:
        run_viethoa_preprocess(
            source_url=args.url,
            output_dir=args.out_dir,
            srt_path=args.srt,
            gemini_api_key=args.api_key,
            extra_prompt=args.prompt,
            progress_callback=log_print
        )
    except Exception as e:
        print(f"[ERROR] {str(e)}", file=sys.stderr, flush=True)
        sys.exit(1)
