import cv2
import sys

def get_frame(video_path, output_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error opening video {video_path}")
        sys.exit(1)
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Lấy frame ở 10% thời lượng video (thường có phụ đề)
    target_frame = int(total_frames * 0.1)
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ret, frame = cap.read()
    
    if not ret:
        # Lùi lại frame 0 nếu không lấy được
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
        
    if ret:
        cv2.imwrite(output_path, frame)
        print("SUCCESS")
    else:
        print("FAILED")
        
    cap.release()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python get_frame.py <video_path> <output_path>")
    else:
        get_frame(sys.argv[1], sys.argv[2])
