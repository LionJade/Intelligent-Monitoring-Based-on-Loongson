import cv2
import socket
import time
import struct
import threading
import pyaudio
import sys
import os
import numpy as np

# ------------------------------------------------------------------------
# 快递箱计数器：每秒统计移动目标（快递箱）数量
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
# 快递箱计数器：每帧画框、每秒统计数量
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
# 快递箱计数器：每帧画框、每秒统计数量（增强版）
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
# 斜视三面箱计数器：检测六边形轮廓，每秒统计、并画多边形
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
# 斜视三面箱计数器（阈值放宽版）
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
# BoxCounter：适应低速移动箱子
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
# 斜视三面箱计数器（检测多边形边数 5–8）
# ------------------------------------------------------------------------
class BoxCounter:
    def __init__(self,
                 history=500,
                 varThreshold=30,
                 min_area=2000,
                 eps_coef=0.025):
        self.bgsub = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=varThreshold,
            detectShadows=False)
        self.min_area = min_area
        self.eps_coef = eps_coef
        self.start_time = time.time()
        self.max_count = 0
        self.kern = cv2.getStructuringElement(cv2.MORPH_RECT, (7,7))

    def process(self, frame):
        # 前景分割 + 二值化
        fg = self.bgsub.apply(frame)
        _, th = cv2.threshold(fg, 180, 255, cv2.THRESH_BINARY)
        clean = cv2.morphologyEx(th, cv2.MORPH_OPEN, self.kern, iterations=2)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, self.kern, iterations=2)

        # 查轮廓（兼容 OpenCV3/4）
        cnts = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = cnts[1] if len(cnts) == 3 else cnts[0]

        valid = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, self.eps_coef * peri, True)

            # 边数限制 5–8，且凸包
            if 5 <= len(approx) <= 8 and cv2.isContourConvex(approx):
                valid.append(approx)

        # 在帧上画多边形
        for poly in valid:
            cv2.polylines(frame, [poly], True, (255, 0, 0), 2)

        # 每秒统计最大数量并返回
        c = len(valid)
        self.max_count = max(self.max_count, c)
        now = time.time()
        if now - self.start_time >= 1.0:
            res = self.max_count
            self.start_time = now
            self.max_count = 0
            return res
        return None

# 更新全局实例
package_counter = BoxCounter()





# ==============================================================================
# 全局配置
# ==============================================================================

# PC 客户端 IP
SERVER_IP = "192.168.137.1"

# 主监控流端口
PORT = 8888

# 模板上传 / 删除端口
TEMPLATE_PORT = 9999
DELETE_PORT = 9998

# 视频配置
VIDEO_DEVICES = ["/dev/video0", "/dev/video2"]
CURRENT_VIDEO_DEVICE = VIDEO_DEVICES[0]
TARGET_WIDTH = 640
TARGET_HEIGHT = 480
FPS = 10

# 音频配置
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024

# 人脸识别配置
TEMPLATE_DIR = "templates"
MATCH_THRESH = 10

os.makedirs(TEMPLATE_DIR, exist_ok=True)

# 全局标志和锁
running_flag = threading.Event()
running_flag.set()
device_lock = threading.Lock()
cap = None

# ORB & BFMatcher
face_cascade = None
orb = cv2.ORB_create()
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
templates = {}

# -----------------------------------------------------------------------------
def load_face_cascade():
    global face_cascade
    cascade_paths = [
        '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml',
        '/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml',
        'haarcascade_frontalface_default.xml'
    ]
    for p in cascade_paths:
        if os.path.exists(p):
            face_cascade = cv2.CascadeClassifier(p)
            if not face_cascade.empty():
                print(f"[INFO] 使用分类器: {p}")
                return
    raise RuntimeError("未找到 haarcascade_frontalface_default.xml")

def load_existing_templates():
    global templates
    for file in os.listdir(TEMPLATE_DIR):
        if file.lower().endswith(".jpg"):
            name = os.path.splitext(file)[0]
            img = cv2.imread(os.path.join(TEMPLATE_DIR, file), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            kp, des = orb.detectAndCompute(img, None)
            if des is not None:
                templates[name] = (kp, des)
                print(f"[INFO] 载入模板 {name}，特征点 {len(kp)}")

def recognize(face_img):
    if face_img is None or face_img.size == 0:
        return "Unknown"
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    kp, des = orb.detectAndCompute(gray, None)
    if des is None:
        return "Unknown"
    best_name, best_score = "Unknown", 0
    for name, (t_kp, t_des) in templates.items():
        if t_des is None or len(t_des) == 0:
            continue
        try:
            matches = bf.match(t_des, des)
            good = [m for m in matches if m.distance < 60]
            if len(good) > best_score:
                best_score = len(good)
                best_name = name
        except cv2.error as e:
            print(f"[ERROR] ORB 匹配错误: {e}")
            continue
    return best_name if best_score >= MATCH_THRESH else "Unknown"

def switch_video_device(new_device):
    global CURRENT_VIDEO_DEVICE, cap
    with device_lock:
        if new_device not in VIDEO_DEVICES:
            print(f"[设备端] 错误: 无效的设备路径: {new_device}")
            return False
        if new_device == CURRENT_VIDEO_DEVICE:
            print(f"[设备端] 设备已是 {new_device}")
            return True
        if cap is not None and cap.isOpened():
            cap.release()
        CURRENT_VIDEO_DEVICE = new_device
        print(f"[设备端] 切换摄像头到: {CURRENT_VIDEO_DEVICE}")
        return True

def video_stream(conn):
    global cap
    frame_cnt, interval = 0, 5
    cached_faces = []
    max_retries, retry_count = 3, 0

    while running_flag.is_set() and retry_count < max_retries:
        with device_lock:
            cap = cv2.VideoCapture(CURRENT_VIDEO_DEVICE)
            if not cap.isOpened():
                retry_count += 1
                print(f"[设备端] 打开摄像头失败 {retry_count}/{max_retries}")
                time.sleep(2)
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_HEIGHT)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            retry_count = 0
            print(f"[设备端] 摄像头初始化: {CURRENT_VIDEO_DEVICE}")
        while running_flag.is_set():
            ret, frame = cap.read()
            if not ret:
                print("[设备端] 读取帧失败，重试摄像头初始化")
                break

            if frame_cnt % interval == 0:
                g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(g, 1.1, 3, minSize=(40, 40))
                cached_faces = faces
            else:
                faces = cached_faces

            for (x, y, w, h) in faces:
                roi = frame[y:y+h, x:x+w]
                label = recognize(roi)
                color = (0, 255, 0) if label != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame, label, (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # ------ 新增：快递箱每秒检测计数 ------
            count = package_counter.process(frame)
            if count is not None:
                print(f"[设备端] 每秒通过快递箱数量: {count}")
                cv2.putText(frame,
                            f"{count} pkg/s",
                            (10, TARGET_HEIGHT - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255), 2)
            # ────────────────────────────────────────

            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                print("[设备端] 警告: 视频编码失败")
                continue
            try:
                data = encoded.tobytes()
                conn.sendall(b"VIDEO")
                conn.sendall(len(data).to_bytes(4, 'big') + data)
                time.sleep(1 / FPS)
            except BrokenPipeError:
                print("[设备端] 视频流断开")
                running_flag.clear()
                break
            except Exception as e:
                print(f"[设备端] 视频发送异常: {e}")
                running_flag.clear()
                break
            frame_cnt += 1

        with device_lock:
            if cap is not None and cap.isOpened():
                cap.release()

    if retry_count >= max_retries:
        print(f"[设备端] 达到最大重试次数，退出")
        running_flag.clear()
    print("[设备端] 视频线程停止")

def audio_stream(conn):
    pa, stream = None, None
    for i in range(3):
        try:
            pa = pyaudio.PyAudio()
            device_idx = -1
            for idx in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(idx)
                if info['maxInputChannels'] > 0 and "USB Camera: Audio" in info['name']:
                    device_idx = idx
                    break
            if device_idx < 0:
                print("[设备端] 未找到音频设备，跳过")
                return
            stream = pa.open(format=AUDIO_FORMAT,
                             channels=CHANNELS,
                             rate=RATE,
                             input=True,
                             frames_per_buffer=CHUNK,
                             input_device_index=device_idx)
            print(f"[设备端] 音频初始化成功 idx={device_idx}")
            break
        except Exception as e:
            print(f"[设备端] 音频初始化错误: {e}")
            time.sleep(2)

    while running_flag.is_set() and stream:
        try:
            audio_data = stream.read(CHUNK, exception_on_overflow=False)
            conn.sendall(b"AUDIO")
            conn.sendall(len(audio_data).to_bytes(4, 'big') + audio_data)
        except BrokenPipeError:
            print("[设备端] 音频流断开")
            running_flag.clear()
            break
        except Exception as e:
            print(f"[设备端] 音频发送异常: {e}")
            running_flag.clear()
            break

    if stream:
        stream.stop_stream()
        stream.close()
    if pa:
        pa.terminate()
    print("[设备端] 音频线程停止")

def command_listener(conn):
    while running_flag.is_set():
        try:
            cmd = conn.recv(1024).decode().strip()
            if not cmd:
                running_flag.clear()
                break
            if cmd in VIDEO_DEVICES:
                switch_video_device(cmd)
            else:
                print(f"[设备端] 未知命令: {cmd}")
        except Exception as e:
            print(f"[设备端] 命令监听异常: {e}")
            running_flag.clear()
            break
    print("[设备端] 命令线程停止")

def receive_template():
    global templates
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", TEMPLATE_PORT))
    srv.listen(1)
    print(f"[INFO] 等待上传模板 port={TEMPLATE_PORT}")
    while running_flag.is_set():
        conn, _ = srv.accept()
        with conn:
            try:
                total_len = int.from_bytes(conn.recv(4), 'big')
                buf = b''
                while len(buf) < total_len:
                    part = conn.recv(total_len - len(buf))
                    if not part: break
                    buf += part
                name_len = int.from_bytes(buf[:2], 'big')
                name = buf[2:2+name_len].decode()
                img = buf[2+name_len:]
                path = os.path.join(TEMPLATE_DIR, f"{name}.jpg")
                with open(path, 'wb') as f:
                    f.write(img)
                print(f"[INFO] 收到模板 {name}")
                gray = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_GRAYSCALE)
                kp, des = orb.detectAndCompute(gray, None)
                if des is not None:
                    templates[name] = (kp, des)
            except Exception as e:
                print(f"[ERROR] 模板接收异常: {e}")
    srv.close()
    print("[INFO] 模板线程停止")

def receive_delete_request():
    global templates
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", DELETE_PORT))
    srv.listen(1)
    print(f"[INFO] 等待删除请求 port={DELETE_PORT}")
    while running_flag.is_set():
        conn, _ = srv.accept()
        with conn:
            try:
                name_len = int.from_bytes(conn.recv(2), 'big')
                name = conn.recv(name_len).decode()
                path = os.path.join(TEMPLATE_DIR, f"{name}.jpg")
                if os.path.exists(path):
                    os.remove(path)
                    templates.pop(name, None)
                    print(f"[INFO] 删除模板 {name}")
            except Exception as e:
                print(f"[ERROR] 删除请求异常: {e}")
    srv.close()
    print("[INFO] 删除线程停止")

if __name__ == "__main__":
    for dev in VIDEO_DEVICES:
        if not os.access(dev, os.R_OK):
            print(f"没有权限访问 {dev}，请 chmod")
            sys.exit(1)

    try:
        load_face_cascade()
        load_existing_templates()
    except Exception as e:
        print(f"初始化失败: {e}")
        sys.exit(1)

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER_IP, PORT))
        print(f"[设备端] 连接到 {SERVER_IP}:{PORT}")

        threads = [
            threading.Thread(target=video_stream, args=(sock,), daemon=True),
            threading.Thread(target=audio_stream, args=(sock,), daemon=True),
            threading.Thread(target=command_listener, args=(sock,), daemon=True),
            threading.Thread(target=receive_template, daemon=True),
            threading.Thread(target=receive_delete_request, daemon=True),
        ]
        for t in threads:
            t.start()

        while running_flag.is_set():
            time.sleep(1)

    except Exception as e:
        print(f"[设备端] 运行错误: {e}")
    finally:
        if sock:
            sock.close()
        running_flag.clear()
        time.sleep(1)
        sys.exit(0)