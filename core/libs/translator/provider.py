import abc
import asyncio
import re
from typing import List, Dict, Optional
from google import genai
import time

import itertools

class LLMProvider(abc.ABC):
    @abc.abstractmethod
    async def translate_batch(self, batch_text: str, src_lang: str, dst_lang: str) -> str:
        """Dịch một chuỗi văn bản (đã chứa các block ID)."""
        pass

class GeminiProvider(LLMProvider):
    def __init__(self, api_keys: List[str], model: str = "gemini-3.1-flash-lite"):
        if not api_keys:
            raise ValueError("Phải cung cấp ít nhất 1 API key")
        self.clients = [genai.Client(api_key=key) for key in api_keys]
        self.client_cycle = itertools.cycle(self.clients)
        self.model = model

    async def translate_batch(self, batch_text: str, src_lang: str, dst_lang: str) -> str:
        # Lấy Client theo vòng tròn (Round-Robin) đảm bảo chia tải đều tuyệt đối 1-1
        client = next(self.client_cycle)
        prompt = f"""Bạn là một chuyên gia dịch thuật phim. Hãy dịch các câu phụ đề sau từ {src_lang} sang {dst_lang}.
Yêu cầu bắt buộc:
1. Dịch tự nhiên, mượt mà, phù hợp với ngữ cảnh đàm thoại.
2. Trả về ĐÚNG định dạng như đầu vào: [ID] Nội dung đã dịch.
3. KHÔNG thêm bất kỳ bình luận hay giải thích nào khác.

Nội dung cần dịch:
{batch_text}
"""
        # Sử dụng asyncio.to_thread để chạy synchronous API call trong background thread
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=self.model,
            contents=prompt
        )
        
        if not response or not response.text:
            raise ValueError("Empty response from Gemini")
            
        return response.text

class TranslationValidator:
    @staticmethod
    def validate_and_parse(response_text: str, expected_ids: List[int], original_source: str, is_last_attempt: bool = False) -> Dict[int, str]:
        """
        Validate kết quả trả về từ API xem có đủ các ID không.
        Trả về dictionary map từ ID -> translated_text.
        """
        result = {}
        lines = response_text.strip().split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Regex bắt: [123] Nội dung
            match = re.search(r'^\[(\d+)\]\s*(.*)', line)
            if match:
                idx = int(match.group(1))
                content = match.group(2).strip()
                result[idx] = content
                
        # Kiểm tra xem có thiếu ID nào không
        missing_ids = [idx for idx in expected_ids if idx not in result]
        if missing_ids:
            if not is_last_attempt:
                raise ValueError(f"Missing translations for IDs: {missing_ids}")
            else:
                # Nếu là lần thử cuối cùng, đành chấp nhận kết quả thiếu và đắp văn bản gốc vào
                # Parse văn bản gốc để lấy câu gốc
                orig_dict = {}
                for line in original_source.split('\n'):
                    m = re.search(r'^\[(\d+)\]\s*(.*)', line.strip())
                    if m:
                        orig_dict[int(m.group(1))] = m.group(2).strip()
                
                for idx in missing_ids:
                    result[idx] = orig_dict.get(idx, "...")
            
        return result
