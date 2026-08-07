import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo thư mục viet_hoa_video nằm trong sys.path để các module nội bộ của nó (như browser_service) hoạt động được
viet_hoa_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs", "viet_hoa_video")
if viet_hoa_dir not in sys.path:
    sys.path.insert(0, viet_hoa_dir)

import json
from viethoa_preprocess import resolve_api_key
from libs.translator.engine import TranslatorEngine

def get_all_gemini_keys() -> list:
    keys = []
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "config", "apiKeys.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                for item in payload:
                    if item.get("provider") == "gemini" and item.get("status") != "invalid":
                        k = str(item.get("key", "")).strip()
                        if k:
                            keys.append(k)
        except Exception:
            pass
    return keys

def run_translate(srt_path: str, src_lang: str, dst_lang: str) -> str:
    """
    Dịch phụ đề từ src_lang sang dst_lang bằng kiến trúc async + checkpointing đa luồng.
    Đây là entry point được gọi từ giao diện (st.py).
    """
    if src_lang == dst_lang:
        print("Ngôn ngữ nguồn và đích giống nhau, bỏ qua dịch.")
        return srt_path
        
    api_keys = get_all_gemini_keys()
    if not api_keys:
        # Fallback to the old resolve_api_key just in case
        fallback_key, _ = resolve_api_key("gemini")
        if fallback_key:
            api_keys = [fallback_key]
            
    if not api_keys:
        print("Không tìm thấy Gemini API Key. Bỏ qua bước dịch phụ đề.")
        return srt_path
        
    print(f"Khởi động Hệ thống Dịch thuật Đa luồng ({len(api_keys)} API keys) cho file {os.path.basename(srt_path)}...")
    
    # Mỗi API key sẽ đảm nhận đúng 1 luồng (worker) để tránh bị rate limit
    concurrency = max(1, len(api_keys))
    
    engine = TranslatorEngine(
        api_keys=api_keys,
        srt_path=srt_path,
        src_lang=src_lang,
        dst_lang=dst_lang,
        max_concurrency=concurrency 
    )
    
    # Chạy vòng lặp bất đồng bộ chặn (block) để đồng bộ với Streamlit
    try:
        translated_srt_path = asyncio.run(engine.run_async())
        return translated_srt_path
    except Exception as e:
        print(f"Lỗi nghiêm trọng trong Translation Engine: {e}")
        return srt_path
