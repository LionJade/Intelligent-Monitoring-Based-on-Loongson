import sys
import cv2
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import Image, ImageTk
import os
import datetime
import subprocess
import json
import socket
import struct
import numpy as np
import pyaudio
import time

# ==============================================================================
# 全局配置和默认值
# ==============================================================================

# 默认设备列表 (Name -> (IP, main_stream_port))
# 这是程序的内置默认设备。
def default_devices_config():
    return {
        "龙芯派摄像头": ("192.168.137.1", 8888), # 示例 IP，请替换为实际 IP
        "备用摄像头": ("192.168.137.104", 8890)    # 示例 IP，请替换为实际 IP
    }

TEMPLATE_PORT = 9999  # Port for sending face templates (from clientv7.py)
DELETE_PORT = 9998    # Port for deleting face templates (from clientv7.py)

# These dimensions should match the device side's TARGET_WIDTH and TARGET_HEIGHT for recording
# Based on '11.py', TARGET_WIDTH = 320, TARGET_HEIGHT = 240
RECORDING_WIDTH = 320
RECORDING_HEIGHT = 240
RECORDING_FPS = 10     # Consistent with '11.py'

# ==============================================================================
# StreamClient 类 (统一版)
# 处理主视频/音频流的接收和播放
# ==============================================================================
class StreamClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.conn = None
        self.running = False
        self.audio = None
        self.audio_stream = None
        self.server_socket = None # To hold the listening socket

        self.save_path = "./records"
        os.makedirs(self.save_path, exist_ok=True)
        self.writer = None

    def start(self):
        max_retries = 3
        retry_count = 0
        if self.running or self.conn:
            self.stop()

        while retry_count < max_retries and not self.running:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.settimeout(10)
            try:
                self.server_socket.bind(("0.0.0.0", self.port))
                self.server_socket.listen(1)
                print(f"[StreamClient] 等待设备连接到端口 {self.port}...")
                self.conn, addr = self.server_socket.accept()
                print(f"[StreamClient] 设备从 {addr} 连接成功")
                self.running = True

                self.audio = pyaudio.PyAudio()
                self.audio_stream = self.audio.open(format=pyaudio.paInt16, channels=2, rate=44100, output=True)

                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                fname = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".avi"
                self.writer = cv2.VideoWriter(os.path.join(self.save_path, fname), fourcc, RECORDING_FPS, (RECORDING_WIDTH, RECORDING_HEIGHT))
                if not self.writer.isOpened():
                    raise IOError(f"无法打开视频写入器。检查路径、编解码器或分辨率 ({RECORDING_WIDTH}x{RECORDING_HEIGHT})。")

                print("[StreamClient] 开始接收数据...")
                time.sleep(1)
                break
            except Exception as e:
                print(f"[StreamClient] 连接尝试 {retry_count + 1}/{max_retries} 失败: {e}")
                retry_count += 1
                if self.server_socket:
                    self.server_socket.close()
                time.sleep(2)

        if not self.running:
            print("[StreamClient] 连接失败，已达到最大重试次数。")
            raise ConnectionError("无法建立流连接。")

    def stop(self):
        self.running = False
        if self.conn:
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
                self.conn.close()
            except OSError as e:
                print(f"[StreamClient] 套接字关闭时出错: {e}")
            finally:
                self.conn = None
            print("[StreamClient] 套接字连接已关闭。")
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError as e:
                print(f"[StreamClient] 服务器套接字关闭时出错: {e}")
            finally:
                self.server_socket = None
            print("[StreamClient] 服务器套接字已关闭。")
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                print(f"[StreamClient] 音频流停止或关闭时出错: {e}")
            finally:
                self.audio_stream = None
            print("[StreamClient] 音频流已停止并关闭。")
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                print(f"[StreamClient] PyAudio 终止时出错: {e}")
            finally:
                self.audio = None
            print("[StreamClient] PyAudio 已终止。")
        if self.writer:
            try:
                self.writer.release()
                print("[StreamClient] 视频写入器已释放。")
            except Exception as e:
                print(f"[StreamClient] 视频写入器释放时出错: {e}")
            finally:
                self.writer = None

    def send_command(self, command):
        if self.conn and self.running:
            try:
                self.conn.sendall(command.encode('utf-8'))
                print(f"[StreamClient] 已发送命令: {command}")
            except Exception as e:
                print(f"[StreamClient] 发送命令失败: {e}。连接可能已丢失。")
                self.running = False

    def read_stream(self):
        if not self.conn or not self.running:
            return None, None
        try:
            header = self.conn.recv(5)
            if not header:
                print("[StreamClient] 警告: 接收到空头，可能连接已丢失。停止流。")
                self.running = False
                return None, None

            length_bytes = self.conn.recv(4)
            if not length_bytes or len(length_bytes) < 4:
                print("[StreamClient] 警告: 接收到不完整的长度字节，可能连接已丢失。停止流。")
                self.running = False
                return None, None

            data_len = int.from_bytes(length_bytes, byteorder='big')

            if data_len <= 0 or data_len > (1024 * 1024 * 5):
                print(f"[StreamClient] 警告: 接收到的数据长度无效: {data_len}。连接可能已损坏。停止流。")
                self.running = False
                return None, None

            data = b''
            bytes_received = 0
            while bytes_received < data_len:
                packet = self.conn.recv(min(4096, data_len - bytes_received))
                if not packet:
                    print(f"[StreamClient] 错误: 数据接收不完整，接收 {bytes_received}/{data_len} 字节。连接丢失。停止流。")
                    self.running = False
                    return None, None
                data += packet
                bytes_received += len(packet)
            return header, data
        except BrokenPipeError:
            print("[StreamClient] 读取流: 连接中断 (BrokenPipeError)。停止流。")
            self.running = False
            return None, None
        except socket.timeout:
            print("[StreamClient] 读取流: 套接字超时期间接收数据。停止流。")
            self.running = False
            return None, None
        except Exception as e:
            print(f"[StreamClient] 读取流: 读取数据时出错: {e}. 停止流。")
            self.running = False
            return None, None

# ==============================================================================
# MonitoringApp 类 (主监控应用，统一版)
# ==============================================================================
class MonitoringApp:
    def __init__(self, root):
        self.root = root
        self.root.title("统一监控客户端")
        self.root.geometry("800x600")

        self.last_frame = None  # 用于人脸模板捕捉的最后一帧

        # 初始化 _after_id，确保它始终存在
        self._after_id = ''

        # 设备列表 (使用 clientv7.py 的加载逻辑，支持 (IP, Port) 元组)
        self.devices = self.load_devices()

        if not self.devices:
            self.devices = default_devices_config()
            if not self.devices:
                self.devices = {"默认设备": ("127.0.0.1", 8888)}
            self.save_devices()

        initial_device_name = self.load_default_device()
        if initial_device_name not in self.devices and self.devices:
            initial_device_name = list(self.devices.keys())[0]
        elif not self.devices:
            initial_device_name = "无可用设备"

        self.device_selector = tk.StringVar(value=initial_device_name)
        if not self.devices:
            self.device_selector.set("请添加设备")

        self.client = None
        self.updater_thread = None

        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        video_frame = tk.Frame(main_frame, bg="black")
        video_frame.pack(fill=tk.BOTH, expand=True)

        self.video_label = tk.Label(video_frame, text="等待视频…", bg="black", fg="white", font=("Helvetica", 16))
        self.video_label.pack(fill=tk.BOTH, expand=True)

        control_frame = tk.Frame(main_frame, bd=2, relief=tk.GROOVE)
        control_frame.pack(fill=tk.X, pady=5)

        tk.Label(control_frame, text="选择设备:").pack(side=tk.LEFT, padx=5, pady=2)
        self.device_option_menu = tk.OptionMenu(control_frame, self.device_selector, *(self.devices.keys() if self.devices else ["无可用设备"]))
        self.device_option_menu.pack(side=tk.LEFT, padx=5, pady=2)
        if not self.devices:
            self.device_option_menu.config(state=tk.DISABLED)

        tk.Label(control_frame, text="选择摄像头:").pack(side=tk.LEFT, padx=5, pady=2)
        self.camera_selector = tk.StringVar(value="/dev/video0")
        self.camera_option_menu = tk.OptionMenu(control_frame, self.camera_selector, *["/dev/video0", "/dev/video2"], command=self.switch_camera)
        self.camera_option_menu.pack(side=tk.LEFT, padx=5, pady=2)

        button_frame = tk.Frame(root, bd=2, relief=tk.GROOVE)
        button_frame.pack(fill=tk.X, pady=5)

        tk.Button(button_frame, text="开始监控", command=self.start_stream, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(button_frame, text="停止监控", command=self.stop_stream, bg="#F44336", fg="white").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(button_frame, text="录入人脸", command=self.capture_template, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(button_frame, text="删除人脸模板", command=self.delete_template, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(button_frame, text="查看历史监控", command=self.view_history, bg="#607D8B", fg="white").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(button_frame, text="添加设备", command=self.add_device, bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(button_frame, text="绑定默认设备", command=self.save_default_device, bg="#795548", fg="white").pack(side=tk.LEFT, padx=5, pady=2)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        print("[MonitoringApp] 正在关闭应用程序...")
        self.stop_stream()
        self.root.destroy()
        sys.exit(0)

    # ---------- 设备管理 ----------
    def load_devices(self):
        loaded_devices = {}
        if os.path.exists("devices.json"):
            try:
                with open("devices.json", "r", encoding="utf-8") as f:
                    loaded_devices = json.load(f)
                    print("[MonitoringApp] devices.json 加载成功。")
            except json.JSONDecodeError:
                print("[MonitoringApp] devices.json 损坏或为空，重新加载默认配置。")
                loaded_devices = {}
            except Exception as e:
                print(f"[MonitoringApp] 加载 devices.json 时出错: {e}")
                loaded_devices = {}

        if not loaded_devices:
            print("[MonitoringApp] 使用默认设备配置。")
            loaded_devices = default_devices_config()
            try:
                with open("devices.json", "w", encoding="utf-8") as f:
                    json.dump(loaded_devices, f, indent=2)
            except Exception as e:
                print(f"[MonitoringApp] 无法将默认设备写入 devices.json: {e}")
        return loaded_devices

    def save_devices(self):
        try:
            with open("devices.json", "w", encoding="utf-8") as f:
                json.dump(self.devices, f, indent=2)
            print("[MonitoringApp] devices.json 已保存。")
        except Exception as e:
            print(f"[MonitoringApp] 保存 devices.json 时出错: {e}")

    def add_device(self):
        name = simpledialog.askstring("添加设备", "设备名称：")
        if not name: return

        ip = simpledialog.askstring("添加设备", "设备 IP：", initialvalue="192.168.137.XXX")
        if not ip: return

        port = simpledialog.askinteger("添加设备", "主监控端口：", initialvalue=8888)
        if port is None: return

        if name and ip and port:
            self.devices[name] = (ip, port)
            self.save_devices()
            self.update_device_selector()
            self.device_selector.set(name)
            messagebox.showinfo("成功", "已添加设备")

    def update_device_selector(self):
        menu = self.device_option_menu["menu"]
        menu.delete(0, 'end')
        if self.devices:
            for dev_name in self.devices.keys():
                menu.add_command(label=dev_name, command=tk._setit(self.device_selector, dev_name))
            self.device_option_menu.config(state=tk.NORMAL)
            if self.device_selector.get() not in self.devices:
                self.device_selector.set(list(self.devices.keys())[0])
        else:
            self.device_selector.set("无可用设备")
            self.device_option_menu.config(state=tk.DISABLED)

    def save_default_device(self):
        selected_device = self.device_selector.get()
        if selected_device == "无可用设备" or selected_device not in self.devices:
            messagebox.showwarning("警告", "请先添加或选择一个有效设备。")
            return

        config = {"default": selected_device}
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            messagebox.showinfo("成功", f"已保存默认设备: {selected_device}")
        except Exception as e:
            messagebox.showerror("错误", f"保存默认设备失败: {e}")

    def load_default_device(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("default")
            except json.JSONDecodeError:
                print("[MonitoringApp] config.json 损坏或为空。")
                return None
            except Exception as e:
                print(f"[MonitoringApp] 加载 config.json 时出错: {e}")
                return None
        return None

    # ---------- 视频流和录制 ----------
    def start_stream(self):
        self.stop_stream()

        dev_name = self.device_selector.get()
        if dev_name == "无可用设备" or dev_name not in self.devices:
            messagebox.showwarning("警告", "请先添加或选择一个有效的设备。")
            return

        ip, port = self.devices[dev_name]
        self.client = StreamClient(ip, port)
        try:
            self.client.start()
            print(f"[MonitoringApp] StreamClient 为 {ip}:{port} 启动成功。")
            self.client.send_command(self.camera_selector.get())
        except ConnectionError as ce:
            messagebox.showerror("连接失败", f"无法启动设备连接：{ce}\n请检查设备是否运行、IP和端口是否正确，或网络配置。")
            if self.client:
                self.client.stop()
            self.client = None
            return
        except IOError as ioe:
            messagebox.showerror("录制初始化失败", f"无法初始化视频录制：{ioe}\n请检查录制路径或权限。")
            if self.client:
                self.client.stop()
            self.client = None
            return
        except Exception as e:
            messagebox.showerror("启动失败", f"启动流时发生未知错误：{e}")
            if self.client:
                self.client.stop()
            self.client = None
            return

        self.updater_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.updater_thread.start()
        print("[MonitoringApp] 数据更新线程已启动。")

    def stop_stream(self):
        if self.client:
            self.client.stop()
            self.client = None
            print("[MonitoringApp] 监控流已停止。")
        if self.updater_thread and self.updater_thread.is_alive():
            print("[MonitoringApp] 等待更新线程结束...")
            self.updater_thread = None

        if self._after_id != '':
            try:
                self.root.after_cancel(self._after_id)
            except ValueError:
                pass
            self._after_id = ''

        self.video_label.config(image='')
        self.video_label.configure(text="等待视频…")

    def update_loop(self):
        frame_counter = 0
        while self.client and self.client.running:
            header, data = self.client.read_stream()
            if header is None:
                print(f"[MonitoringApp] 没有有效数据或连接丢失 (header is None)，停止更新循环。总帧数: {frame_counter}。")
                self.root.after(0, self.stop_stream)
                break

            if header == b"VIDEO":
                try:
                    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        frame_counter += 1
                        img_height, img_width = frame.shape[:2]
                        lbl_width = self.video_label.winfo_width()
                        lbl_height = self.video_label.winfo_height()

                        if lbl_width == 1 or lbl_height == 1:
                            continue

                        aspect_ratio = img_width / img_height
                        if lbl_width / lbl_height > aspect_ratio:
                            new_height = lbl_height
                            new_width = int(lbl_height * aspect_ratio)
                        else:
                            new_width = lbl_width
                            new_height = int(lbl_width / aspect_ratio)

                        display_frame = cv2.resize(frame, (new_width, new_height))
                        rgb_frame_for_display = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                        imgtk = ImageTk.PhotoImage(image=Image.fromarray(rgb_frame_for_display))

                        self._after_id = self.root.after(0, lambda img=imgtk: self._update_video_label(img))

                        frame_for_writer = cv2.resize(frame, (RECORDING_WIDTH, RECORDING_HEIGHT))
                        self.last_frame = frame_for_writer.copy()

                        if self.client.writer and self.client.writer.isOpened():
                            self.client.writer.write(frame_for_writer)
                        else:
                            print("[MonitoringApp] 警告: 视频写入器未打开或已关闭，跳过帧写入。")
                    else:
                        print("[MonitoringApp] 警告: 视频帧解码失败 (frame is None)。")
                except Exception as e:
                    print(f"[MonitoringApp] 视频帧处理错误: {e}")
            elif header == b"AUDIO":
                try:
                    if self.client.audio_stream:
                        self.client.audio_stream.write(data)
                except Exception as e:
                    print(f"[MonitoringApp] 音频播放错误: {e}")
            else:
                print(f"[MonitoringApp] 警告: 接收到未知头: {header.decode()}。")
        print(f"[MonitoringApp] 数据更新线程已停止。最终帧数: {frame_counter}。")

    def _update_video_label(self, imgtk):
        if hasattr(self.video_label, 'winfo_exists') and self.video_label.winfo_exists():
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)

    def switch_camera(self, value):
        if self.client and self.client.running:
            self.client.send_command(value)
            print(f"[MonitoringApp] 请求切换摄像头至: {value}")
        else:
            messagebox.showwarning("警告", "客户端未运行，无法切换摄像头。请先开始监控。")

    # ---------- 录入/删除模板 ----------
    def capture_template(self):
        if self.last_frame is None:
            messagebox.showwarning("提示", "没有可用的视频帧，请先开始监控。")
            return

        name = simpledialog.askstring("录入人脸", "请输入姓名：")
        if not name:
            return

        ok, enc = cv2.imencode(".jpg", self.last_frame)
        if not ok:
            messagebox.showerror("编码失败", "无法编码当前帧为 JPG。")
            return

        img_bytes = enc.tobytes()
        name_bytes = name.encode("utf-8")

        packet = (
                         len(name_bytes) + len(img_bytes) + 2
                 ).to_bytes(4, "big") + len(name_bytes).to_bytes(2, "big") + name_bytes + img_bytes

        dev_name = self.device_selector.get()
        if dev_name not in self.devices:
            messagebox.showerror("错误", "选定的设备不存在，无法发送模板。")
            return
        ip, _ = self.devices[dev_name]

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((ip, TEMPLATE_PORT))
                s.sendall(packet)
            messagebox.showinfo("成功", f"{name} 模板已上传")
        except socket.timeout:
            messagebox.showerror("连接超时", f"连接到 {ip}:{TEMPLATE_PORT} 超时。请检查设备端服务是否运行。")
        except ConnectionRefusedError:
            messagebox.showerror("连接拒绝", f"设备拒绝连接到 {ip}:{TEMPLATE_PORT}。请检查设备端服务是否运行。")
        except Exception as e:
            messagebox.showerror("失败", f"上传模板失败: {e}")

    def delete_template(self):
        dev_name = self.device_selector.get()
        if dev_name not in self.devices:
            messagebox.showerror("错误", "选定的设备不存在，无法删除模板。")
            return
        ip, _ = self.devices[dev_name]

        name = simpledialog.askstring("删除模板", "请输入要删除的姓名：")
        if not name:
            return

        try:
            name_bytes = name.encode("utf-8")
            packet = len(name_bytes).to_bytes(2, "big") + name_bytes
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((ip, DELETE_PORT))
                s.sendall(packet)
            messagebox.showinfo("成功", f"{name} 模板已发送删除请求。")
        except socket.timeout:
            messagebox.showerror("连接超时", f"连接到 {ip}:{DELETE_PORT} 超时。请检查设备端服务是否运行。")
        except ConnectionRefusedError:
            messagebox.showerror("连接拒绝", f"设备拒绝连接到 {ip}:{DELETE_PORT}。请检查设备端服务是否运行。")
        except Exception as e:
            messagebox.showerror("失败", f"删除模板失败: {e}")

    # ---------- 历史视频 ----------
    def view_history(self):
        history_path = "./records"
        os.makedirs(history_path, exist_ok=True)

        files = sorted([f for f in os.listdir(history_path) if f.endswith((".avi", ".mp4"))], reverse=True)
        if not files:
            messagebox.showinfo("提示", "没有历史录像")
            return

        win = tk.Toplevel(self.root)
        win.title("历史记录")

        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for f in files:
            tk.Button(scrollable_frame, text=f, command=lambda fp=f: self.play_video(fp), padx=5, pady=2).pack(fill=tk.X, pady=2)

        win.update_idletasks()
        win_width = win.winfo_reqwidth()
        win_height = min(win.winfo_reqheight(), 600)
        win.geometry(f"{win_width}x{win_height}")

    def play_video(self, fname):
        win = tk.Toplevel(self.root)
        win.title(f"播放: {fname}")
        win.geometry("700x550")

        lbl = tk.Label(win, bg="black")
        lbl.pack(fill=tk.BOTH, expand=True)

        ctrl_frame = tk.Frame(win)
        ctrl_frame.pack(fill=tk.X, pady=5)

        pause_btn = tk.Button(ctrl_frame, text="暂停", bg="#00BCD4", fg="white")
        pause_btn.pack(side=tk.LEFT, padx=5)

        rewind_btn = tk.Button(ctrl_frame, text="后退10秒", bg="#FF5722", fg="white")
        rewind_btn.pack(side=tk.LEFT, padx=5)

        fast_forward_btn = tk.Button(ctrl_frame, text="快进10秒", bg="#8BC34A", fg="white")
        fast_forward_btn.pack(side=tk.LEFT, padx=5)

        time_label = tk.Label(ctrl_frame, text="00:00 / 00:00", font=("Helvetica", 10))
        time_label.pack(side=tk.LEFT, padx=10)

        progress = tk.Scale(ctrl_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=300, showvalue=False, command=lambda val: on_progress(val, from_scale=True))
        progress.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        video_path = os.path.join("./records", fname)
        if not os.path.exists(video_path):
            print(f"[MonitoringApp] 错误: 视频文件 {video_path} 不存在。")
            messagebox.showerror("播放错误", f"视频文件 {fname} 不存在。")
            win.destroy()
            return

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[MonitoringApp] 警告: 无法打开视频文件 {fname}，检查文件编码或路径。")
            messagebox.showerror("播放错误", f"无法打开视频文件: {fname}。可能编码不兼容，请检查或重新录制。")
            win.destroy()
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = RECORDING_FPS  # Force using the recorded FPS to avoid mismatch
        print(f"[MonitoringApp] 使用录制帧率 {fps} FPS 播放 {fname}。")
        delay = int(1000 / fps)

        state = {"paused": False, "current_frame": 0, "playing": True}
        _after_id_play = None

        def update_time_display():
            if not state["playing"]: return
            current_time_sec = state["current_frame"] / fps
            total_time_sec = total_frames / fps
            current_time = str(datetime.timedelta(seconds=int(current_time_sec)))
            total_time = str(datetime.timedelta(seconds=int(total_time_sec)))
            time_label.config(text=f"{current_time} / {total_time}")
            if state["playing"]:
                win.after(1000, update_time_display)

        def toggle_pause():
            state["paused"] = not state["paused"]
            pause_btn.config(text="继续" if state["paused"] else "暂停")
            if not state["paused"]:
                update_frame()

        def fast_forward():
            if not cap.isOpened() or not state["playing"]: return
            state["current_frame"] = min(total_frames - 1, state["current_frame"] + int(fps * 10))
            cap.set(cv2.CAP_PROP_POS_FRAMES, state["current_frame"])
            update_frame()

        def rewind():
            if not cap.isOpened() or not state["playing"]: return
            state["current_frame"] = max(0, state["current_frame"] - int(fps * 10))
            cap.set(cv2.CAP_PROP_POS_FRAMES, state["current_frame"])
            update_frame()

        def on_progress(val, from_scale=False):
            if not cap.isOpened() or not state["playing"]: return
            if from_scale:
                target_frame = int(float(val) / 100 * total_frames)
                state["current_frame"] = target_frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                update_frame()

        def update_frame():
            nonlocal _after_id_play
            if not state["playing"]:
                if _after_id_play != '':
                    try:
                        win.after_cancel(_after_id_play)
                    except ValueError:
                        pass
                return

            if not state["paused"]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, state["current_frame"])
                ret, frame = cap.read()
                if ret:
                    state["current_frame"] += 1

                    img_height, img_width = frame.shape[:2]
                    lbl_width = lbl.winfo_width()
                    lbl_height = lbl.winfo_height()

                    if lbl_width == 1 or lbl_height == 1:
                        _after_id_play = win.after(delay, update_frame)
                        return

                    aspect_ratio = img_width / img_height
                    if lbl_width / lbl_height > aspect_ratio:
                        new_height = lbl_height
                        new_width = int(lbl_height * aspect_ratio)
                    else:
                        new_width = lbl_width
                        new_height = int(lbl_width / aspect_ratio)

                    display_frame = cv2.resize(frame, (new_width, new_height))
                    display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                    imgtk = ImageTk.PhotoImage(image=Image.fromarray(display_frame))
                    lbl.imgtk = imgtk
                    lbl.config(image=imgtk)

                    if not progress.get() == int(state["current_frame"] * 100 / total_frames):
                        progress.set(int(state["current_frame"] * 100 / total_frames))
                else:
                    print(f"[MonitoringApp] 视频 {fname} 播放结束，帧读取失败。")
                    state["playing"] = False
                    cap.release()
                    messagebox.showinfo("播放完成", f"视频 {fname} 播放完毕。")
                    if _after_id_play != '':
                        try:
                            win.after_cancel(_after_id_play)
                        except ValueError:
                            pass
                    return

            _after_id_play = win.after(delay, update_frame)

        pause_btn.config(command=toggle_pause)
        fast_forward_btn.config(command=fast_forward)
        rewind_btn.config(command=rewind)

        update_time_display()
        update_frame()

        def on_win_close_play():
            state["playing"] = False
            if _after_id_play != '':
                try:
                    win.after_cancel(_after_id_play)
                except ValueError:
                    pass
            cap.release()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_win_close_play)

# ---------- main ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = MonitoringApp(root)
    root.mainloop()