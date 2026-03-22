import socket
import struct
import cv2
import numpy as np

HOST = ""  # 监听所有网卡
PORT = 9999

# ===== 创建 TCP 服务端 =====
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print("Waiting for Pi connection...")
conn, addr = server_socket.accept()
print("Connected by", addr)

# ===== 初始化 =====
data = b""
payload_size = struct.calcsize("Q")

try:
    while True:
        # ===== 1. 接收帧长度 =====
        while len(data) < payload_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Client disconnected")
            data += packet

        packed_msg_size = data[:payload_size]
        data = data[payload_size:]
        msg_size = struct.unpack("Q", packed_msg_size)[0]

        # ===== 2. 接收完整帧数据 =====
        while len(data) < msg_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Client disconnected")
            data += packet

        frame_data = data[:msg_size]
        data = data[msg_size:]

        # ===== 3. 解码 JPEG =====
        np_data = np.frombuffer(frame_data, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

        if frame is None:
            continue  # 防止偶尔解码失败

        # ===== 4. 显示视频 =====
        cv2.imshow("Pi Camera Stream", frame)

        # 按 q 退出
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except Exception as e:
    print("[ERROR]", e)

finally:
    conn.close()
    server_socket.close()
    cv2.destroyAllWindows()
