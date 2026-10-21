"""Single-file Windows UI for the read-only OCS question bank."""
import json
import queue
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

from bank_server import Bank, DEFAULT_PORT, SERVICE, make_server, ocs_config, probe

BG = "#F2F5F3"
INK = "#193E35"
MUTED = "#65776F"
GREEN = "#15785F"
LINE = "#DDE6E0"
WHITE = "#FFFFFF"
TITLE = "OCS 本地题库"


class ActivityBank(Bank):
    def __init__(self, path):
        super().__init__(path)
        self.lock = threading.Lock()
        self.requests = self.hits = 0
        self.latest = "等待 OCS 查询"

    def search(self, *args, **kwargs):
        result = super().search(*args, **kwargs)
        with self.lock:
            self.requests += 1
            self.hits += bool(result["results"])
            self.latest = time.strftime("%H:%M:%S") + ("  找到答案" if result["results"] else "  未找到匹配题目")
        return result


class App:
    def __init__(self, root, port=DEFAULT_PORT):
        self.root, self.port = root, port
        self.bank = ActivityBank(Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "seed.json")
        self.server = self.thread = None
        self.state = "stopped"
        self.busy = False
        self.closed = False
        self.messages = queue.Queue()
        self.notice_timer = None
        root.title(TITLE)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Address.TEntry", fieldbackground="#F5F8F6", bordercolor=LINE,
                        lightcolor=LINE, darkcolor=LINE, padding=9)
        style.map("Address.TEntry", fieldbackground=[("readonly", "#F5F8F6")])
        self.icon = tk.PhotoImage(width=32, height=32)
        self.icon.put(GREEN, to=(0, 0, 32, 32))
        for y in (9, 15, 21):
            self.icon.put(WHITE, to=(8, y, 24, y + 2))
        root.iconphoto(True, self.icon)
        self.build()
        root.update_idletasks()
        width = max(780, root.winfo_reqwidth())
        height = max(640, root.winfo_reqheight())
        root.geometry(f"{width}x{height}")
        root.minsize(width, height)
        root.after(80, self.drain)
        root.after(200, self.start)

    def label(self, parent, text, size=10, color=INK, bold=False, bg=WHITE, **kw):
        return tk.Label(parent, text=text, font=("Microsoft YaHei UI", size, "bold" if bold else "normal"),
                        bg=bg, fg=color, anchor="w", **kw)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, cursor="hand2", relief="flat",
                         bd=0, padx=22, pady=11, bg=GREEN if primary else "#EAF1ED",
                         fg=WHITE if primary else INK, activebackground="#10634F" if primary else "#DDE9E2",
                         activeforeground=WHITE if primary else INK, disabledforeground="#97A69E",
                         font=("Microsoft YaHei UI", 11, "bold"), takefocus=True,
                         highlightthickness=1, highlightbackground=GREEN if primary else LINE,
                         highlightcolor="#389B7F")

    def build(self):
        header = tk.Frame(self.root, bg=INK, padx=30, pady=24)
        header.pack(fill="x")
        self.label(header, "OCS  /  LOCAL QUESTION BANK", 9, "#A8C7B8", bg=INK).pack(anchor="w")
        row = tk.Frame(header, bg=INK)
        row.pack(fill="x", pady=(5, 0))
        self.label(row, TITLE, 25, WHITE, True, bg=INK).pack(side="left")
        self.label(row, "v1.1  ·  单文件版", 10, "#BED4C8", bg=INK).pack(side="right")
        self.label(header, "工程伦理（玉泉路）  ·  打开即用，供 OCS 本地查询", 10, "#C9DDD2", bg=INK).pack(anchor="w", pady=(8, 0))
        main = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        main.pack(fill="both", expand=True)
        card = tk.Frame(main, bg=WHITE, padx=24, pady=20, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x")
        status_row = tk.Frame(card, bg=WHITE)
        status_row.pack(fill="x")
        self.dot = tk.Canvas(status_row, width=20, height=26, bg=WHITE, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.dot_item = self.dot.create_oval(4, 8, 16, 20, fill="#A8B7AE", outline="")
        self.status_label = self.label(status_row, "正在准备题库…", 17, INK, True)
        self.status_label.pack(side="left")
        self.status_note = self.label(card, "", 10, MUTED, wraplength=660)
        self.status_note.pack(fill="x", pady=(8, 16))
        tk.Frame(card, bg=LINE, height=1).pack(fill="x")
        facts = tk.Frame(card, bg=WHITE)
        facts.pack(fill="x", pady=(15, 2))
        for i, (number, caption) in enumerate(((str(len(self.bank.questions)), "道内置题目"),
                     (str(len({q.get('chapter') for q in self.bank.questions})), "个章节测验"), ("本机", "数据仅供本机查询"))):
            cell = tk.Frame(facts, bg=WHITE)
            cell.grid(row=0, column=i, sticky="ew")
            facts.grid_columnconfigure(i, weight=1)
            self.label(cell, number, 22, GREEN, True).pack(anchor="w")
            self.label(cell, caption, 10, MUTED).pack(anchor="w", pady=(2, 0))
        address_row = tk.Frame(main, bg=BG)
        address_row.pack(fill="x", pady=(18, 7))
        self.label(address_row, "OCS 查询地址", 10, MUTED, bg=BG).pack(side="left")
        self.label(address_row, "沿用现有配置即可", 10, MUTED, bg=BG).pack(side="right")
        self.address = tk.StringVar(value=f"http://127.0.0.1:{self.port}/search")
        ttk.Entry(main, textvariable=self.address, state="readonly", style="Address.TEntry",
                  font=("Consolas", 12)).pack(fill="x")
        actions = tk.Frame(main, bg=BG)
        actions.pack(fill="x", pady=(17, 0))
        self.toggle = self.button(actions, "启动服务", self.toggle_service, True)
        self.toggle.pack(side="left")
        self.button(actions, "复制 OCS 配置", self.copy_config).pack(side="left", padx=12)
        self.check_button = self.button(actions, "检测连接", self.check_connection)
        self.check_button.pack(side="left")
        self.notice = self.label(main, "", 10, GREEN, bg=BG, wraplength=680)
        self.notice.pack(fill="x", pady=(10, 10))
        help_box = tk.Frame(main, bg="#E7EFEB", padx=18, pady=14)
        help_box.pack(fill="x")
        self.label(help_box, "第一次使用？", 11, INK, True, bg="#E7EFEB").pack(anchor="w")
        self.label(help_box, "复制配置 → OCS「通用 / 全局设置 / 题库配置」→ 加入并保存。", 10,
                   MUTED, bg="#E7EFEB").pack(anchor="w", pady=(5, 0))
        self.label(help_box, "已有其他题库时保留原配置；本机已配置过则无需重复添加。", 10,
                   MUTED, bg="#E7EFEB").pack(anchor="w", pady=(3, 0))
        bottom = tk.Frame(main, bg=BG)
        bottom.pack(fill="x", pady=(14, 0))
        self.activity = self.label(bottom, "等待 OCS 查询", 9, MUTED, bg=BG)
        self.activity.pack(side="left")
        tk.Button(bottom, text="查看配置与帮助", command=self.show_help, relief="flat", bd=0,
                  bg=BG, fg=GREEN, cursor="hand2").pack(side="right")
        self.label(main, "可以最小化继续运行；关闭窗口将停止本窗口启动的服务。", 9, MUTED,
                   bg=BG).pack(anchor="w", pady=(8, 0))

    def announce(self, text, error=False):
        self.notice.configure(text=text, fg="#A34D22" if error else GREEN)

    def change_state(self, state, detail=""):
        self.state = state
        title, note, color, action = {
            "running": ("服务运行中", "OCS 现在可以读取题库。使用时保持本窗口开启或最小化。", GREEN, "停止服务"),
            "stopped": ("服务已停止", "点击启动服务后，OCS 即可继续查询。", "#84958A", "启动服务"),
            "starting": ("正在启动…", "正在加载内置题库并准备查询接口。", "#C58A31", "正在启动…"),
            "stopping": ("正在停止…", "正在释放查询端口，请稍候。", "#C58A31", "正在停止…"),
            "external": ("已有题库服务运行", "此窗口未启动服务。请关闭原服务后点击重试；不会强制结束其他程序。", "#BD812D", "重试启动"),
            "error": ("服务未能启动", detail, "#B95532", "重试启动"),
        }[state]
        self.status_label.configure(text=title)
        self.status_note.configure(text=note)
        self.dot.itemconfigure(self.dot_item, fill=color)
        self.toggle.configure(text=action, state="disabled" if self.busy else "normal")
        self.check_button.configure(state="normal" if state in {"running", "external"} else "disabled")

    def background(self, work, callback):
        def run():
            try:
                result = work()
            except Exception as exc:
                result = exc
            self.messages.put((callback, result))
        threading.Thread(target=run, daemon=True).start()

    def drain(self):
        if self.closed:
            return
        while not self.messages.empty():
            callback, result = self.messages.get_nowait()
            callback(result)
            if self.closed:
                return
        with self.bank.lock:
            self.activity.configure(text=f"查询 {self.bank.requests} 次  ·  命中 {self.bank.hits} 次  |  {self.bank.latest}")
        if self.state == "running" and self.thread and not self.thread.is_alive():
            self.server.server_close()
            self.server = self.thread = None
            self.change_state("error", "服务意外结束，请点击重试启动。")
        self.root.after(150, self.drain)

    def start(self):
        if self.busy or self.server:
            return
        self.busy = True
        self.change_state("starting")
        def work():
            try:
                server = make_server(self.bank, self.port)
            except OSError as exc:
                if probe(self.port).get("service") == SERVICE:
                    return "external"
                raise RuntimeError(f"端口 {self.port} 被占用或不可用。请关闭占用程序后重试。") from exc
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.15}, daemon=True)
            thread.start()
            return server, thread
        def done(result):
            self.busy = False
            if isinstance(result, Exception):
                self.change_state("error", str(result))
            elif result == "external":
                self.change_state("external")
            else:
                self.server, self.thread = result
                self.change_state("running")
                self.announce("已就绪，无需额外的题库文件或 Python 环境。")
        self.background(work, done)

    def stop(self, close=False):
        if self.busy:
            return
        if not self.server:
            if close:
                self.closed = True
                self.root.destroy()
            return
        self.busy = True
        self.change_state("stopping")
        server = self.server
        def work():
            server.shutdown()
            server.server_close()
        def done(result):
            self.busy = False
            if isinstance(result, Exception):
                self.change_state("error", str(result))
                return
            self.server = self.thread = None
            if close:
                self.closed = True
                self.root.destroy()
            else:
                self.change_state("stopped")
                self.announce("服务已停止，可以随时再次启动。")
        self.background(work, done)

    def toggle_service(self):
        if self.server:
            self.stop()
        else:
            self.start()

    def copy_config(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(ocs_config(self.port), ensure_ascii=False, indent=2))
        self.announce("配置已复制。在 OCS 题库配置中加入并保存即可。")

    def check_connection(self):
        if self.state not in {"running", "external"}:
            return
        self.check_button.configure(state="disabled")
        self.announce("正在通过本地 HTTP 接口检查连接和答案返回…")
        def work():
            opener = build_opener(ProxyHandler({}))
            q = next(q for q in self.bank.questions if q["id"] == "53546")
            with opener.open(f"http://127.0.0.1:{self.port}/health", timeout=3) as response:
                health = json.load(response)
            if health.get("service") != SERVICE:
                raise ValueError("此端口运行的不是本题库服务。")
            params = urlencode({"title": q["question"], "type": q["type"]})
            with opener.open(f"http://127.0.0.1:{self.port}/search?{params}", timeout=3) as response:
                result = json.load(response)
            if not any(r["id"] == q["id"] and r["answer"] == q["answer"] for r in result["results"]):
                raise ValueError("接口已连接，但测试题的答案不匹配。")
            return f"连接正常：{health['questions']} 道题可读取，测试答案“义务”返回正确。"
        def done(result):
            if self.state in {"running", "external"}:
                self.check_button.configure(state="normal")
                self.announce(str(result) if not isinstance(result, Exception) else f"检测失败：{result}",
                              isinstance(result, Exception))
        self.background(work, done)

    def show_help(self):
        win = tk.Toplevel(self.root)
        win.title("OCS 配置与使用方法")
        win.configure(bg=BG)
        win.transient(self.root)
        win.geometry("700x580")
        body = tk.Frame(win, bg=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        self.label(body, "把题库接入 OCS", 18, INK, True, bg=BG).pack(anchor="w")
        self.label(body, "1. 保持主窗口显示“服务运行中”。\n2. 点击下方按钮复制配置。\n3. 在 OCS 题库配置中加入；已有题库请保留原配置。", 10,
                   MUTED, bg=BG, justify="left").pack(anchor="w", pady=12)
        text = tk.Text(body, wrap="word", height=14, font=("Consolas", 10), bg=WHITE,
                       fg=INK, relief="flat", padx=12, pady=12)
        text.insert("1.0", json.dumps(ocs_config(self.port), ensure_ascii=False, indent=2))
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(16, 0))
        self.button(row, "复制配置", lambda: (self.copy_config(), feedback.configure(text="已复制到剪贴板")), True).pack(side="left")
        feedback = self.label(row, "", 10, GREEN, bg=BG)
        feedback.pack(side="left", padx=15)
        self.button(row, "关闭", win.destroy).pack(side="right")
        win.update_idletasks()
        width, height = max(700, win.winfo_reqwidth()), max(620, win.winfo_reqheight())
        win.minsize(width, height)
        x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2)
        y = max(0, self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.grab_set()

    def close(self):
        if self.busy:
            self.announce("正在处理服务操作，请稍候再关闭。")
            return
        if self.server:
            if messagebox.askyesno("退出题库服务？", "退出后 OCS 将无法查询这份本地题库。\n\n需要继续使用时，可以最小化本窗口。\n确定停止服务并退出吗？", parent=self.root):
                self.stop(close=True)
        else:
            self.closed = True
            self.root.destroy()


def main():
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    try:
        App(root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror("题库无法加载", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
