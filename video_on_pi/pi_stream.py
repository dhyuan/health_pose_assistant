import socket, struct, cv2, time
from picamera2 import Picamera2

MAC_IP = "dahuiMac.local"
PORT = 9999

picam2 = Picamera2()
picam2.configure(
    picam2.create_video_configuration(
        main={"size": (640, 480)},  # 明确指定分辨率
    )
)
picam2.start()


def connect_with_retry(ip, port, retry_interval=3):
    """断线自动重连"""
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, port))
            print(f"[INFO] 已连接 {ip}:{port}")
            return s
        except Exception as e:
            print(f"[WARN] 连接失败: {e}，{retry_interval}秒后重试...")
            time.sleep(retry_interval)


sock = connect_with_retry(MAC_IP, PORT)

try:
    while True:
        frame = picam2.capture_array()
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        data = buf.tobytes()  # ← 去掉 pickle
        try:
            sock.sendall(struct.pack("Q", len(data)) + data)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[WARN] 连接异常: {type(e).__name__}，重连中...")
            try:
                sock.close()
            except:
                pass
            sock = connect_with_retry(MAC_IP, PORT)
except KeyboardInterrupt:
    pass
finally:
    picam2.stop()
    try:
        sock.close()
    except:
        pass
