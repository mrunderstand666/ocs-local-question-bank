"""Portable, read-only OCS bank server. Runtime dependencies: Python stdlib."""
import argparse
import json
import re
import socket
import sys
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, build_opener

VERSION = "1.1.0"
SERVICE = "ucas-ethics-personal-bank"
DEFAULT_PORT = 18651


def normalize(value):
    value = unicodedata.normalize("NFKC", str(value))
    value = re.sub(r"^\s*[\[【](?:单选题|多选题|判断题|填空题)[\]】]\s*", "", value)
    value = re.sub(r"^\s*\d+[.、．]\s*", "", value)
    value = re.sub(r"\([\d.]+分\)\s*$", "", value)
    return "".join(c.lower() for c in value if c.isalnum())


def option_set(value):
    if str(value).strip() in {"", "undefined", "null", "${options}"}:
        return set()
    return {normalize(re.sub(r"^\s*[A-Z][.、．:：]\s*", "", line))
            for line in str(value).splitlines() if line.strip()}


class Bank:
    def __init__(self, path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self.questions = data["questions"]
        if not isinstance(self.questions, list) or not self.questions:
            raise ValueError("题库 questions 必须是非空数组。")
        self.index = {}
        ids = set()
        for q in self.questions:
            if (not isinstance(q, dict) or not isinstance(q.get("question"), str)
                    or not normalize(q["question"])
                    or not isinstance(q.get("answer"), str)
                    or q.get("type") not in {"single", "multiple", "judgement", "completion"}
                    or not isinstance(q.get("options"), list)):
                raise ValueError("题目缺少有效的 question、answer、type 或 options。")
            if not q.get("id") or q["id"] in ids:
                raise ValueError("题目 ID 为空或重复。")
            ids.add(q["id"])
            if any(not isinstance(o, dict) or not isinstance(o.get("text"), str)
                   for o in q["options"]):
                raise ValueError("选项必须包含 text 文本。")
            self.index.setdefault(normalize(q["question"]), []).append(q)
        self.queryable = sum(bool(q["answer"]) for q in self.questions)

    def search(self, title, qtype="", options=""):
        key = normalize(title)
        if not key:
            return {"code": 0, "msg": "请输入题干", "results": []}
        matches = self.index.get(key, [])
        if qtype in {"single", "multiple", "judgement", "completion"}:
            matches = [q for q in matches if q["type"] == qtype]
        supplied = option_set(options)
        if supplied:
            matches = [q for q in matches if not q["options"] or
                       {normalize(o["text"]) for o in q["options"]} == supplied]
        if len(matches) > 1:
            signatures = {(q["type"], tuple(sorted(normalize(o["text"]) for o in q["options"])),
                           q["answer"]) for q in matches}
            if len(signatures) > 1:
                return {"code": 0, "msg": "题干存在歧义，请同时提供题型及全部选项", "results": []}
        results = [{"id": q["id"], "question": q["question"], "answer": q["answer"],
                    "chapter": q.get("chapter", ""),
                    "answer_source": q.get("answer_source", "")}
                   for q in matches if q["answer"]]
        return {"code": 1 if results else 0,
                "msg": "找到匹配答案" if results else "未找到匹配题目",
                "results": results}


def ocs_config(port=DEFAULT_PORT):
    return [{
        "name": "工程伦理（玉泉路）个人作答题库",
        "homepage": f"http://127.0.0.1:{port}/",
        "url": f"http://127.0.0.1:{port}/search",
        "method": "get", "contentType": "json", "type": "GM_xmlhttpRequest",
        "data": {"title": "${title}", "type": "${type}", "options": "${options}"},
        "handler": "return (res) => res.code === 1 ? res.results.map(r => [r.question, r.answer]) : undefined",
    }]


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        # On Windows, never share a listening port with another service.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(bank, port):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OCSLocalBank/" + VERSION
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, fmt, *args):
            pass

        def reply(self, body, status=200, head=False):
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head:
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def handle_read(self, head=False):
            if self.headers.get("Host", "").split(":")[0] not in {"127.0.0.1", "localhost"}:
                self.reply({"code": 0, "msg": "Invalid host"}, 403, head)
                return
            if len(self.path) > 32000:
                self.reply({"code": 0, "msg": "题目过长"}, 414, head)
                return
            req = urlsplit(self.path)
            args = parse_qs(req.query, max_num_fields=20)
            if req.path in {"/", "/index.html", "/health"}:
                self.reply({"status": "ok", "service": SERVICE, "version": VERSION,
                            "questions": len(bank.questions), "queryable": bank.queryable}, head=head)
            elif req.path == "/search":
                self.reply(bank.search(args.get("title", [""])[0],
                                       args.get("type", [""])[0],
                                       args.get("options", [""])[0]), head=head)
            elif req.path == "/ocs-config":
                self.reply(ocs_config(self.server.server_port), head=head)
            else:
                self.reply({"code": 0, "msg": "Not found"}, 404, head)

        def do_GET(self):
            try:
                self.handle_read()
            except ValueError:
                self.reply({"code": 0, "msg": "无效请求"}, 400)

        def do_HEAD(self):
            try:
                self.handle_read(head=True)
            except ValueError:
                self.reply({"code": 0, "msg": "无效请求"}, 400, True)

    return Server(("127.0.0.1", port), Handler)


def resolve_bank(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    folder = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent.parent
    external = folder / "题库.json"
    if external.exists():
        return external
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "seed.json"


def probe(port):
    try:
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/health", timeout=1) as r:
            return json.load(r)
    except (URLError, ValueError, OSError):
        return {}


def pause_on_error():
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\n按回车关闭此窗口。")
        except (EOFError, KeyboardInterrupt):
            pass


def windows_stop_event(port, open_existing=False):
    """A session-local stop signal, without exposing a network write endpoint."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = f"Local\\OCSLocalBank_1_Stop_{port}"
    handle = (kernel.OpenEventW(2, False, name) if open_existing
              else kernel.CreateEventW(None, False, False, name))
    if not open_existing and not handle:
        raise OSError(ctypes.get_last_error(), "无法创建服务停止信号")
    return kernel, handle


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="OCS 本地题库服务")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--bank", help="指定题库 JSON 文件")
    parser.add_argument("--check", action="store_true", help="验证题库并退出")
    parser.add_argument("--stop", action="store_true", help="停止本软件启动的服务")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须为 1 至 65535。")
    if args.stop:
        if sys.platform != "win32":
            print("此选项仅用于 Windows，请按 Ctrl+C 停止服务。", flush=True)
            return 1
        kernel, handle = windows_stop_event(args.port, open_existing=True)
        if not handle:
            print("本软件没有正在运行的服务。", flush=True)
            return 0
        try:
            kernel.SetEvent(handle)
        finally:
            kernel.CloseHandle(handle)
        print("已发送停止请求。", flush=True)
        return 0
    try:
        bank = Bank(resolve_bank(args.bank))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"题库加载失败：{exc}", flush=True)
        pause_on_error()
        return 1
    if args.check:
        print(json.dumps({"status": "ok", "questions": len(bank.questions),
                          "queryable": bank.queryable}, ensure_ascii=False), flush=True)
        return 0
    try:
        server = make_server(bank, args.port)
    except OSError as exc:
        existing = probe(args.port)
        if existing.get("service") == SERVICE:
            print(f"题库服务已在运行，端口 {args.port}，{existing.get('questions')} 道题。\n"
                  "请保留先前启动的服务窗口，本次没有另开服务。", flush=True)
            pause_on_error()
            return 0
        print(f"无法启动：端口 {args.port} 不可用。\n{exc}\n"
              "请关闭占用该端口的程序，或通过 --port 指定其他端口并同步修改 OCS 配置。", flush=True)
        pause_on_error()
        return 2
    stop_kernel = stop_handle = None
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("OCS 本地题库服务 · 运行中")
        try:
            stop_kernel, stop_handle = windows_stop_event(args.port)
        except OSError:
            server.server_close()
            raise
    print(f"OCS 本地题库服务  v{VERSION}\n"
          f"{'=' * 48}\n"
          f"运行中  |  {len(bank.questions)} 道题  |  {bank.queryable} 道可查询\n"
          f"OCS 接口：http://127.0.0.1:{args.port}/search\n"
          f"状态检查：http://127.0.0.1:{args.port}/health\n"
          f"题库文件：{bank.path}\n\n"
          "现有 OCS 配置可继续使用。\n"
          "请保持此窗口开启。关闭窗口、按 Ctrl+C 或运行“停止题库.cmd”可停止服务。\n"
          "重启电脑后再次双击程序即可。\n"
          f"{'=' * 48}", flush=True)
    try:
        if stop_handle:
            server.timeout = 0.2
            while stop_kernel.WaitForSingleObject(stop_handle, 0) != 0:
                server.handle_request()
        else:
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\n服务已停止。", flush=True)
    finally:
        server.server_close()
        if stop_handle:
            stop_kernel.CloseHandle(stop_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
