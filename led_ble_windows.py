# -*- coding: utf-8 -*-
"""
LED BLE 灯控 — Windows 桌面版
适配 LEDDMX-01 系列 WS2812 BLE 控制器
协议: 7B FF <cmd> <p1..p5> BF
"""
import asyncio, threading, colorsys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, colorchooser
from bleak import BleakScanner, BleakClient
import numpy as np
import pyaudiowpatch as pyaudio

# ---------- 协议 ----------
def _frame(cmd, p1=0xFF, p2=0xFF, p3=0xFF, p4=0xFF, p5=0xFF):
    return bytes([0x7B, 0xFF, cmd & 0xFF, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF, p4 & 0xFF, p5 & 0xFF, 0xBF])

CMD_ON   = _frame(0x04, 0x01)
CMD_OFF  = _frame(0x04, 0x00)
def cmd_rgb(r, g, b):
    return bytes([0x7B, 0xFF, 0x07, r & 0xFF, g & 0xFF, b & 0xFF, 0xFF, 0xFF, 0xBF])
def cmd_brightness(v):   return _frame(0x01, v)
def cmd_speed(v):        return _frame(0x02, v)
def cmd_mode(m):         return _frame(0x13, m)
def cmd_dim(v):          return _frame(0x09, v)
def cmd_direction(v):    return _frame(0x0D, v)
def cmd_spi_model(v):    return _frame(0x03, v)

# ---------- 颜色主题 ----------
BG       = "#1a1b26"
BG2      = "#24283b"
FG       = "#c0caf5"
ACCENT   = "#7aa2f7"
DANGER   = "#f7768e"
SUCCESS  = "#9ece6a"
WARN     = "#e0af68"
SLIDER_BG = "#2f3549"

# ---------- BLE 后端 ----------
class BleController:
    def __init__(self, log_cb):
        self.client = None; self.addr = None; self.log = log_cb
        self.loop = None; self._write_char = None

    def start_loop(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def submit(self, coro):
        if not self.loop: self.start_loop()
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def scan_async(self):
        self.log("扫描 BLE 设备...")
        devs = await BleakScanner.discover(timeout=5.0)
        found = []
        for d in devs:
            name = d.name or ""
            if name and "LED" in name.upper():
                found.append((d.address, name))
                self.log(f"  {name}  [{d.address}]")
        return found

    async def connect_async(self, addr):
        self.addr = addr
        self.client = BleakClient(addr, disconnected_callback=lambda c: self.log("设备已断开"))
        await self.client.connect()
        target = None
        for svc in self.client.services:
            for ch in svc.characteristics:
                if "febd" in str(ch.uuid).lower():
                    target = ch; break
            if target: break
        if target is None:
            for svc in self.client.services:
                for ch in svc.characteristics:
                    if "write-without-response" in ch.properties and "notify" in ch.properties:
                        target = ch; break
                if target: break
        if target is None: raise RuntimeError("未找到写特征")
        self._write_char = target
        self.log(f"已连接: {addr}")

    async def write_async(self, data: bytes):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("未连接")
        try:
            await self.client.write_gatt_char(self._write_char, data, response=False)
        except Exception:
            await self.client.write_gatt_char(self._write_char, data, response=True)

    async def disconnect_async(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        self.log("已断开")

# ---------- 音乐律动 ----------
class MusicEngine:
    def __init__(self, send_cb, log_cb):
        self.send = send_cb; self.log = log_cb
        self.running = False; self.thread = None
        self.sensitivity = 50; self._stream = None

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self._stream:
            try: self._stream.stop_stream(); self._stream.close()
            except: pass
            self._stream = None
        if self.thread: self.thread.join(timeout=2)

    def _run(self):
        try:
            pa = pyaudio.PyAudio()
            wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_out = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            loopback_dev = None
            for dev in pa.get_loopback_device_info_generator():
                if default_out["name"] in dev["name"]:
                    loopback_dev = dev; break
            if not loopback_dev:
                raise RuntimeError(f"未找到 loopback 设备")
            self.log(f"回采: {loopback_dev['name']}")
            RATE = int(loopback_dev["defaultSampleRate"]); CHUNK = 1024
            self._stream = pa.open(format=pyaudio.paFloat32, channels=1, rate=RATE,
                input=True, input_device_index=loopback_dev["index"], frames_per_buffer=CHUNK)
        except Exception as e:
            self.log(f"音频捕获失败: {e}"); self.running = False; return

        bass_avg = mid_avg = treb_avg = 0.0
        hue = 0.0; flash = 0.0; frame_count = 0; bass_history = []
        while self.running:
            raw = self._stream.read(CHUNK, exception_on_overflow=False)
            mono = np.frombuffer(raw, dtype=np.float32)
            windowed = mono * np.hanning(len(mono))
            fft = np.abs(np.fft.rfft(windowed))
            freqs = np.fft.rfftfreq(len(mono), 1.0/RATE)
            bass = np.mean(fft[(freqs>=20)&(freqs<250)])
            mid  = np.mean(fft[(freqs>=250)&(freqs<2000)])
            treb = np.mean(fft[(freqs>=2000)&(freqs<8000)])
            bass_avg = bass_avg*0.7 + bass*0.3
            mid_avg  = mid_avg*0.7 + mid*0.3
            treb_avg = treb_avg*0.7 + treb*0.3
            bass_history.append(bass_avg)
            if len(bass_history) > 20: bass_history.pop(0)
            local_avg = sum(bass_history)/len(bass_history)
            beat = bass_avg > local_avg * 1.3 and bass_avg > 0.005
            sens = self.sensitivity / 50.0
            if beat:
                flash = 1.0; hue = (hue + 0.06) % 1.0
            flash *= 0.88
            br, bg, bb = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
            vol = min(1.0, (bass_avg+mid_avg+treb_avg) * sens * 400)
            R = min(255, int(br*vol*255 + flash*255))
            G = min(255, int(bg*vol*255 + flash*255))
            B = min(255, int(bb*vol*255 + flash*255))
            frame_count += 1
            if frame_count % 2 == 0:
                self.send(cmd_rgb(R, G, B))

# ---------- UI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LED BLE 灯控")
        self.geometry("680x720")
        self.configure(bg=BG)
        self.ctrl = BleController(self.log)
        self.music = MusicEngine(self.send_fast, self.log)
        self._setup_style()
        self._build_ui()

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=FG, fieldbackground=BG2,
                       borderwidth=0, focusthickness=0)
        style.configure('TFrame', background=BG)
        style.configure('TLabelframe', background=BG, foreground=ACCENT, borderwidth=1, relief='solid')
        style.configure('TLabelframe.Label', background=BG, foreground=ACCENT, font=('Segoe UI', 9, 'bold'))
        style.configure('TButton', background=BG2, foreground=FG, padding=6, font=('Segoe UI', 9))
        style.map('TButton', background=[('active', '#343a52')])
        style.configure('Accent.TButton', background=ACCENT, foreground='#1a1b26')
        style.map('Accent.TButton', background=[('active', '#89b4fa')])
        style.configure('Danger.TButton', background=DANGER, foreground='#1a1b26')
        style.map('Danger.TButton', background=[('active', '#ff7a93')])
        style.configure('TCombobox', fieldbackground=BG2, background=BG2, foreground=FG)
        style.configure('TRadiobutton', background=BG, foreground=FG)
        style.configure('TLabel', background=BG, foreground=FG)

    def _build_ui(self):
        # 顶部
        top = ttk.Frame(self); top.pack(fill="x", padx=12, pady=(12,4))
        ttk.Label(top, text="LED BLE 灯控", font=('Segoe UI', 14, 'bold'), foreground=ACCENT).pack(side="left")
        self.status = ttk.Label(top, text="● 未连接", foreground=DANGER)
        self.status.pack(side="right")

        # 设备
        f = ttk.LabelFrame(self, text=" 设备 "); f.pack(fill="x", padx=12, pady=4)
        self.dev_cb = ttk.Combobox(f, width=35, state="readonly")
        self.dev_cb.pack(side="left", padx=8, pady=8)
        ttk.Button(f, text="扫描", command=self.scan).pack(side="left", padx=4)
        self.btn_conn = ttk.Button(f, text="连接", style='Accent.TButton', command=self.connect)
        self.btn_conn.pack(side="left", padx=4)
        ttk.Button(f, text="断开", command=self.disconnect).pack(side="left", padx=4)

        # 电源 + 亮度
        f = ttk.LabelFrame(self, text=" 基础控制 "); f.pack(fill="x", padx=12, pady=4)
        row = ttk.Frame(f); row.pack(fill="x", padx=8, pady=6)
        ttk.Button(row, text="⏻ 开", style='Accent.TButton', command=lambda: self.send(CMD_ON)).pack(side="left", padx=4)
        ttk.Button(row, text="⏻ 关", style='Danger.TButton', command=lambda: self.send(CMD_OFF)).pack(side="left", padx=4)
        ttk.Label(row, text="亮度").pack(side="left", padx=(16,4))
        self.bright = tk.Scale(row, from_=0, to=255, orient="horizontal", length=180,
                               bg=BG2, fg=FG, troughcolor=SLIDER_BG, highlightthickness=0,
                               command=lambda v: self.send(cmd_brightness(int(float(v)))))
        self.bright.set(255); self.bright.pack(side="left", padx=4)
        ttk.Label(row, text="DIM").pack(side="left", padx=(16,4))
        self.dim = tk.Scale(row, from_=0, to=100, orient="horizontal", length=100,
                           bg=BG2, fg=FG, troughcolor=SLIDER_BG, highlightthickness=0,
                           command=lambda v: self.send(cmd_dim(int(float(v)))))
        self.dim.set(100); self.dim.pack(side="left", padx=4)

        # 颜色
        f = ttk.LabelFrame(self, text=" 颜色 "); f.pack(fill="x", padx=12, pady=4)
        row = ttk.Frame(f); row.pack(fill="x", padx=8, pady=6)
        self.rgb_sliders = []
        for i, (name, c) in enumerate([("R", "#f7768e"), ("G", "#9ece6a"), ("B", "#7aa2f7")]):
            ttk.Label(row, text=name, foreground=c).pack(side="left", padx=(8,2))
            s = tk.Scale(row, from_=0, to=255, orient="horizontal", length=120,
                         bg=BG2, fg=FG, troughcolor=SLIDER_BG, highlightthickness=0,
                         command=lambda v=None: self.push_color())
            s.set(255 if i == 0 else 0)
            s.pack(side="left", padx=(0,8))
            self.rgb_sliders.append(s)
        self.preview = tk.Label(row, text="  ", bg="#000000", width=6, relief="flat")
        self.preview.pack(side="left", padx=12)
        ttk.Button(row, text="取色", command=self.pick_color).pack(side="left", padx=4)
        # 预设
        row2 = ttk.Frame(f); row2.pack(fill="x", padx=8, pady=(0,8))
        presets = [("红",(255,0,0)),("绿",(0,255,0)),("蓝",(0,0,255)),
                   ("白",(255,255,255)),("暖白",(255,180,80)),("紫",(180,0,255)),
                   ("橙",(255,120,0)),("青",(0,255,255))]
        for n, rgb in presets:
            b = tk.Button(row2, text=n, width=4, bg=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
                          fg="white" if sum(rgb)<380 else "black", relief="flat",
                          activebackground="#444", command=lambda c=rgb: self.set_rgb(*c))
            b.pack(side="left", padx=3)

        # 动态模式
        f = ttk.LabelFrame(self, text=" 动态模式 "); f.pack(fill="x", padx=12, pady=4)
        row = ttk.Frame(f); row.pack(fill="x", padx=8, pady=6)
        modes = [("渐变",0x00),("M1",0x01),("M2",0x02),("M3",0x03),
                 ("M4",0x04),("M5",0x05),("M6",0x06),("M7",0x07)]
        for n, c in modes:
            ttk.Button(row, text=n, width=5, command=lambda m=c: self.send(cmd_mode(m))).pack(side="left", padx=3)
        ttk.Label(row, text="速度").pack(side="left", padx=(16,4))
        self.speed = tk.Scale(row, from_=0, to=100, orient="horizontal", length=120,
                              bg=BG2, fg=FG, troughcolor=SLIDER_BG, highlightthickness=0,
                              command=lambda v: self.send(cmd_speed(int(float(v)))))
        self.speed.set(50); self.speed.pack(side="left", padx=4)
        self.dir_var = tk.IntVar(value=0)
        ttk.Radiobutton(row, text="正向", value=0, variable=self.dir_var,
                        command=lambda: self.send(cmd_direction(0))).pack(side="left", padx=(16,2))
        ttk.Radiobutton(row, text="反向", value=1, variable=self.dir_var,
                        command=lambda: self.send(cmd_direction(1))).pack(side="left", padx=2)

        # 音乐律动
        f = ttk.LabelFrame(self, text=" 音乐律动 "); f.pack(fill="x", padx=12, pady=4)
        row = ttk.Frame(f); row.pack(fill="x", padx=8, pady=6)
        self.btn_music = ttk.Button(row, text="▶ 启动", style='Accent.TButton', command=self.start_music)
        self.btn_music.pack(side="left", padx=4)
        ttk.Button(row, text="■ 停止", command=self.stop_music).pack(side="left", padx=4)
        ttk.Label(row, text="灵敏度").pack(side="left", padx=(16,4))
        self.sens = tk.Scale(row, from_=10, to=200, orient="horizontal", length=180,
                             bg=BG2, fg=FG, troughcolor=SLIDER_BG, highlightthickness=0,
                             command=lambda v: setattr(self.music, 'sensitivity', int(float(v))))
        self.sens.set(50); self.sens.pack(side="left", padx=4)

        # 日志
        f = ttk.LabelFrame(self, text=" 日志 "); f.pack(fill="both", expand=True, padx=12, pady=4)
        self.log_box = scrolledtext.ScrolledText(f, height=6, state="disabled",
            font=("Consolas", 9), bg=BG2, fg=FG, insertbackground=FG, relief="flat")
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)

    # ---- 业务 ----
    def log(self, msg):
        def _a():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", str(msg)+"\n"); self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _a)

    def set_status(self, text, color):
        self.status.configure(text=text, foreground=color)

    def set_rgb(self, r, g, b):
        self.rgb_sliders[0].set(r); self.rgb_sliders[1].set(g); self.rgb_sliders[2].set(b)
        self.push_color()

    def push_color(self):
        r, g, b = [int(s.get()) for s in self.rgb_sliders]
        self.preview.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
        self.send(cmd_rgb(r, g, b))

    def pick_color(self):
        c = colorchooser.askcolor(parent=self)
        if c and c[0]:
            self.set_rgb(*[int(x) for x in c[0]])

    def start_music(self):
        if not self.ctrl.client or not self.ctrl.client.is_connected:
            messagebox.showinfo("提示", "请先连接灯"); return
        self.music.sensitivity = int(self.sens.get())
        self.music.start()

    def stop_music(self):
        self.music.stop()
        r, g, b = [int(s.get()) for s in self.rgb_sliders]
        self.send(cmd_rgb(r, g, b))

    def send(self, data: bytes):
        def _do():
            try: self.ctrl.submit(self.ctrl.write_async(data)).result(timeout=5)
            except: pass
        threading.Thread(target=_do, daemon=True).start()

    def send_fast(self, data: bytes):
        try: self.ctrl.submit(self.ctrl.write_async(data))
        except: pass

    def scan(self):
        def _do():
            try:
                devs = self.ctrl.submit(self.ctrl.scan_async()).result(timeout=15)
                def _f():
                    self.dev_cb["values"] = [f"{n}  [{a}]" for a,n in devs]
                    if devs: self.dev_cb.current(0)
                self.after(0, _f)
            except Exception as e: self.log(f"扫描失败: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def connect(self):
        sel = self.dev_cb.get()
        if not sel: messagebox.showinfo("提示","先扫描选设备"); return
        addr = sel.split("[")[-1].rstrip("]")
        def _do():
            try:
                self.ctrl.submit(self.ctrl.connect_async(addr)).result(timeout=15)
                self.after(0, lambda: [self.btn_conn.configure(state="disabled", text="已连接"),
                                        self.set_status("● 已连接", SUCCESS)])
            except Exception as e: self.log(f"连接失败: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def disconnect(self):
        def _do():
            try:
                self.ctrl.submit(self.ctrl.disconnect_async()).result(timeout=5)
                self.after(0, lambda: [self.btn_conn.configure(state="normal", text="连接"),
                                        self.set_status("● 未连接", DANGER)])
            except Exception as e: self.log(f"断开失败: {e}")
        threading.Thread(target=_do, daemon=True).start()

if __name__ == "__main__":
    App().mainloop()
