import socket, struct, cv2, time, numpy as np
from picamera2 import Picamera2
from libcamera import controls

MAC_IP = "dahuiMac.local"
PORT = 9999

picam2 = Picamera2()
picam2.configure(
    picam2.create_video_configuration(
        main={"size": (640, 480)},  # 明确指定分辨率
    )
)
picam2.start()

# ── 对焦配置 ──────────────────────────────────────────
# 设置连续自动对焦 + 对焦到中距离
try:
    # 启用自动对焦（使用 libcamera controls 对象）
    picam2.set_controls(
        {
            controls.AfMode: controls.AfModeEnum.Continuous,  # 连续自动对焦
            controls.LensPosition: 0.5,  # 对焦到中距离（0.0=无穷远, 1.0=最近）
        }
    )
    print("[INFO] 已启用连续自动对焦（对焦距离: 0.5）")
except Exception as e:
    print(f"[WARN] 对焦设置失败: {e}")
    try:
        # 如果连续对焦失败，尝试手动固定对焦
        picam2.set_controls({controls.LensPosition: 0.5})
        print("[INFO] 已设置固定对焦距离: 0.5")
    except Exception as e2:
        print(f"[WARN] 固定对焦也失败: {e2}，继续使用默认对焦")


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
