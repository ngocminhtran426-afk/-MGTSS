import gradio as gr
from capcut_dubber import process_srt_to_video
import os
import json

VOICE_LIST = {
    "Cô Gái Hoạt Ngôn": {"voice_id": "BV074_streaming", "resource_id": "7102355709945188865"},
    "Thanh Niên Tự Tin": {"voice_id": "BV075_streaming", "resource_id": "7102355803792740865"},
    "Nhỏ Ngọt Ngào": {"voice_id": "BV421_vivn_streaming", "resource_id": "7252594014782755330"},
    "Giọng Nữ Phổ Thông": {"voice_id": "vi_female_huong", "resource_id": "7264854897953083905"},
    "Giọng Bé": {"voice_id": "BV074_streaming_dsp", "resource_id": "7550087831092251920"},
    "Hoai My": {"voice_id": "vi-VN-HoaiMyNeural", "resource_id": "7371666434650280464"},
    "Nam Minh": {"voice_id": "vi-VN-NamMinhNeural", "resource_id": "7371666524727153168"},
    "Việt Méo": {"voice_id": "BV075_streaming_vibrato_dsp", "resource_id": "7569450639810465040"},
    "Mai": {"voice_id": "BV562_streaming", "resource_id": "7483736254694035984"},
    "Ban Mai": {"voice_id": "multi_female_yangguangnv_uranus_bigtts", "resource_id": "7637456432522218773"},
    "Review Phim (Mới)": {"voice_id": "multi_female_richgirl_uranus_bigtts", "resource_id": "7637460351541447956"},
    "Bản Tin 1": {"voice_id": "multi_female_quanweinv_uranus_bigtts", "resource_id": "7637458743197732117"},
    "Review Phim 4": {"voice_id": "multi_female_stokie_uranus_bigtts", "resource_id": "7637456729696996628"},
    "Bản Tin (Nữ)": {"voice_id": "multi_female_sisi_uranus_bigtts", "resource_id": "7637455857285860629"},
    "Review Phim 3": {"voice_id": "multi_female_daqi_uranus_bigtts", "resource_id": "7637451983389019409"},
    "Review Phim 2": {"voice_id": "multi_female_xyf04auto_uranus_bigtts", "resource_id": "7637458743197732117"},
    "Sunny Idol": {"voice_id": "multi_female_kiwi_uranus_bigtts", "resource_id": "7637457995882089749"},
    "Kenny Đại Đế": {"voice_id": "BV075_streaming_demon_dsp", "resource_id": "7569442422665661712"},
    "Robot VN": {"voice_id": "BV075_streaming_robot_dsp", "resource_id": "7538698409633516816"},
    "Giọng Nam Trầm": {"voice_id": "multi_male_felipe_uranus_bigtts", "resource_id": "7637456729696996628"},
    "Giọng Gái Mới Lớn": {"voice_id": "multi_female_peiqi_uranus_bigtts", "resource_id": "7637458789033151751"},
    "Nam Bản Tin": {"voice_id": "multi_female_xinwenjieshuo_uranus_bigtts", "resource_id": "7637455039719640327"},
    "Giọng Test": {"voice_id": "multi_female_tianmeijieshuo_uranus_bigtts", "resource_id": "7637460417295469832"},
    "Alex Đại Đế": {"voice_id": "BV560_streaming", "resource_id": "7483736167565758992"},
}

def render_video(video_path, srt_path, output_name, threads, tts_method, piper_model, voice, resource_id, volume_db, pitch_semitones, speed_factor, enable_viethoa, source_url, gemini_api_key, channel_name, extra_prompt):
    if not video_path or not srt_path:
        return "⚠️ Lỗi: Vui lòng cung cấp đủ đường dẫn Video và SRT!"

    if enable_viethoa and not source_url:
        return "⚠️ Lỗi: Bạn đã bật Việt hoá trước render nhưng chưa nhập URL video nguồn."
        
    out_path = output_name.strip() if output_name else "output.mp4"
    if not out_path.endswith('.mp4'):
        out_path += ".mp4"
        
    try:
        # Gọi hàm chính từ capcut_dubber
        result = process_srt_to_video(
            srt_path.strip(),
            video_path.strip(),
            out_path,
            max_workers=int(threads),
            voice=voice.strip(),
            resource_id=resource_id.strip(),
            tts_method=tts_method.strip(),
            piper_model=piper_model.strip(),
            volume_db=float(volume_db),
            pitch_semitones=float(pitch_semitones),
            speed_factor=float(speed_factor),
            source_url=source_url.strip() if enable_viethoa else "",
            gemini_api_key=gemini_api_key.strip(),
            channel_name=channel_name.strip(),
            extra_prompt=extra_prompt.strip(),
        )
        if not result:
            return "⚠️ Pipeline đã dừng do có lỗi trong quá trình xử lý. Hãy xem log terminal để biết chi tiết."

        message = [
            "✅ HOÀN TẤT XUẤT SẮC!",
            "Video thành phẩm đã được lưu tại:",
            result.get("output_path", os.path.abspath(out_path)),
        ]
        if result.get("viethoa"):
            message.extend([
                "",
                "📦 Bộ kết quả Việt hoá đã được lưu tại:",
                result["viethoa"].get("output_dir", ""),
            ])
        return "\n".join(message)
    except Exception as e:
        return f"❌ LỖI NGHIÊM TRỌNG:\n{e}"

with gr.Blocks(title="CapCut Auto Dubber Pro") as demo:
    gr.Markdown("# 🎬 CapCut Auto Dubber Pro")
    gr.Markdown("Biến file phụ đề SRT thành video lồng tiếng chân thực với giọng AI siêu thực của CapCut.")
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### ⚙️ Cấu Hình Đầu Vào")
            vid_input = gr.Textbox(label="Tên file hoặc Đường dẫn Video Gốc", value="input.mp4", placeholder="Ví dụ: input.mp4")
            srt_input = gr.Textbox(label="Tên file hoặc Đường dẫn Phụ Đề", value="speech.srt", placeholder="Ví dụ: speech.srt")
            
            with gr.Row():
                out_name = gr.Textbox(label="Tên Video Xuất Ra", value="output.mp4")
                threads = gr.Number(label="Số Luồng Tải AI (Threads)", value=10, minimum=1, maximum=50)
                
            with gr.Row():
                tts_method = gr.Radio(choices=["CapCut API", "Piper Offline"], value="CapCut API", label="Phương thức TTS")

            with gr.Row():
                volume_db = gr.Number(label="Tăng/giảm âm lượng (dB)", value=0.0)
                pitch_semitones = gr.Number(label="Tăng/giảm cao độ (nửa cung)", value=0.0)
                speed_factor = gr.Number(label="Tăng/giảm Tốc độ (1.0 là gốc)", value=1.0)

            with gr.Row():
                piper_model = gr.Textbox(label="Đường dẫn Model Piper (.onnx) (Dành cho Piper Offline)", value="vi_VN-vivos-mac_tts.onnx", visible=False)

            with gr.Row():
                voice_dropdown = gr.Dropdown(choices=list(VOICE_LIST.keys()) + ["Tùy chỉnh (Nhập tay mã)"], value="Cô Gái Hoạt Ngôn", label="Chọn Giọng Đọc AI (Tiếng Việt)")
                
            with gr.Row():
                voice = gr.Textbox(label="Mã Giọng Đọc (Voice ID)", value="BV074_streaming")
                resource_id = gr.Textbox(label="Mã Tài Nguyên (Resource ID)", value="7102355709945188865")
                
            def update_voice_inputs(choice):
                if choice == "Tùy chỉnh (Nhập tay mã)":
                    return gr.update(), gr.update()
                else:
                    v = VOICE_LIST.get(choice)
                    return gr.update(value=v["voice_id"]), gr.update(value=v["resource_id"])

            voice_dropdown.change(fn=update_voice_inputs, inputs=voice_dropdown, outputs=[voice, resource_id])

            def toggle_tts_method(method):
                if method == "Piper Offline":
                    return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
                else:
                    return gr.update(visible=False), gr.update(visible=True), gr.update(visible=True), gr.update(visible=True)

            tts_method.change(fn=toggle_tts_method, inputs=tts_method, outputs=[piper_model, voice_dropdown, voice, resource_id])

            with gr.Accordion("🇻🇳 Việt hoá trước khi render (Tùy chọn)", open=False):
                enable_viethoa = gr.Checkbox(label="Chạy bước Việt hoá trước pipeline render", value=False)
                source_url = gr.Textbox(
                    label="URL video nguồn",
                    placeholder="Dán link YouTube, Douyin, TikTok, Facebook... để lấy metadata + thumbnail trước khi render",
                )
                gemini_api_key = gr.Textbox(
                    label="Gemini API Key (Tùy chọn)",
                    type="password",
                    placeholder="Để trống nếu muốn tự đọc từ apiKeys.json",
                )
                channel_name = gr.Textbox(
                    label="Tên kênh (Tùy chọn)",
                    placeholder="Ví dụ: Việt Ca",
                )
                extra_prompt = gr.Textbox(
                    label="Prompt phụ cho thumbnail (Tùy chọn)",
                    lines=3,
                    placeholder="Ví dụ: đổi chữ logo góc trái thành MIN REVIEW PHIM",
                )
                
            run_btn = gr.Button("▶ BẮT ĐẦU RENDER", variant="primary")
            
        with gr.Column():
            gr.Markdown("### 📝 Kết Quả Trạng Thái")
            output_msg = gr.Textbox(label="Log", lines=10)
            gr.Markdown("*Mẹo: Bạn có thể xem tiến độ Render chi tiết chạy % ở cửa sổ đen (Terminal) bên dưới.*")
            
    run_btn.click(
        fn=render_video,
        inputs=[vid_input, srt_input, out_name, threads, tts_method, piper_model, voice, resource_id, volume_db, pitch_semitones, speed_factor, enable_viethoa, source_url, gemini_api_key, channel_name, extra_prompt],
        outputs=[output_msg]
    )

if __name__ == "__main__":
    print("Khởi động Giao diện Web siêu tốc...")
    demo.launch(inbrowser=True, theme=gr.themes.Soft())
