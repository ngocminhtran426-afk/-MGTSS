# 🎬 VideoLingo - Video Processing & Dubbing

Dự án này là phiên bản đóng gói các công cụ xử lý video, nhận diện phụ đề (OCR), dịch thuật (Translation) và lồng tiếng AI (Dubbing) thành một luồng (pipeline) liền mạch.

## 🚀 Trải nghiệm ngay trên Google Colab

Bạn có thể chạy trực tiếp dự án này trên trình duyệt thông qua Google Colab mà không cần cài đặt bất cứ thứ gì lên máy tính của mình. Colab sẽ cung cấp GPU miễn phí (T4) để việc nhận diện và xử lý AI diễn ra cực nhanh!

Hãy click vào nút dưới đây để bắt đầu:

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ngocminhtran426-afk/-MGTSS/blob/main/Run_on_Colab.ipynb)

---

## 💻 Cài đặt Cục bộ (Local)

Nếu bạn muốn chạy trên máy tính cá nhân (yêu cầu có card đồ họa NVIDIA để tối ưu tốc độ):

1. **Cài đặt Python 3.9+**
2. **Cài đặt các thư viện cần thiết:**
   ```bash
   python install.py
   ```
3. **Chạy giao diện Web:**
   Nhấp đúp vào file `OneKeyStart.bat` hoặc chạy lệnh:
   ```bash
   streamlit run st.py
   ```

## 📂 Cấu trúc thư mục

* `core/`: Chứa các module cốt lõi (OCR, Translator, Capcut Dubbing...)
* `models/`: Chứa các mô hình AI phục vụ nhận diện và giọng đọc.
* `storage/`: Nơi lưu trữ video tải xuống, dữ liệu tạm, và video hoàn thiện.
* `Run_on_Colab.ipynb`: Notebook dành riêng cho môi trường Google Colab.
