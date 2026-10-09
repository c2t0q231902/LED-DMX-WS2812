
[README.md](https://github.com/user-attachments/files/33248076/README.md)
# LED BLE 灯控 (Windows)

一个开源的 Windows 桌面端 BLE LED 灯带控制器，适用于 **LED DMX-01** 系列 WS2812 可寻址灯带控制器。

## 免责声明




* 本项目仅供**学习交流和个人使用**，请勿用于商业用途。

* 使用者自行承担使用本软件的风险，作者不对因使用本软件造成的任何设备损坏、数据丢失或其他损失负责。

* 如官方开发者认为本项目侵犯其权益，请联系删除。

## 功能



* BLE 扫描与连接（自动识别 `LEDDMX-` 设备）

* RGB 调色 + 8 个常用颜色预设 + 系统取色器

* 亮度 / DIM 调光

* 动态模式切换 + 速度调节 + 方向控制

* **音乐律动**：捕获 Windows 系统音频（WASAPI loopback），FFT 分频后实时控制灯效，打鼓点白闪 + 自动切色

* 深色主题 UI




## 运行

### 直接使用（推荐）

下载 `Djnb.exe`，双击运行。需要 Windows 10/11 + 蓝牙适配器（BLE 4.0+）。

### 从源码运行



```
pip install bleak numpy pyaudiowpatch
python led_ble_windows.py
```

### 打包



```
pip install pyinstaller
pyinstaller --onefile --windowed --name "LED灯控" --collect-submodules bleak --collect-submodules pyaudiowpatch led_ble_windows.py
```

## 硬件



* 主控芯片：**Telink TLSR8251**

* 灯珠：WS2812 / WS2811 / SK6812 等可寻址灯带

* 广播名前缀：`LEDDMX-`

## License

MIT
<img width="200" height="200" alt="IMG_20261009_192922" src="https://github.com/user-attachments/assets/04a56f1a-bcd1-422d-bfc6-7e9d3df42209" />

