import socket
import struct
import cv2
import numpy as np
import tensorflow as tf

# ===== MoveNet 加载 =====
interpreter = tf.lite.Interpreter(model_path="movenet_lightning.tflite")
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()


def run_movenet(frame):
    img = cv2.resize(frame, (192, 192))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = np.expand_dims(img, axis=0).astype(np.uint8)

    print(input_details)

    interpreter.set_tensor(input_details[0]["index"], img)
    interpreter.invoke()

    keypoints = interpreter.get_tensor(output_details[0]["index"])
    return keypoints


# ===== 画关键点 =====
def draw_keypoints(frame, keypoints, threshold=0.3):
    h, w, _ = frame.shape
    for kp in keypoints[0][0]:
        y, x, score = kp
        if score > threshold:
            cx, cy = int(x * w), int(y * h)
            cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)


# ===== TCP 接收 =====
HOST = ""
PORT = 9999

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print("Waiting for Pi connection...")
conn, addr = server_socket.accept()
print("Connected by", addr)

data = b""
payload_size = struct.calcsize("Q")

try:
    while True:
        # 收长度
        while len(data) < payload_size:
            packet = conn.recv(4096)
            if not packet:
                raise ConnectionError("Client disconnected")
            data += packet

        packed_msg_size = data[:payload_size]
        data = data[payload_size:]
        msg_size = struct.unpack("Q", packed_msg_size)[0]

        # 收数据
        while len(data) < msg_size:
            data += conn.recv(4096)

        frame_data = data[:msg_size]
        data = data[msg_size:]

        # 解码
        np_data = np.frombuffer(frame_data, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

        if frame is None:
            continue

        # ===== 关键点检测 =====
        keypoints = run_movenet(frame)

        # ===== 画关键点 =====
        draw_keypoints(frame, keypoints)

        cv2.imshow("Pose Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except Exception as e:
    print("[ERROR]", e)

finally:
    conn.close()
    server_socket.close()
    cv2.destroyAllWindows()
