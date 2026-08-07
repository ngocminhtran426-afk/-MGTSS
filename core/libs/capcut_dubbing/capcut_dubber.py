import os
import sys
import time
import json
import re
import math
import srt
import uuid
import random
import requests
import subprocess
import threading
import datetime
import shutil
import psutil
from pathlib import Path
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor, as_completed

TOOL_ROOT = Path(__file__).resolve().parents[3]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from tool_paths import ToolPaths

# Template Engine - overlay text, watermark, blur, BGM
try:
    from .template_engine import (
        build_ffmpeg_filter_complex_with_template,
        build_bgm_mix_cmd,
        build_default_variables,
        load_template,
        get_template_by_index,
    )
    TEMPLATE_ENGINE_AVAILABLE = True
except ImportError as e:
    TEMPLATE_ENGINE_AVAILABLE = False
    print(f"[WARN] template_engine không khả dụng: {e}")

VIET_HOA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "viet_hoa_video"))
if os.path.isdir(VIET_HOA_DIR) and VIET_HOA_DIR not in sys.path:
    sys.path.insert(0, VIET_HOA_DIR)

try:
    from viethoa_preprocess import run_viethoa_preprocess
    VIET_HOA_AVAILABLE = True
except Exception as e:
    VIET_HOA_AVAILABLE = False
    print(f"[WARN] Viet hoa preprocess khong kha dung: {e}")

PATHS = ToolPaths.from_root(TOOL_ROOT)
TEMP_DIR = os.fspath(PATHS.capcut_temp_dir())

# Tắt các cảnh báo vô hại của HuggingFace để tránh làm rác log giao diện
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

# --- VieNeu-TTS Singleton ---
_vieneu_engine = None
_vieneu_lock = threading.Lock()

def get_vieneu_engine():
    global _vieneu_engine
    if _vieneu_engine is None:
        with _vieneu_lock:
            if _vieneu_engine is None:
                print("\n[VieNeu-TTS] Đang nạp mô hình ONNX siêu thực vào bộ nhớ (Chỉ chạy 1 lần duy nhất)...", file=sys.stderr)
                from vieneu import Vieneu
                _vieneu_engine = Vieneu()
    return _vieneu_engine

def generate_vieneu_tts(text, voice, mode="local", api_key="", emotion="natural"):
    if mode == "api":
        if not api_key:
            print("[!] Lỗi: Chế độ API nhưng chưa cung cấp API Key VieNeu.", file=sys.stderr)
            return AudioSegment.empty()
        
        try:
            url = "https://api.vieneu.io/api/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "input": text,
                "voice": voice,
                "response_format": "wav",
                "aiRefine": False,
                "emotion": emotion
            }
            
            for retry in range(5):
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if resp.status_code == 200:
                    tmp_path = os.path.join(TEMP_DIR, f"tmp_vieneu_api_{uuid.uuid4().hex[:8]}.wav")
                    with open(tmp_path, "wb") as f:
                        f.write(resp.content)
                    
                    audio_seg = AudioSegment.from_file(tmp_path, format="wav")
                    try: os.remove(tmp_path)
                    except: pass
                    return audio_seg
                elif resp.status_code == 429 or resp.status_code >= 500:
                    sleep_time = (retry + 1) * 1.5 + random.uniform(0.1, 2.0)
                    print(f"[*] Máy chủ API bận ({resp.status_code}). Chờ {sleep_time:.1f} giây để thử lại (Lần {retry+1}/5)...", file=sys.stderr)
                    time.sleep(sleep_time)
                    continue
                else:
                    print(f"[!] Lỗi API VieNeu: {resp.status_code} - {resp.text}", file=sys.stderr)
                    return AudioSegment.empty()
            print("[!] Lỗi API VieNeu: Đã thử lại 3 lần nhưng vẫn quá tải (429).", file=sys.stderr)
            return AudioSegment.empty()
        except Exception as e:
            print(f"[!] Lỗi kết nối VieNeu API: {e}", file=sys.stderr)
            return AudioSegment.empty()
            
    # Local CPU mode
    engine = get_vieneu_engine()
    audio = engine.infer(text, voice=voice, style="tu_nhien")
    tmp_path = os.path.join(TEMP_DIR, f"tmp_vieneu_{uuid.uuid4().hex[:8]}.wav")
    engine.save(audio, tmp_path)
    
    if os.path.exists(tmp_path):
        audio_seg = AudioSegment.from_file(tmp_path, format="wav")
        for _ in range(5):
            try:
                os.remove(tmp_path)
                break
            except Exception:
                time.sleep(0.5)
        return audio_seg
    return AudioSegment.empty()
# ----------------------------

from .capcut_common_task_client import build_request

class Args:
    pass

ip_lock = threading.Lock()
last_ip_change = 0

def update_fake_device(dev_file):
    fake_dev = {
        "device_id": str(random.randint(1000000000000000000, 9999999999999999999)),
        "iid": str(random.randint(1000000000000000000, 9999999999999999999)),
    }
    fake_dev["tdid"] = fake_dev["device_id"]
    with open(dev_file, "w") as f:
        json.dump(fake_dev, f)
    return dev_file

def request_with_retry(text, args, max_retries=10):
    global last_ip_change
    
    for attempt in range(max_retries):
        url, headers, body_text = build_request(args)
        
        try:
            resp = requests.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=60).json()
        except Exception as e:
            print(f"[!] Network error: {str(e)}")
            time.sleep(3)
            continue
            
        if "data" not in resp or not resp["data"] or "tasks" not in resp["data"]:
            err_msg = resp.get("errmsg", "").lower()
            if "shark block" in err_msg or "rate limit" in err_msg or resp.get("ret") == "-6" or resp.get("ret") == -6:
                print(f"[!] Bị chặn IP (shark block). Đang đợi đổi VPN... (Lần {attempt+1}/{max_retries})")
                
                with ip_lock:
                    if time.time() - last_ip_change > 20:
                        print("\n>> Kích hoạt WARP-CLI: Disconnecting...")
                        subprocess.run(["warp-cli", "disconnect"], capture_output=True)
                        time.sleep(3)
                        
                        print(">> Kích hoạt WARP-CLI: Connecting...")
                        subprocess.run(["warp-cli", "connect"], capture_output=True)
                        time.sleep(8)
                        
                        last_ip_change = time.time()
                        print(">> Đã đổi IP xong, các luồng tiếp tục chạy!\n")
                    else:
                        time.sleep(2)
                
                update_fake_device(args.device_json)
                continue
            else:
                print(f"API Error for text '{text}': {resp}")
                return None
        return resp
        
    print(f"Failed to generate TTS after {max_retries} retries for text: {text}")
    return None

def generate_capcut_tts(text, rate=1.0, voice="BV074_streaming", resource_id="7102355709945188865"):
    dev_file = os.path.join(TEMP_DIR, f"temp_dev_{uuid.uuid4().hex}.json")
    update_fake_device(dev_file)
        
    try:
        args = Args()
        args.mode = "tts-new"
        args.device_json = dev_file
        args.text = [text]
        args.text_file = None
        args.voice = voice
        args.resource_id = resource_id
        args.rate = f"{rate:.2f}"
        
        resp = request_with_retry(text, args)
        if not resp:
            return AudioSegment.empty()
            
        task_info = resp["data"]["tasks"][0]
        task_id = task_info["id"]
        token = task_info["token"]
        
        args.mode = "tts-query"
        args.task_id = task_id
        args.token = token
        args.bind_id = ""
        
        for query_attempt in range(30):
            time.sleep(2)
            
            resp_query = request_with_retry(text, args)
            if not resp_query:
                return AudioSegment.empty()
                
            status = resp_query["data"]["tasks"][0]["status"]
            
            if status == "succeed":
                payload = json.loads(resp_query["data"]["tasks"][0]["payload"])
                speech_url = payload["audio_subtitles"][0]["speech_url"]
                
                try:
                    audio_data = requests.get(speech_url, timeout=60).content
                except Exception as e:
                    print(f"Failed to download audio for {text}: {e}")
                    return AudioSegment.empty()
                
                tmp_path = os.path.join(TEMP_DIR, f"tmp_{task_id}_{uuid.uuid4().hex[:8]}.mp3")
                with open(tmp_path, "wb") as f:
                    f.write(audio_data)
                    
                audio_seg = AudioSegment.from_file(tmp_path, format="mp3")
                
                for _ in range(5):
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        break
                    except Exception:
                        time.sleep(0.5)
                        
                return audio_seg
                
            elif status == "failed":
                print(f"TTS Failed for text: {text}")
                return AudioSegment.empty()
                
        print(f"TTS Timeout for text: {text}")
        return AudioSegment.empty()
    finally:
        if os.path.exists(dev_file):
            os.remove(dev_file)

def split_text(text):
    parts = re.split(r'([.?!,\n]+)', text)
    sentences = []
    for i in range(0, len(parts), 2):
        phrase = parts[i].strip()
        punc = parts[i+1] if i+1 < len(parts) else ""
        if phrase:
            sentences.append((phrase, punc))
    return sentences

def build_atempo_chain(factor):
    chain = []
    while factor < 0.5:
        chain.append("atempo=0.5")
        factor /= 0.5
    while factor > 2.0:
        chain.append("atempo=2.0")
        factor /= 2.0
    chain.append(f"atempo={factor:.4f}")
    return ",".join(chain)

def apply_audio_effects(audio_segment, volume_db=0.0, pitch_semitones=0.0, speed_factor=1.0):
    if volume_db != 0:
        audio_segment += volume_db
        
    if pitch_semitones == 0 and speed_factor == 1.0:
        return audio_segment
        
    tmp_in = os.path.join(TEMP_DIR, f"tmp_eff_in_{uuid.uuid4().hex[:8]}.wav")
    tmp_out = os.path.join(TEMP_DIR, f"tmp_eff_out_{uuid.uuid4().hex[:8]}.wav")
    audio_segment.export(tmp_in, format="wav")
    
    sr = audio_segment.frame_rate
    new_sr = int(sr * (2.0 ** (pitch_semitones / 12.0)))
    
    required_atempo = speed_factor / (new_sr / sr)
    atempo_str = build_atempo_chain(required_atempo)
    
    if pitch_semitones != 0:
        filter_str = f"asetrate={new_sr},{atempo_str}"
    else:
        filter_str = atempo_str
        
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.IDLE_PRIORITY_CLASS
        
    res_ff = subprocess.run(["ffmpeg", "-y", "-i", tmp_in, "-filter:a", filter_str, "-ar", "44100", tmp_out], capture_output=True, creationflags=creationflags)
    
    if res_ff.returncode != 0:
        print(f"[FFMPEG LỖI] Lỗi apply_audio_effects: {res_ff.stderr.decode('utf-8', errors='ignore')}", file=sys.stderr)
        # Nếu FFmpeg lỗi, trả về audio gốc để không bị crash
        res = audio_segment
    elif os.path.exists(tmp_out):
        res = AudioSegment.from_file(tmp_out, format="wav")
    else:
        res = audio_segment
        
    for f in [tmp_in, tmp_out]:
        for _ in range(5):
            try:
                if os.path.exists(f): os.remove(f)
                break
            except Exception:
                time.sleep(0.5)
            
    return res

# --- Piper-TTS Pool ---
_piper_engines = []
_piper_lock = threading.Lock()
_engine_index = 0

DEBUG_LOG = os.path.join(TEMP_DIR, "piper_debug.log")
def log_debug(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")

class PiperEngine:
    def __init__(self, piper_model, script_dir):
        self.piper_model = piper_model
        self.script_dir = script_dir
        self.lock = threading.Lock()
        self._start_process()

    def _start_process(self):
        piper_exe = os.path.join(self.script_dir, "piper.exe")
        espeak_data = os.path.join(self.script_dir, "espeak-ng-data")
        cmd = [piper_exe, "--model", self.piper_model, "--espeak_data", espeak_data, "--json-input", "--quiet"]
        
        # Set below normal priority to prevent system lag
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.IDLE_PRIORITY_CLASS

        self.process = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            creationflags=creationflags,
            cwd=TEMP_DIR
        )

    def infer(self, text):
        # Sanitize text to prevent piper crashes
        text = text.replace('"', '').replace('\n', ' ')
        out_filename = f"tmp_piper_{uuid.uuid4().hex[:8]}.wav"
        payload = json.dumps({"text": text, "output_file": out_filename}) + "\n"
        with self.lock:
            if self.process.poll() is not None:
                err_msg = f"Process đã chết (exit={self.process.returncode}), đang restart..."
                print(f"[Piper] {err_msg}", file=sys.stderr)
                log_debug(err_msg)
                self._start_process()
                
            try:
                self.process.stdin.write(payload)
                self.process.stdin.flush()
                
                out_line = self.process.stdout.readline()
                if not out_line:
                    err_msg = "stdout trả về rỗng, process đã chết. Restarting..."
                    print(f"[Piper] {err_msg}", file=sys.stderr)
                    log_debug(err_msg)
                    self._start_process()
                    return None
                    
                if out_line:
                    out_path = os.path.join(TEMP_DIR, out_line.strip())
                    if os.path.exists(out_path):
                        return out_path
                    else:
                        err_msg = f"File không tồn tại: {out_path} (stdout={out_line.strip()!r})"
                        print(f"[Piper] {err_msg}", file=sys.stderr)
                        log_debug(err_msg)
            except BrokenPipeError:
                err_msg = "BrokenPipeError - process đã chết bất ngờ. Restarting..."
                print(f"[Piper] {err_msg}", file=sys.stderr)
                log_debug(err_msg)
                self._start_process()
            except Exception as e:
                err_msg = f"Lỗi: {type(e).__name__}: {e}"
                print(f"[Piper] {err_msg}", file=sys.stderr)
                log_debug(err_msg)
                self._start_process()
        return None

def get_piper_engine(piper_model):
    global _piper_engines, _piper_lock, _engine_index
    with _piper_lock:
        if not _piper_engines:
            # Khởi tạo 4 luồng Piper để chạy song song (tăng tốc 4x)
            num_engines = 4
            print(f"\n[Piper-TTS] Đang nạp {num_engines} luồng mô hình ONNX vào bộ nhớ để chạy song song...", file=sys.stderr)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            for _ in range(num_engines):
                _piper_engines.append(PiperEngine(piper_model, script_dir))
        
        # Trả về engine theo kiểu round-robin
        engine = _piper_engines[_engine_index]
        _engine_index = (_engine_index + 1) % len(_piper_engines)
        return engine

def generate_piper_tts(text, piper_model):
    if not piper_model or not str(piper_model).endswith(".onnx"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_models_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "..", "models"))
        if os.path.exists(root_models_dir):
            import glob
            onnx_files = glob.glob(os.path.join(root_models_dir, "*.onnx"))
            if onnx_files:
                piper_model = onnx_files[0]
                print(f"[DUB] [DEBUG] Fallback to first available model: {piper_model}")
                
    engine = get_piper_engine(piper_model)
    tmp_path = engine.infer(text)
    
    if tmp_path and os.path.exists(tmp_path):
        audio_seg = AudioSegment.from_file(tmp_path, format="wav")
        for _ in range(5):
            try:
                os.remove(tmp_path)
                break
            except Exception:
                time.sleep(0.5)
        return audio_seg
    else:
        print(f"Piper failed for text: {text}")
        return AudioSegment.empty()

def chunk_text(text, max_chars=90):
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        # Nếu cộng thêm từ này vượt quá max_chars, ta ngắt chunk
        if current_length + len(word) + (1 if current_length > 0 else 0) > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_length = len(word)
        else:
            current_chunk.append(word)
            current_length += len(word) + (1 if current_length > 0 else 0)
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def _generate_fpt_tts_chunk(text, voice, api_key, attempt_outer=0):
    url = "https://api.fpt.ai/hmi/tts/v5"
    headers = {
        "api_key": api_key,
        "voice": voice,
        "Cache-Control": "no-cache"
    }
    
    # FPT TTS yêu cầu text tối thiểu 3 ký tự. Thêm dấu chấm để đệm nếu quá ngắn.
    padded_text = text.strip()
    while len(padded_text) < 3:
        padded_text += "."
        
    attempt = 0
    max_outer_attempts = 3
    while attempt < max_outer_attempts:
        attempt += 1
        try:
            resp = requests.post(url, headers=headers, data=padded_text.encode('utf-8'), timeout=20)
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"FPT TTS Server Error {resp.status_code}. Thử lại lần {attempt}...", file=sys.stderr)
                time.sleep(3)
                continue
                
            if resp.status_code != 200:
                print(f"FPT TTS Error: {resp.status_code} - {resp.text}. Thử lại lần {attempt}...", file=sys.stderr)
                time.sleep(3)
                continue
                
            data = resp.json()
            if data.get("error") != 0 or "async" not in data:
                print(f"FPT TTS API Error: {data}. Thử lại lần {attempt}...", file=sys.stderr)
                time.sleep(3)
                continue
                
            async_url = data["async"]
            
            # Polling (Tối đa 2 phút chờ)
            max_polling_attempts = 40
            for i in range(max_polling_attempts):
                time.sleep(3) # Tăng thời gian chờ mỗi lần poll lên 3s để tránh bị cấm IP
                try:
                    audio_resp = requests.get(async_url, timeout=10)
                    if audio_resp.status_code == 200:
                        # Kiểm tra xem có phải FPT trả về JSON lỗi hay không
                        content_type = audio_resp.headers.get("Content-Type", "")
                        if "json" in content_type:
                            continue # Vẫn chưa sẵn sàng
                            
                        tmp_path = os.path.join(TEMP_DIR, f"tmp_fpt_{uuid.uuid4().hex[:8]}.mp3")
                        with open(tmp_path, "wb") as f:
                            f.write(audio_resp.content)
                        seg = AudioSegment.from_file(tmp_path, format="mp3")
                        if os.path.exists(tmp_path): os.remove(tmp_path)
                        return seg
                except Exception as e:
                    pass
                    
            print(f"FPT TTS Polling Timeout cho đoạn: {text}. Bắt đầu gửi lại yêu cầu (Lần {attempt})...", file=sys.stderr)
            time.sleep(2)
            
        except Exception as e:
            print(f"FPT TTS Exception (Attempt {attempt}): {str(e)}", file=sys.stderr)
            time.sleep(2)

    # Nếu thử lại quá số lần mà vẫn thất bại, trả về audio câm để tránh treo luồng (hanging)
    print(f"FPT TTS thất bại hoàn toàn sau {max_outer_attempts} lần thử cho đoạn: {text}. Bỏ qua đoạn này.", file=sys.stderr)
    return AudioSegment.empty()

def generate_fpt_tts(text, voice, api_key):
    chunks = chunk_text(text, max_chars=90)
    final_audio = AudioSegment.empty()
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  -> Xử lý chunk {i+1}/{len(chunks)} cho FPT ({len(chunk)} ký tự): {chunk[:40]}...")
        seg = _generate_fpt_tts_chunk(chunk, voice, api_key)
        final_audio += seg
    return final_audio

def synthesize_block_audio(sub, voice="BV074_streaming", resource_id="7102355709945188865", tts_method="CapCut API", piper_model="", tts_api_key="", volume_db=0.0, pitch_semitones=0.0, speed_factor=1.0, vieneu_mode="local", vieneu_api_key="", vieneu_emotion="natural"):
    # Tự động loại bỏ dấu phẩy để tránh ngắt nghỉ không mong muốn
    content = sub.content.replace(",", "").replace("，", "")
    
    target_duration_ms = (sub.end - sub.start).total_seconds() * 1000
    if target_duration_ms <= 0:
        target_duration_ms = 1000  # Fallback 1s tránh lỗi chia cho 0
        
    if not content.strip():
        seg = AudioSegment.silent(duration=int(target_duration_ms))
        tmp_wav = os.path.join(TEMP_DIR, f"tmp_audio_{uuid.uuid4().hex[:8]}.wav")
        seg.export(tmp_wav, format="wav")
        return tmp_wav, target_duration_ms, target_duration_ms

    sentences = split_text(content)
    def generate_for_sentences(rate):
        audio_block = AudioSegment.empty()
        for phrase, punc in sentences:
            if tts_method.lower() in ["piper", "piper offline"]:
                seg = generate_piper_tts(phrase, piper_model)
            elif tts_method.lower() == "fpt":
                seg = generate_fpt_tts(phrase, voice, tts_api_key)
            elif tts_method.lower() == "vieneu":
                seg = generate_vieneu_tts(phrase, voice, mode=vieneu_mode, api_key=vieneu_api_key, emotion=vieneu_emotion)
            else:
                seg = generate_capcut_tts(phrase, rate=rate, voice=voice, resource_id=resource_id)
            audio_block += seg
        return audio_block

    # Default capcut rate = 1.1
    audio_block = generate_for_sentences(rate=1.1)
    
    # Apply user audio effects (Volume, Pitch, Speed)
    audio_block = apply_audio_effects(audio_block, volume_db, pitch_semitones, speed_factor)
    
    final_duration_ms = len(audio_block)
    
    # [FIX] Chống lỗi tua nhanh video khi rớt câu (hoặc câu quá ngắn)
    # Nếu âm thanh cuối cùng quá ngắn (< 30% thời lượng) và <= 2000ms, 
    # tỷ lệ cao là lỗi rớt câu hoặc câu quá ngắn. Ta bù silence để video chạy bình thường.
    # TUY NHIÊN: Nếu final_duration_ms == 0 (tức là lỗi API hoàn toàn), KHÔNG bù silence để Checkpoint 1 phát hiện và tạo lại.
    if final_duration_ms > 0 and final_duration_ms < target_duration_ms * 0.3 and final_duration_ms <= 2000:
        missing_ms = target_duration_ms - final_duration_ms
        if missing_ms > 0:
            print(f"BÙ SILENCE: Phát hiện rớt câu TTS, đã bù {int(missing_ms)}ms khoảng trắng để chống tua nhanh.", file=sys.stderr)
            audio_block += AudioSegment.silent(duration=int(missing_ms))
            final_duration_ms = len(audio_block)
            
    tmp_wav = os.path.join(TEMP_DIR, f"tmp_audio_{uuid.uuid4().hex[:8]}.wav")
    audio_block.export(tmp_wav, format="wav")
    return tmp_wav, target_duration_ms, final_duration_ms

def process_sub_worker(sub, index, total, voice="BV074_streaming", resource_id="7102355709945188865", tts_method="CapCut API", piper_model="", tts_api_key="", volume_db=0.0, pitch_semitones=0.0, speed_factor=1.0, vieneu_mode="local", vieneu_api_key="", vieneu_emotion="natural"):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [INFO] [DUB] --- [Audio] Tải câu {index}/{total}...")
    start_sec = sub.start.total_seconds()
    wav_path, target_dur_ms, final_dur_ms = synthesize_block_audio(sub, voice, resource_id, tts_method, piper_model, tts_api_key, volume_db, pitch_semitones, speed_factor, vieneu_mode, vieneu_api_key, vieneu_emotion)
    return index, start_sec, target_dur_ms/1000.0, final_dur_ms/1000.0, wav_path, sub

def get_video_info(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    dur = float(subprocess.check_output(cmd).decode('utf-8').strip())
    
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", video_path]
    output = subprocess.check_output(cmd).decode('utf-8').strip().split(',')
    
    width = int(output[0])
    height = int(output[1])
    
    fps_str = output[2]
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)
        
    return dur, fps, width, height

def preprocess_srt(subs, tts_method="", vieneu_mode=""):
    print("\\n[KIỂM TRA] Đang tiền xử lý và dọn dẹp file SRT...")
    fixed_subs = []
    for i, sub in enumerate(subs):
        duration = (sub.end - sub.start).total_seconds()
        
        # 1. Tự động sửa lỗi nếu câu thoại dài một cách vô lý (> 30 giây) do gõ nhầm thời gian
        if duration > 30.0:
            print(f"  [*] Đã tự động sửa lỗi thời lượng quá dài (>30s) ở câu {sub.index}.")
            # Chỉnh lại thời lượng dựa trên số lượng chữ (ước tính trung bình 3-5 từ/giây)
            estimated_duration = max(3.0, min(15.0, len(sub.content) * 0.2))
            sub.end = sub.start + datetime.timedelta(seconds=estimated_duration)
            
        # 2. Tự động sửa lỗi nếu thời gian kết thúc nhỏ hơn thời gian bắt đầu
        if duration < 0:
            print(f"  [*] Đã tự động sửa lỗi thời gian âm ở câu {sub.index}.")
            estimated_duration = max(3.0, min(15.0, len(sub.content) * 0.2))
            sub.end = sub.start + datetime.timedelta(seconds=estimated_duration)
            
        # 3. Tự động sửa lỗi Overlap (câu sau xuất hiện khi câu trước chưa kết thúc)
        if i > 0:
            prev_end = fixed_subs[-1].end
            if sub.start < prev_end:
                print(f"  [*] Đã tự động sửa lỗi thời gian đè nhau ở câu {sub.index}.")
                sub.start = prev_end
                
        # 4. Đảm bảo 100% thời lượng luôn lớn hơn 0 (không bao giờ = 0s)
        if (sub.end - sub.start).total_seconds() <= 0:
            print(f"  [*] Đã tự động ép thời lượng cho câu {sub.index} (do bị 0s).")
            estimated_duration = max(1.0, min(15.0, len(sub.content) * 0.2))
            sub.end = sub.start + datetime.timedelta(seconds=estimated_duration)
            
        fixed_subs.append(sub)
        
    # 5. Gộp các câu phụ đề đứng sát nhau (khoảng cách <= 0.3s) để TTS đọc mượt hơn và giảm luồng
    # Yêu cầu: Chỉ áp dụng cho VieNeu Local
    if tts_method.lower() == "vieneu" and vieneu_mode.lower() == "local":
        merged_subs = []
        for sub in fixed_subs:
            if not merged_subs:
                merged_subs.append(sub)
            else:
                prev = merged_subs[-1]
                gap = (sub.start - prev.end).total_seconds()
                
                # Gộp nếu khoảng cách <= 0.3s và tổng thời lượng sau khi gộp <= 15s
                if gap <= 0.3 and (sub.end - prev.start).total_seconds() <= 15.0:
                    prev.end = sub.end
                    prev.content = f"{prev.content} {sub.content}"
                else:
                    merged_subs.append(sub)
                    
        # Cập nhật lại index cho đẹp
        for i, sub in enumerate(merged_subs):
            sub.index = i + 1
            
        print(f"  [+] Đã gộp các câu phụ đề gần nhau (chế độ VieNeu Local). Từ {len(fixed_subs)} câu giảm còn {len(merged_subs)} câu.")
        fixed_subs = merged_subs
        
    print("[KIỂM TRA] File SRT hoàn toàn hợp lệ!")
    return fixed_subs

def get_optimal_threads(task_type, base_max_workers, gpu_enabled=False):
    import psutil
    import subprocess
    
    cpu_cores = os.cpu_count() or 4
    mem = psutil.virtual_memory()
    free_ram_gb = mem.available / (1024 * 1024 * 1024)
    
    if task_type == "audio":
        max_by_ram = max(1, int(free_ram_gb / 0.5))
        optimal = min(base_max_workers, cpu_cores, max_by_ram)
        print(f"[SYSTEM] Tài nguyên Audio TTS: Trống {free_ram_gb:.1f}GB RAM. Khởi động {optimal} luồng.")
        return optimal
        
    elif task_type == "video":
        if gpu_enabled:
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                res = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, startupinfo=startupinfo)
                if res.returncode == 0:
                    vram_mb_strs = res.stdout.strip().split('\n')
                    if vram_mb_strs:
                        vram_mb = int(vram_mb_strs[0].strip())
                        max_by_vram = max(1, vram_mb // 800)
                        optimal = min(base_max_workers, max_by_vram, 4) # Giới hạn 4 luồng GPU để tránh nghẽn I/O
                        print(f"[SYSTEM] Tài nguyên GPU NVIDIA: Trống {vram_mb}MB VRAM. Khởi động {optimal} luồng Render phần cứng.")
                        return optimal
            except Exception:
                pass
            print(f"[SYSTEM] Cảnh báo: Đang dùng GPU phần cứng nhưng không quét được VRAM, giới hạn an toàn 2 luồng.")
            return min(2, base_max_workers)
        else:
            max_by_ram = max(1, int(free_ram_gb / 1.5))
            max_by_cpu = max(1, cpu_cores - 1)
            # Giới hạn tối đa 3 luồng vì FFmpeg x264 chiếm rất nhiều CPU và gây lag
            optimal = min(max_by_ram, max_by_cpu, base_max_workers, 3)
            print(f"[SYSTEM] Tài nguyên CPU Video: Trống {free_ram_gb:.1f}GB RAM, {cpu_cores} Cores. Khởi động {optimal} luồng Render phần mềm (đã giới hạn chống lag).")
            return optimal
            
    elif task_type == "vfx":
        max_by_ram = max(1, int(free_ram_gb / 1.0))
        max_by_cpu = max(1, cpu_cores - 1)
        optimal = min(max_by_ram, max_by_cpu)
        print(f"[SYSTEM] Tài nguyên VideoSubFinder: Trống {free_ram_gb:.1f}GB RAM. Giới hạn {optimal} luồng OCR (chừa 1 core).")
        return optimal

    return base_max_workers

def get_best_encoder():
    try:
        # Thử NVIDIA NVENC
        res = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:s=128x128", "-c:v", "h264_nvenc", "-t", "0.1", "-f", "null", "-"], capture_output=True)
        if res.returncode == 0:
            return "h264_nvenc", ["-preset", "p4", "-cq", "20", "-b:v", "0"]
            
        # Thử Intel QSV
        res = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:s=128x128", "-c:v", "h264_qsv", "-t", "0.1", "-f", "null", "-"], capture_output=True)
        if res.returncode == 0:
            return "h264_qsv", ["-preset", "veryfast", "-global_quality", "20"]
            
        # Thử AMD AMF
        res = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:s=128x128", "-c:v", "h264_amf", "-t", "0.1", "-f", "null", "-"], capture_output=True)
        if res.returncode == 0:
            return "h264_amf", []
    except Exception:
        pass
        
    # Fallback về CPU (cực nhanh nhưng nét hơn)
    return "libx264", ["-preset", "superfast", "-crf", "20", "-threads", "2"]

def render_ffmpeg_chunk(chunk, video_path, out_chunk, video_norm, fps, random_flip=False, template=None, variables=None, total_video_duration=0.0):
    encoder, enc_params = get_best_encoder()
    
    flip_str = ""
    if random_flip and random.choice([True, False]):
        flip_str = ",hflip"
    
    # --- Template Integration ---
    # Nếu có template VÀ template_engine khả dụng, dùng template engine để build filter_complex
    if template and TEMPLATE_ENGINE_AVAILABLE:
        # Lấy kích thước video từ video_norm string (vd: "scale=1920:1080,...")
        try:
            norm_parts = video_norm.split(",")[0]  # "scale=1920:1080"
            wh = norm_parts.replace("scale=", "").split(":")
            vw, vh = int(wh[0]), int(wh[1])
        except Exception:
            vw, vh = 1920, 1080
        
        if chunk["type"] == "gap":
            factor = 1.0
            has_tts = False
        else:
            if chunk["duration"] > 0 and chunk["final_duration"] > 0:
                factor = chunk["final_duration"] / chunk["duration"]
            else:
                factor = 1.0
            has_tts = True if chunk["final_duration"] > 0 else False
        
        filter_complex, extra_inputs = build_ffmpeg_filter_complex_with_template(
            template=template,
            video_width=vw, video_height=vh,
            video_norm=video_norm, flip_str=flip_str,
            chunk_type=chunk["type"],
            factor=factor,
            has_tts_audio=has_tts,
            variables=variables,
            chunk_start=chunk["start"],
            chunk_duration=chunk["duration"],
            total_video_duration=total_video_duration
        )
        
        # Build command
        cmd = ["ffmpeg", "-y", "-ss", f"{chunk['start']:.3f}", "-t", f"{chunk['duration']:.3f}"]
        cmd += ["-i", video_path]
        if chunk["type"] == "sub":
            cmd += ["-i", chunk["audio_file"]]
        for extra_path in extra_inputs:
            cmd += ["-i", extra_path]
        
        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", "[vout]", "-map", "[aout]"]
        cmd += ["-c:v", encoder] + enc_params
        cmd += ["-r", str(fps), "-c:a", "pcm_s16le", "-ac", "2", "-ar", "44100", "-shortest"]
        cmd += [out_chunk]
        
        creationflags = subprocess.IDLE_PRIORITY_CLASS if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, creationflags=creationflags)
        return res
    
    # --- Fallback: Logic gốc (không có template) ---
    if chunk["type"] == "gap":
        cmd = [
            "ffmpeg", "-y", "-ss", f"{chunk['start']:.3f}", "-t", f"{chunk['duration']:.3f}",
            "-i", video_path,
            "-filter_complex", f"[0:v]setpts=PTS-STARTPTS,{video_norm}{flip_str}[vout];[0:a]asetpts=PTS-STARTPTS,apad[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", encoder
        ] + enc_params + [
            "-r", str(fps),
            "-c:a", "pcm_s16le", "-ac", "2", "-ar", "44100",
            "-shortest",
            out_chunk
        ]
        creationflags = subprocess.IDLE_PRIORITY_CLASS if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, creationflags=creationflags)
        return res
    else:
        wav_path = chunk["audio_file"]
        if chunk["duration"] > 0 and chunk["final_duration"] > 0:
            factor = chunk["final_duration"] / chunk["duration"]
            has_tts = True
        else:
            factor = 1.0
            has_tts = False
            
        # Áp dụng cho CẢ 2 trường hợp: AI nói chậm (factor > 1) và AI nói nhanh (factor < 1) để khớp hình
        if has_tts and abs(factor - 1.0) > 0.001:
            inv_factor = 1.0 / factor
            atempo_str = build_atempo_chain(inv_factor)
            filter_complex = (
                f"[0:v]setpts={factor}*(PTS-STARTPTS),{video_norm}{flip_str}[vout];"
                f"[0:a]asetpts=PTS-STARTPTS,{atempo_str},apad,volume=0.15[a0];"
                f"[1:a]asetpts=PTS-STARTPTS,apad,volume=1.0[a1];"
                f"[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
            )
        elif has_tts:
            filter_complex = (
                f"[0:v]setpts=PTS-STARTPTS,{video_norm}{flip_str}[vout];"
                f"[0:a]asetpts=PTS-STARTPTS,apad,volume=0.15[a0];"
                f"[1:a]asetpts=PTS-STARTPTS,apad,volume=1.0[a1];"
                f"[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
            )
        else:
            filter_complex = f"[0:v]setpts=PTS-STARTPTS,{video_norm}{flip_str}[vout];[0:a]asetpts=PTS-STARTPTS,apad[aout]"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{chunk['start']:.3f}", "-t", f"{chunk['duration']:.3f}",
            "-i", video_path, "-i", wav_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", encoder
        ] + enc_params + [
            "-r", str(fps),
            "-c:a", "pcm_s16le", "-ac", "2", "-ar", "44100",
            "-shortest",
            out_chunk
        ]
        creationflags = subprocess.IDLE_PRIORITY_CLASS if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, creationflags=creationflags)
        return res

def resolve_template_paths(template_data):
    if not template_data:
        return
    import os
    try:
        from tool_paths import ToolPaths
        paths = ToolPaths.from_root()
    except ImportError:
        return

    def _resolve(path_str):
        if not path_str:
            return path_str
        if path_str.startswith("assets/") or path_str.startswith("assets\\"):
            basename = os.path.basename(path_str.replace("\\", "/"))
            return str(paths.assets_dir / basename)
        return path_str

    if 'bgmPath' in template_data:
        template_data['bgmPath'] = _resolve(template_data['bgmPath'])
    
    for elem in template_data.get('elements', []):
        if elem.get('type') == 'watermark' and 'logoPath' in elem:
            elem['logoPath'] = _resolve(elem['logoPath'])

def process_srt_to_video(srt_path, video_path, output_path, max_workers=10, voice="BV074_streaming", resource_id="7102355709945188865", tts_method="CapCut API", piper_model="", tts_api_key="", volume_db=0.0, pitch_semitones=0.0, speed_factor=1.0, vieneu_mode="local", vieneu_api_key="", vieneu_emotion="natural", random_flip=False, skip_concat=False, template=None, video_title="", source_url="", gemini_api_key="", channel_name="", extra_prompt="", viethoa_output_dir=""):
    if not os.path.exists(video_path):
        print(f"Lỗi: Không tìm thấy file video {video_path}")
        return

    resolve_template_paths(template)

    viethoa_result = None
    source_url = (source_url or "").strip()
    
    # [FIX] Tự động đọc info.json từ thư mục _viet_hoa do C# tạo ra (nếu có)
    # Vì C# có thể không truyền source_url vào đây.
    expected_viethoa_dir = os.path.abspath(os.path.splitext(video_path)[0] + "_viet_hoa")
    if os.path.exists(expected_viethoa_dir):
        info_path = os.path.join(expected_viethoa_dir, "info.json")
        if os.path.exists(info_path):
            try:
                import json
                with open(info_path, 'r', encoding='utf-8') as f:
                    info_data = json.load(f)
                
                viethoa_result = {
                    "original_title": info_data.get("title_original", ""),
                    "translated_title": info_data.get("title_viet", ""),
                    "video_title_with_prefix": info_data.get("video_title_with_prefix", ""),
                    "short_title": info_data.get("short_title", "")
                }
                if viethoa_result.get("translated_title") and not video_title:
                    video_title = viethoa_result["translated_title"]
                print(f"[PREPROCESS] Đã tự động nạp tiêu đề tiếng Việt từ: {info_path}")
            except Exception as e:
                print(f"Lỗi đọc info.json: {e}")

    if source_url and not viethoa_result:
        if not VIET_HOA_AVAILABLE:
            raise RuntimeError(
                "Module Viet hoa chua san sang. Hay cai dependency cho modules/viet_hoa_video."
            )

        resolved_viethoa_dir = (
            viethoa_output_dir.strip()
            if isinstance(viethoa_output_dir, str) and viethoa_output_dir.strip()
            else os.path.abspath(os.path.splitext(output_path)[0] + "_viet_hoa")
        )

        print("\n[PREPROCESS] Bat dau chay Viet hoa truoc khi xu ly video...")
        viethoa_result = run_viethoa_preprocess(
            source_url=source_url,
            output_dir=resolved_viethoa_dir,
            gemini_api_key=gemini_api_key,
            channel_name=channel_name,
            extra_prompt=extra_prompt,
            progress_callback=lambda msg: print(f"[VIET_HOA] {msg}"),
        )

        if viethoa_result.get("translated_title"):
            video_title = viethoa_result["translated_title"]
        
    print(f"Đọc thông tin video: {video_path}")
    total_dur_sec, fps, width, height = get_video_info(video_path)
    print(f"Thời lượng gốc: {total_dur_sec:.2f}s, Kích thước: {width}x{height}, FPS: {fps}")
    
    # Chuẩn bị thư mục temp
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        subs = list(srt.parse(f.read()))
        
    if not subs:
        print("SRT file is empty!")
        return
        
    subs = preprocess_srt(subs, tts_method=tts_method, vieneu_mode=vieneu_mode)
        
    # --- PHASE 1: GENERATE AUDIO ---
    optimal_audio_workers = get_optimal_threads("audio", max_workers)
    print(f"\n[PHASE 1] Khởi tạo AI Audio với {optimal_audio_workers} luồng (Phương thức: {tts_method})...")
    results = []
    total_subs = len(subs)
    with ThreadPoolExecutor(max_workers=optimal_audio_workers) as executor:
        futures = {executor.submit(process_sub_worker, sub, i+1, total_subs, voice, resource_id, tts_method, piper_model, tts_api_key, volume_db, pitch_semitones, speed_factor, vieneu_mode, vieneu_api_key, vieneu_emotion): i for i, sub in enumerate(subs)}
        for future in as_completed(futures):
            results.append(future.result())
            
    results.sort(key=lambda x: x[0])
    
    # --- PHASE 2: CALCULATE CHUNKS ---
    chunks = []
    current_time = 0.0
    for res in results:
        idx, start_time, target_dur, final_dur, wav_path, sub_obj = res
        
        gap_dur = start_time - current_time
        if gap_dur > 0.0:
            if gap_dur <= 1.0 and len(chunks) > 0 and chunks[-1]["type"] == "sub":
                # Gap nhỏ <= 1 giây, ghép luôn vào đoạn SUB TRƯỚC ĐÓ
                prev_sub = chunks[-1]
                prev_sub["duration"] += gap_dur
                prev_sub["final_duration"] += gap_dur
                try:
                    audio = AudioSegment.from_file(prev_sub["audio_file"], format="wav")
                    audio += AudioSegment.silent(duration=int(gap_dur * 1000))
                    audio.export(prev_sub["audio_file"], format="wav")
                except Exception as e:
                    print(f"Lỗi thêm silence: {e}")
            elif gap_dur <= 1.0 and len(chunks) == 0:
                # Gap nhỏ ở đầu video, ghép vào SUB hiện tại
                start_time -= gap_dur
                target_dur += gap_dur
                final_dur += gap_dur
                try:
                    audio = AudioSegment.from_file(wav_path, format="wav")
                    audio = AudioSegment.silent(duration=int(gap_dur * 1000)) + audio
                    audio.export(wav_path, format="wav")
                except Exception as e:
                    print(f"Lỗi thêm silence vào đầu: {e}")
            else:
                chunks.append({"type": "gap", "start": current_time, "duration": gap_dur})
            
        chunks.append({
            "type": "sub", 
            "start": start_time, 
            "duration": target_dur, 
            "final_duration": final_dur, 
            "audio_file": wav_path, 
            "idx": idx,
            "sub_obj": sub_obj
        })
        # Force current_time to end of sub to prevent floating point drift
        current_time = start_time + target_dur
        
    # --- CHECKPOINT 1: KIỂM TRA VÀ FIX AUDIO ---
    print("\\n[CHECKPOINT 1] Đang kiểm tra và tự động FIX tính toàn vẹn của các file Audio AI...")
    MAX_AUDIO_RETRIES = 3
    for attempt in range(MAX_AUDIO_RETRIES):
        missing_audio = []
        for chunk in chunks:
            if chunk["type"] == "sub":
                w_path = chunk["audio_file"]
                if not os.path.exists(w_path) or os.path.getsize(w_path) <= 44:
                    missing_audio.append(chunk)
                    
        if not missing_audio:
            if attempt > 0:
                print("  -> Đã fix thành công 100% file Audio AI lỗi.")
            else:
                print("  -> Tuyệt vời! 100% file Audio AI đã sẵn sàng và hợp lệ ngay từ đầu.")
            break
            
        print(f"\n[!] Phát hiện {len(missing_audio)} file audio lỗi. Tiến hành RE-GENERATE (Lần {attempt+1}/{MAX_AUDIO_RETRIES})...")
        with ThreadPoolExecutor(max_workers=optimal_audio_workers) as executor:
            futures = {executor.submit(synthesize_block_audio, chunk["sub_obj"], voice, resource_id, tts_method, piper_model, tts_api_key, volume_db, pitch_semitones, speed_factor, vieneu_mode, vieneu_api_key, vieneu_emotion): chunk for chunk in missing_audio}
            for future in as_completed(futures):
                chunk = futures[future]
                try:
                    new_wav, _, new_final_dur_ms = future.result()
                    chunk["audio_file"] = new_wav
                    chunk["final_duration"] = new_final_dur_ms / 1000.0
                except Exception as e:
                    print(f"  -> Lỗi re-generate audio câu {chunk['idx']}: {e}")
                    
    final_missing_audio = [c for c in chunks if c["type"] == "sub" and (not os.path.exists(c["audio_file"]) or os.path.getsize(c["audio_file"]) <= 44)]
    if final_missing_audio:
        print("\\n[!] LỖI CHECKPOINT 1 NGHIÊM TRỌNG: Đã cố gắng FIX nhưng vẫn có audio bị lỗi.")
        return "⚠️ Lỗi: Quá trình tạo giọng nói (TTS) thất bại hoàn toàn. Vui lòng kiểm tra lại kết nối mạng hoặc API Key!"
        
    # --- PHASE 3: RENDER CHUNKS ---
    print(f"\\n[PHASE 2] Bắt đầu Render {len(chunks)} phân đoạn Video (Chế độ Đa Luồng Siêu Tốc)...")
    rendered_files = [None] * len(chunks)
    
    video_norm = f"scale={width}:{height},setsar=1:1,format=yuv420p"
    
    # Chuẩn bị template variables cho render
    tpl_variables = None
    if template and TEMPLATE_ENGINE_AVAILABLE:
        custom_vars = {}
        if viethoa_result:
            translated = viethoa_result.get("translated_title", "")
            custom_vars.update({
                "TEN_VIDEO": translated if translated else video_title,
                "TEN_VIDEO_GOC": viethoa_result.get("original_title", ""),
                "TEN_VIDEO_VIET": translated,
                "TEN_VIDEO_NGAN": viethoa_result.get("short_title", ""),
                "MO_TA_VIET": viethoa_result.get("translated_description", ""),
                "VIDEO_URL": viethoa_result.get("source_url", ""),
                "THUMB_GOC": viethoa_result.get("thumbnail_original_path", ""),
                "THUMB_VIET": viethoa_result.get("thumbnail_viet_path", ""),
            })
        elif video_title:
            custom_vars.update({
                "TEN_VIDEO": video_title,
                "TEN_VIDEO_VIET": video_title
            })
        tpl_variables = build_default_variables(video_path, custom_vars or None)
        print(f"  -> Template: '{template.get('name', 'N/A')}' với {len(template.get('elements', []))} elements")
        if template.get('bgmPath'):
            print(f"  -> BGM: {os.path.basename(template['bgmPath'])} (Vol: {template.get('bgmVolume', 100)}%, Speed: {template.get('bgmSpeed', 1.0)}x)")
    
    def render_worker(i, chunk):
        out_chunk = os.path.join(TEMP_DIR, f"chunk_{i:04d}.mkv")
        res = render_ffmpeg_chunk(chunk, video_path, out_chunk, video_norm, fps, random_flip, template=template, variables=tpl_variables, total_video_duration=total_dur_sec)
        # Xóa file audio để tiết kiệm dung lượng ổ đĩa ngay khi render xong
        try:
            if chunk.get("type") == "sub" and chunk.get("audio_file") and os.path.exists(chunk["audio_file"]):
                os.remove(chunk["audio_file"])
        except Exception:
            pass
        return i, out_chunk, res
        
    encoder, _ = get_best_encoder()
    gpu_enabled = ("nvenc" in encoder or "qsv" in encoder or "amf" in encoder)
    base_render_threads = max_workers if max_workers > 0 else 4
    render_threads = get_optimal_threads("video", base_render_threads, gpu_enabled=gpu_enabled)
    
    if gpu_enabled:
        print(f"  -> Kích hoạt {render_threads} luồng FFmpeg xử lý song song bằng GPU (Hardware Acceleration)!")
    else:
        print(f"  -> Kích hoạt {render_threads} luồng FFmpeg xử lý song song bằng CPU (Superfast Mode)!")
    
    with ThreadPoolExecutor(max_workers=render_threads) as executor:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(executor.submit(render_worker, i, chunk))
            
        for future in as_completed(futures):
            i, out_chunk, res = future.result()
            if res.returncode != 0:
                print(f"Lỗi Render Đoạn {i+1}: {res.stderr.decode('utf-8')}")
            else:
                print(f"  -> Hoàn thành render phân đoạn {i+1}/{len(chunks)}")
            rendered_files[i] = out_chunk
        
    # --- CHECKPOINT 2: KIỂM TRA & FIX TÀI NGUYÊN VIDEO ---
    print("\\n[CHECKPOINT 2] Đang kiểm tra và tự động FIX tính toàn vẹn của các phân đoạn video trước khi ghép nối...")
    MAX_VIDEO_RETRIES = 3
    for attempt in range(MAX_VIDEO_RETRIES):
        missing_video_indices = []
        for i, rf in enumerate(rendered_files):
            if not os.path.exists(rf) or os.path.getsize(rf) < 1024:
                missing_video_indices.append(i)
                
        if not missing_video_indices:
            if attempt > 0:
                print("  -> Đã fix thành công 100% phân đoạn Video lỗi.")
            else:
                print("  -> Tuyệt vời! 100% tài nguyên đã sẵn sàng và hoàn hảo ngay từ đầu.")
            break
            
        print(f"\\n[!] Phát hiện {len(missing_video_indices)} phân đoạn video lỗi. Tiến hành RENDER LẠI (Lần {attempt+1}/{MAX_VIDEO_RETRIES})...")
        for i in missing_video_indices:
            chunk = chunks[i]
            out_chunk = rendered_files[i]
            print(f"  -> Đang render LẠI đoạn {chunk['type'].upper()} {i+1}/{len(chunks)}...")
            res = render_ffmpeg_chunk(chunk, video_path, out_chunk, video_norm, fps, random_flip, total_video_duration=total_dur_sec)
            if res.returncode != 0:
                print(f"  -> Lỗi Render LẠI: {res.stderr.decode('utf-8')}")

    final_missing_video = [rf for rf in rendered_files if not os.path.exists(rf) or os.path.getsize(rf) < 1024]
    if final_missing_video:
        print("\\n[!] LỖI CHECKPOINT 2 NGHIÊM TRỌNG: Đã cố gắng RENDER LẠI nhưng vẫn có video bị lỗi.")
        return "⚠️ Lỗi: Quá trình xuất video thất bại (Checkpoint 2). Vui lòng thử lại!"
        
    # --- PHASE 4: CONCAT ---
    print("\\n[PHASE 3] Đang nối các mảnh video (Concat)...")
    concat_txt = os.path.join(TEMP_DIR, "concat_list.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for rf in rendered_files:
            # Dùng đường dẫn tuyệt đối cho an toàn trong concat
            abs_path = os.path.abspath(rf).replace('\\', '/')
            f.write(f"file '{abs_path}'\n")
            
    if skip_concat:
        print("\\n[PHASE 3] C# requested skip_concat, but we MUST concat to _dubbed.mp4 for Phase 4 to work.")
        skip_concat = False
        if output_path.endswith(".txt"):
            base_dir = os.path.dirname(video_path)
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(base_dir, f"{base_name}_dubbed.mp4")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, 
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", 
        "-af", "aresample=async=1",
        output_path
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        print(f"\n[!] LỖI GHI FILE GHÉP NỐI: {res.stderr.decode('utf-8')}")
    
    # --- PHASE 4.5: BGM MIXING (nếu template có BGM) ---
    if template and TEMPLATE_ENGINE_AVAILABLE and template.get('bgmPath'):
        bgm_path = template['bgmPath']
        bgm_volume = template.get('bgmVolume', 15.0)
        bgm_speed = template.get('bgmSpeed', 1.0)
        
        if os.path.exists(bgm_path):
            print(f"\n[PHASE 3.5] Đang mix nhạc nền (BGM) vào video...")
            print(f"  -> File: {os.path.basename(bgm_path)}, Volume: {bgm_volume}%, Speed: {bgm_speed}x")
            
            bgm_cmd = build_bgm_mix_cmd(
                input_video=output_path,
                bgm_path=bgm_path,
                output_path=output_path + ".bgm_tmp.mp4",
                bgm_volume=bgm_volume,
                bgm_speed=bgm_speed
            )
            
            if bgm_cmd:
                bgm_res = subprocess.run(bgm_cmd, capture_output=True)
                if bgm_res.returncode == 0:
                    # Thay thế file gốc bằng file có BGM
                    try:
                        os.remove(output_path)
                        os.rename(output_path + ".bgm_tmp.mp4", output_path)
                        print("  -> Đã mix BGM thành công!")
                    except Exception as e:
                        print(f"  -> Lỗi rename file BGM: {e}")
                else:
                    print(f"  -> Lỗi mix BGM: {bgm_res.stderr.decode('utf-8', errors='ignore')[:200]}")
                    # Xóa file tạm nếu lỗi
                    try:
                        os.remove(output_path + ".bgm_tmp.mp4")
                    except Exception:
                        pass
        else:
            print(f"\n[WARN] File BGM không tồn tại: {bgm_path}")
    
    # --- CLEANUP ---
    print("\n[PHASE 4] Dọn dẹp file tạm...")
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    
    print(f"\n=> HOÀN TẤT! Video thành phẩm đã được lưu tại: {output_path}")
    if viethoa_result:
        print(f"=> Bo ket qua Viet hoa da duoc luu tai: {viethoa_result['output_dir']}")
    return {
        "output_path": os.path.abspath(output_path),
        "viethoa": viethoa_result,
        "video_title": video_title,
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auto AI Dubbing & Video Renderer")
    parser.add_argument("--srt", default="speech.srt", help="File phụ đề SRT")
    parser.add_argument("--video", required=True, help="File video gốc (VD: input.mp4)")
    parser.add_argument("--out", default="output.mp4", help="Video xuất ra (VD: output.mp4)")
    parser.add_argument("--threads", default=10, type=int, help="Số luồng tạo audio AI")
    parser.add_argument("--voice", default="BV074_streaming", help="Mã giọng đọc (Voice ID)")
    parser.add_argument("--resource_id", default="7102355709945188865", help="Mã tài nguyên (Resource ID)")
    parser.add_argument("--tts_method", default="CapCut API", help="Phương thức TTS: 'CapCut API' hoặc 'Piper Offline'")
    parser.add_argument("--piper_model", default="vi_VN-vivos-mac_tts.onnx", help="Đường dẫn đến file model Piper")
    parser.add_argument("--source_url", default="", help="URL video nguon de chay Viet hoa truoc render")
    parser.add_argument("--gemini_api_key", default="", help="Gemini API key. Bo trong de auto doc tu apiKeys.json")
    parser.add_argument("--channel_name", default="", help="Ten kenh de chen vao tieu de Viet hoa")
    parser.add_argument("--extra_prompt", default="", help="Prompt phu de tao thumbnail Viet hoa")
    parser.add_argument("--viethoa_output_dir", default="", help="Thu muc luu ket qua Viet hoa truoc render")
    args = parser.parse_args()
    
    # Auto-load template from ui_profiles.json
    selected_template = None
    try:
        if TEMPLATE_ENGINE_AVAILABLE:
            profile_path = os.fspath(PATHS.ui_profiles_file())
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                
                last_profile_id = profiles.get("LastSelectedProfile", "Default")
                profile_data = profiles.get("Profiles", {}).get(last_profile_id, {})
                cboTemplate = int(profile_data.get("cboTemplate", 0))
                
                if cboTemplate > 0:
                    template_path = os.fspath(PATHS.template_file())
                    if os.path.exists(template_path):
                        templates = load_template(template_path)
                        selected_template = get_template_by_index(templates, cboTemplate)
                        if selected_template:
                            print(f"[TEMPLATE] Đã nạp tự động template: {selected_template.get('name')} (Index: {cboTemplate})")
    except Exception as e:
        print(f"[WARN] Lỗi tự động nạp template: {e}")

    # Lấy tên video gốc để dùng cho biến [[TEN_VIDEO]]
    video_title = os.path.splitext(os.path.basename(args.video))[0]
    
    process_srt_to_video(
        args.srt, args.video, args.out, 
        max_workers=args.threads, voice=args.voice, 
        resource_id=args.resource_id, tts_method=args.tts_method, 
        piper_model=args.piper_model,
        template=selected_template,
        video_title=video_title,
        source_url=args.source_url,
        gemini_api_key=args.gemini_api_key,
        channel_name=args.channel_name,
        extra_prompt=args.extra_prompt,
        viethoa_output_dir=args.viethoa_output_dir,
    )
