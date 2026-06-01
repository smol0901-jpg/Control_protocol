"""
DevCleaner Pro HUD – Расширенный мониторинг (Tkinter)
NEURAL_ARCHTECT_PREMIUM++ v8.3
Более 300 строк кода: графики, история, управление процессами,
прозрачность, ручной и автоматический лёгкий режим.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import psutil
from collections import deque

class HistoryChart:
    def __init__(self, parent, width, height, title, color, max_points=60):
        self.canvas = tk.Canvas(parent, width=width, height=height, bg="#1e1e2e", highlightthickness=0)
        self.width = width
        self.height = height
        self.color = color
        self.max_points = max_points
        self.data = deque(maxlen=max_points)

        # Оси и сетка
        self.canvas.create_line(30, 10, 30, height-20, fill="#555555")
        self.canvas.create_line(30, height-20, width-10, height-20, fill="#555555")
        self.canvas.create_text(15, height//2, text="100%", fill="#aaaaaa", font=("Arial", 7), angle=90)
        self.canvas.create_text(15, height-20, text="0%", fill="#aaaaaa", font=("Arial", 7), angle=90)
        self.canvas.create_text(width-20, height-10, text="t", fill="#aaaaaa", font=("Arial", 7))
        self.canvas.create_text(width//2, 10, text=title, fill="#ffffff", font=("Arial", 9, "bold"))

        self.line_id = None
        self.area_id = None

    def add_point(self, value):
        self.data.append(value)
        self.draw()

    def draw(self):
        if not self.data:
            return
        self.canvas.delete(self.line_id)
        self.canvas.delete(self.area_id)

        left, right = 35, self.width - 15
        top, bottom = 15, self.height - 25
        h = bottom - top
        w = right - left

        points_xy = []
        for i, val in enumerate(self.data):
            x = left + (i / (self.max_points-1)) * w if self.max_points > 1 else left
            y = bottom - (val / 100.0) * h
            points_xy.extend((x, y))

        if len(points_xy) >= 4:
            self.line_id = self.canvas.create_line(points_xy, fill=self.color, width=2, smooth=True)
            fill_points = list(points_xy)
            fill_points.extend([right, bottom, left, bottom])
            self.area_id = self.canvas.create_polygon(fill_points, fill=self.color, stipple="gray25", outline="")

class DevCleanerHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DevCleaner Pro HUD – NEURAL_ARCHTECT_PREMIUM++ v8.3")
        self.root.geometry("520x680")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="#0f0f1a")

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#0f0f1a")
        self.style.configure("TLabel", background="#0f0f1a", foreground="#e0e0e0", font=("Consolas", 9))
        self.style.configure("TButton", background="#2c3e50", foreground="white", font=("Consolas", 9))
        self.style.map("TButton", background=[("active", "#34495e")])
        self.style.configure("TCheckbutton", background="#0f0f1a", foreground="#e0e0e0")

        self.active_mode = True
        self.manual_mode = False
        self.active_interval = 2000
        self.idle_interval = 30000
        self.update_interval = self.active_interval

        self.setup_ui()

        self.root.bind("<Unmap>", self.on_minimize)
        self.root.bind("<Map>", self.on_restore)

        self.update_data()
        self.root.after(5000, self.check_active_state)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        info_frame = ttk.Frame(main_frame, relief=tk.RIDGE, borderwidth=2, padding=5)
        info_frame.pack(fill=tk.X, pady=(0, 5))

        self.cpu_label = ttk.Label(info_frame, text="CPU: --%", font=("Consolas", 12, "bold"))
        self.cpu_label.grid(row=0, column=0, padx=10, pady=2, sticky="w")
        self.mem_label = ttk.Label(info_frame, text="RAM: --%", font=("Consolas", 12, "bold"))
        self.mem_label.grid(row=0, column=1, padx=10, pady=2, sticky="w")
        self.proc_count_label = ttk.Label(info_frame, text="Процессов: 0", font=("Consolas", 10))
        self.proc_count_label.grid(row=0, column=2, padx=10, pady=2, sticky="e")
        info_frame.columnconfigure(2, weight=1)

        mode_frame = ttk.Frame(info_frame)
        mode_frame.grid(row=1, column=0, columnspan=3, pady=2, sticky="ew")
        self.mode_label = tk.Label(mode_frame, text="⚡ Активный", font=("Consolas", 9, "bold"),
                                   fg="#2ecc71", bg="#0f0f1a")
        self.mode_label.pack(side=tk.LEFT, padx=5)
        self.manual_var = tk.IntVar(value=0)
        self.manual_check = ttk.Checkbutton(mode_frame, text="Ручной режим", variable=self.manual_var,
                                            command=self.toggle_manual_mode)
        self.manual_check.pack(side=tk.RIGHT, padx=5)

        charts_frame = ttk.Frame(main_frame)
        charts_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.cpu_chart = HistoryChart(charts_frame, width=500, height=130, title="Загрузка CPU (%)", color="#3498db")
        self.cpu_chart.canvas.pack(side=tk.TOP, fill=tk.X, pady=2)

        self.mem_chart = HistoryChart(charts_frame, width=500, height=130, title="Использование памяти (%)", color="#2ecc71")
        self.mem_chart.canvas.pack(side=tk.TOP, fill=tk.X, pady=2)

        proc_frame = ttk.Frame(main_frame, relief=tk.RIDGE, borderwidth=2, padding=5)
        proc_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        ttk.Label(proc_frame, text="Dev-процессы (можно завершить)", font=("Consolas", 10, "bold")).pack(anchor="w")

        tree_container = ttk.Frame(proc_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_container, columns=("pid", "name", "mem", "cpu", "action"),
                                 show="headings", height=10)
        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="Имя процесса")
        self.tree.heading("mem", text="RAM (MB)")
        self.tree.heading("cpu", text="CPU %")
        self.tree.heading("action", text="")
        self.tree.column("pid", width=60, anchor="center")
        self.tree.column("name", width=150)
        self.tree.column("mem", width=80, anchor="center")
        self.tree.column("cpu", width=80, anchor="center")
        self.tree.column("action", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill="y")

        self.kill_buttons = []

    def toggle_manual_mode(self):
        self.manual_mode = bool(self.manual_var.get())

    def on_minimize(self, event):
        if not self.manual_mode:
            self.set_mode(False)

    def on_restore(self, event):
        if not self.manual_mode:
            self.set_mode(True)

    def set_mode(self, active: bool):
        if self.active_mode == active:
            return
        self.active_mode = active
        if active:
            self.mode_label.config(text="⚡ Активный", fg="#2ecc71")
            self.update_interval = self.active_interval
        else:
            self.mode_label.config(text="💤 Легкий", fg="#f39c12")
            self.update_interval = self.idle_interval

    def check_active_state(self):
        if not self.manual_mode:
            if self.root.state() == 'iconic':
                self.set_mode(False)
            else:
                self.set_mode(True)
        self.root.after(5000, self.check_active_state)

    def update_data(self):
        try:
            cpu_total = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            self.cpu_label.config(text=f"CPU: {cpu_total:.0f}%")
            self.mem_label.config(text=f"RAM: {mem.percent:.0f}%")
            self.proc_count_label.config(text=f"Процессов: {len(list(psutil.process_iter()))}")

            self.cpu_chart.add_point(cpu_total)
            self.mem_chart.add_point(mem.percent)

            self.refresh_process_table()
        except Exception as e:
            print(e)

        self.root.after(self.update_interval, self.update_data)

    def refresh_process_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for btn in self.kill_buttons:
            btn.destroy()
        self.kill_buttons.clear()

        dev_names = {'node.exe', 'python.exe', 'java.exe', 'code.exe', 'powershell.exe', 'cmd.exe'}
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                name = proc.info['name'].lower()
                if name in dev_names:
                    pid = proc.info['pid']
                    mem_mb = proc.info['memory_info'].rss / 1024 / 1024
                    cpu = proc.info['cpu_percent'] or 0
                    row_id = self.tree.insert("", "end", values=(pid, proc.info['name'],
                                                                 f"{mem_mb:.0f}", f"{cpu:.0f}", ""))
                    kill_btn = ttk.Button(self.tree, text="Kill", command=lambda p=pid: self.kill_process(p))
                    self.root.after_idle(lambda r=row_id, b=kill_btn: self._place_button(r, b))
            except:
                continue

    def _place_button(self, row_id, button):
        try:
            self.tree.window_create(row_id, column="action", window=button)
            self.kill_buttons.append(button)
        except:
            pass

    def kill_process(self, pid):
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            if messagebox.askyesno("Подтверждение", f"Завершить процесс {name} (PID {pid})?"):
                proc.terminate()
                self.root.after(1000, self.refresh_process_table)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось завершить процесс: {e}")

    def on_close(self):
        self.root.destroy()

if __name__ == "__main__":
    DevCleanerHUD()