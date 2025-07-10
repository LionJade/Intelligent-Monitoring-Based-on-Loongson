# Intelligent-Monitoring-Based-on-Loongson
2025 Embedded Competition Project

## Overview
This project is an intelligent monitoring system based on the Loongson 2K1000LA architecture, designed for industrial security and production process monitoring. The system integrates sensors like cameras and microphones, with the Loongson processor handling video and audio data collection and processing. It includes both edge and cloud-based intelligence for industrial scenarios, offering facial recognition, object motion detection, and production flow monitoring.

## Features
- **Real-time Monitoring**: Supports live video/audio streaming and recording.
- **Face Recognition**: Real-time facial recognition on the device side.
- **Object Detection**: Detects moving objects such as packages, and counts them per second.
- **Industrial Process Monitoring**: Monitors production efficiency and safety.
- **PC Client**: Manages devices, displays real-time and historical data, and supports face template management.
- **Flexible Device Management**: Add, remove, and bind devices to the system with ease.
  
## System Requirements

### Device-Side Requirements:
- **opencv==3.2.0**: Required for image processing, including object and face detection.
- **numpy~=1.21.6**: Used for numerical operations, especially in handling arrays and matrices in image processing.
- **PyAudio>=0.2.11**: Necessary for handling audio input/output operations.

### Software Dependencies:
Ensure all dependencies are installed using the following command:
```bash
pip install opencv-python==3.2.0 numpy~=1.21.6 PyAudio>=0.2.11
```

### Hardware Requirements:
- **Loongson 2K1000LA Processor**  
  The main processing unit for handling video/audio data and running edge algorithms.

- **Cameras**  
  Industrial-grade or USB cameras for capturing video feeds. It can include a microphone.

- **Microphones**  
  For capturing audio, which is necessary for complete monitoring.

- **PC for Client**  
  A desktop or laptop PC running the client application to monitor devices and manage the system.

- **Network**  
  A stable local network to connect the device (Loongson board) and the client PC.

## Installation
1. Clone the repository or download the project files to your local machine.

2. Install the required Python dependencies:
  ```bash
  pip install opencv-python==3.2.0 numpy~=1.21.6 PyAudio>=0.2.11
  ```
  
3. Configure the device and PC client settings (e.g., IP addresses, ports).

4. Run the PC client to start the application:
  ```bash
  python3 client_new7.py
  ```

5. On the device (Loongson board), run the device-side program to start video/audio streaming and object detection:
   ```bash
   python3 faceDetectv7.1.py
   ```
   
## Usage

1. **Start Video Stream**: 
   - Launch the PC client and select the device you want to monitor.
   - Click on the **Start Monitoring** button to begin live monitoring, which includes both video and audio streams.
   
2. **Manage Face Templates**:
   - To add new face recognition templates, click on **Capture Face Template**.
   - To remove a previously saved face template, click on **Delete Face Template** and enter the name of the person whose template you wish to delete.
   
3. **Monitor Package Count**:
   - The device will count and display the number of packages passing through the monitored area every second.

4. **View Historical Data**:
   - View previously recorded video and other data by selecting **View History**.

## Application Areas
This system is designed for industrial environments, and it can be applied in various sectors:
- **Factory Production Lines**: Real-time monitoring of personnel, products, and process flow.
- **Industrial Parks**: Security surveillance, preventing unauthorized access.
- **Industrial Warehouses**: Object tracking and inventory management.
- **Chemical Plants**: Monitoring critical safety parameters and process control.

## License
This project is open-source and available under the MIT License.

## Acknowledgements
- Thanks to the development team and resources provided by the **Loongson** ecosystem.
- Special appreciation for the **OpenCV** community for providing tools for vision-based applications.
