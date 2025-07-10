# Intelligent-Monitoring-Based-on-Loongson
2025 Embedded Competition Project


目录

• #系统架构

• #功能特性

• #环境依赖

• #安装指南

• #使用说明

• #核心算法

• #通信协议

• #项目结构

<a id="系统架构"></a>系统架构

设备端（龙芯2K1000LA）与PC客户端通过TCP/IP网络通信：
• 设备端负责音视频采集、人脸识别和快递箱计数

• PC客户端提供可视化界面和设备管理

• 双向数据传输：音视频流+控制指令

<a id="功能特性"></a>功能特性

监控功能

• 📹 720P@10FPS实时视频流

• 🔊 双声道音频同步传输

• 📅 7天历史录像存储

智能识别

• 👤 人脸识别（ORB特征匹配）

• 📦 快递箱动态计数

• ⚠️ 异常行为预警

设备管理

• ➕ 多设备添加/绑定

• 🔄 摄像头热切换

• 🗑️ 人脸模板管理

<a id="环境依赖"></a>环境依赖

设备端（龙芯2K1000LA）

opencv==3.2.0        # 计算机视觉处理
numpy~=1.21.6         # 数值计算支持
PyAudio>=0.2.11       # 音频采集
python3.7+           # 解释器环境


PC客户端

opencv-python        # 视频解码
PyAudio              # 音频播放
Pillow               # 图像处理
tkinter              # GUI界面


<a id="安装指南"></a>安装指南

设备端部署

# 安装核心依赖
sudo apt install python3-pip
pip3 install opencv-python==3.2.0.8 numpy==1.21.6 PyAudio==0.2.11

# 配置设备权限
sudo usermod -aG video $USER
sudo chmod 666 /dev/video*

# 启动服务
python3 device_side.py


客户端部署

pip install opencv-python numpy PyAudio pillow
python3 client_side.py


<a id="使用说明"></a>使用说明

设备管理

1. 添加设备：名称+IP+端口（默认8888）
2. 绑定默认设备：自动连接最近使用设备
3. 摄像头切换：支持/dev/video0和/dev/video2热切换

人脸模板操作

1. 录入：实时捕获画面+姓名绑定
2. 删除：指定姓名模板删除

历史回溯

• 存储路径：./records/

• 命名格式：YYYYMMDD_HHMMSS.avi

• 支持播放/暂停/快进控制

<a id="核心算法"></a>核心算法

快递箱计数

class BoxCounter:
    def process(self, frame):
        # 1. 背景减除获取运动物体
        # 2. 多边形轮廓检测(5-8边)
        # 3. 每秒统计最大值
        return count_per_second


人脸识别

def recognize(face_img):
    # 1. ORB特征提取
    # 2. BFMatcher匹配
    # 3. 阈值过滤(≥10个匹配点)
    return name


<a id="通信协议"></a>通信协议

端口 功能 数据格式

8888 主音视频流 [HEADER(5B)] + [DATA_LEN(4B)] + [DATA]

9999 人脸模板上传 [总长(4B)] + [姓名长度(2B)] + [姓名] + [图片数据]

9998 模板删除 [姓名长度(2B)] + [姓名]

<a id="项目结构"></a>项目结构


Intelligent-Monitoring-Based-on-Loongson/
├── client_side.py        # PC客户端主程序
├── device_side.py        # 龙芯设备端程序
├── templates/            # 人脸模板存储
├── records/              # 监控录像
└── config.json           # 设备配置
