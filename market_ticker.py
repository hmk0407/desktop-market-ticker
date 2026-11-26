# -*- coding: utf-8 -*-
"""
Desktop Market Ticker - 桌面右对齐单列行情看板
================================================
5 类资产（上证指数 / 恒生指数 / 纳斯达克 / 美元人民币 / BTC）竖排常驻桌面，
无边框、半透明、置顶、可鼠标穿透，红涨绿跌，每行带迷你走势图。

零第三方依赖：仅使用 Python 3 标准库 + Windows 原生 API（ctypes 调用 user32/gdi32）。
运行：python market_ticker.py
自检：python market_ticker.py --test   （只抓数据打印，不打开窗口）
"""

import ctypes
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
APP_NAME = "DesktopMarketTicker"
CONFIG_FILE = "config.json"
HEADER_H = 10   # 顶部留白（标题栏已去掉）
FOOTER_H = 10   # 底部留白


def app_dir():
    """ exe 打包后用 sys.executable 所在目录；源码运行用脚本所在目录。 """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG = {
    "rows": [
        {"label": "上证指数",   "feed": "eastmoney", "secid": "1.000001",   "kline": "1.000001"},
        {"label": "恒生指数",   "feed": "eastmoney", "secid": "100.HSI",    "kline": "100.HSI"},
        {"label": "纳斯达克",   "feed": "eastmoney", "secid": "100.NDX",    "kline": "100.NDX"},
        {"label": "美元/人民币", "feed": "eastmoney", "secid": "133.USDCNH", "kline": "133.USDCNH"},
        {"label": "BTC/USDT",   "feed": "gateio",    "pair": "BTC_USDT"}
    ],
    "refresh_seconds": 10,
    "opacity": 220,                 # 0-255，越小越透明
    "margin_right": 16,
    "position": "right-center",     # right-top / right-center / right-bottom
    "width": 330,
    "row_height": 78,
    "font": "Microsoft YaHei",      # Win10/11 自带；也可换成 SimHei
    "font_size": 13,
    "mouse_penetrable": False,      # True = 鼠标穿透（点不到窗口，老板键切换）
    "snap_edge": 12,               # 拖动/拉伸时吸附屏幕边缘的像素阈值
    "remember_size": True,         # 记忆拉伸后的尺寸与位置，重启恢复
    "saved": {                     # 由程序自动写入，勿手动改
        "width": 0, "height": 0, "x": -1, "y": -1
    },
    "colors": {
        "card": "1E222D",           # 卡片底色
        "border": "3A4152",
        "text": "E6E9EF",
        "muted": "9AA0AA",
        "up": "FF4D4F",             # 红涨
        "down": "00B578",           # 绿跌
        "flat": "9AA0AA",
        "grid": "2A3040"
    }
}

# ---------------------------------------------------------------------------
# Win32 类型与函数声明
# 说明：只用 ctypes 内置类型自建 Win32 类型，不依赖 ctypes.wintypes
#       （部分精简版 Python 的 wintypes 不完整）
# ---------------------------------------------------------------------------
class _WinTypes:
    """轻量命名空间，等价于常用 wintypes。"""
    BYTE = ctypes.c_byte
    BOOL = ctypes.c_int
    DWORD = ctypes.c_ulong
    UINT = ctypes.c_uint
    INT = ctypes.c_int
    LONG = ctypes.c_long
    LPVOID = ctypes.c_void_p
    HANDLE = ctypes.c_void_p
    HWND = ctypes.c_void_p
    HDC = ctypes.c_void_p
    HMENU = ctypes.c_void_p
    HICON = ctypes.c_void_p
    HCURSOR = ctypes.c_void_p
    HBRUSH = ctypes.c_void_p
    HFONT = ctypes.c_void_p
    HPEN = ctypes.c_void_p
    HINSTANCE = ctypes.c_void_p
    HGDIOBJ = ctypes.c_void_p
    ATOM = ctypes.c_ushort
    COLORREF = ctypes.c_ulong
    WPARAM = ctypes.c_size_t
    LPARAM = ctypes.c_ssize_t
    LPCWSTR = ctypes.c_wchar_p
    UINT_PTR = ctypes.c_size_t

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


w = _WinTypes()


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_ulong), ("pt", w.POINT),
                ("lPrivate", ctypes.c_ulong)]

w.MSG = MSG

WM_CREATE, WM_DESTROY, WM_PAINT, WM_TIMER, WM_CLOSE = 0x0001, 0x0002, 0x000F, 0x0113, 0x0010
WM_SIZE, WM_NCHITTEST, WM_GETMINMAXINFO = 0x0005, 0x0084, 0x0024
WM_EXITSIZEMOVE = 0x0232
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE, WM_RBUTTONUP = 0x0201, 0x0202, 0x0200, 0x0205
WM_COMMAND, WM_HOTKEY, WM_APP_REFRESH = 0x0111, 0x0312, 0x8001
WM_APP_TOGGLE_PEN, WM_APP_TOGGLE_VIS, WM_APP_RESET_SIZE = 0x8002, 0x8003, 0x8004

# 命中测试返回值（用于边缘拖拽拉伸）
HTCLIENT, HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 1, 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

WS_POPUP, WS_VISIBLE, WS_THICKFRAME = 0x80000000, 0x10000000, 0x00040000
WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT = 0x00080000, 0x00000008, 0x00000080, 0x00000020
LWA_COLORKEY, LWA_ALPHA = 0x00000001, 0x00000002
SM_CXSCREEN, SM_CYSCREEN = 0, 1
SPI_GETWORKAREA = 0x0030
MOD_CONTROL, MOD_ALT = 0x0002, 0x0001
VK_T, VK_H, VK_Q = 0x54, 0x48, 0x51
HOTKEY_PEN, HOTKEY_VIS, HOTKEY_QUIT = 1, 2, 3
ERROR_ALREADY_EXISTS = 183
IDM_REFRESH, IDM_PEN, IDM_HIDE, IDM_RESET_SIZE, IDM_EXIT = 1001, 1002, 1003, 1004, 1005
MF_STRING, MF_SEPARATOR = 0x00000000, 0x00000800
TRANSPARENT, DEFAULT_CHARSET = 1, 1
NULL_PEN = 8  # GetStockObject(NULL_PEN)
DT_LEFT, DT_RIGHT, DT_VCENTER, DT_SINGLELINE, DT_NOPREFIX = 0x00000000, 0x00000002, 0x00000004, 0x00000020, 0x00000800
COLORKEY = 0x00FF00FF  # 洋红作为透明键

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t  # 64位下 LRESULT 为有符号指针宽度
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HCURSOR),
        ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
        ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", w.HDC), ("fErase", w.BOOL), ("rcPaint", w.RECT),
        ("fRestore", w.BOOL), ("fIncUpdate", w.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", w.POINT), ("ptMaxSize", w.POINT),
        ("ptMaxPosition", w.POINT), ("ptMinTrackSize", w.POINT),
        ("ptMaxTrackSize", w.POINT),
    ]


def _rgb(hexstr):
    """'RRGGBB' -> COLORREF (0x00BBGGRR)"""
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = w.ATOM
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.CreateWindowExW.restype = w.HWND
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.SetLayeredWindowAttributes.argtypes = [w.HWND, w.COLORREF, w.BYTE, w.DWORD]
user32.SetLayeredWindowAttributes.restype = w.BOOL
user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = w.BOOL
kernel32.CreateMutexW.argtypes = [w.LPVOID, w.BOOL, w.LPCWSTR]
kernel32.CreateMutexW.restype = w.HANDLE
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.SetForegroundWindow.restype = w.BOOL
user32.SetTimer.argtypes = [w.HWND, w.UINT_PTR, w.UINT, w.LPVOID]
user32.SetTimer.restype = w.UINT_PTR
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.PostMessageW.restype = w.BOOL
user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, w.UINT_PTR, w.LPCWSTR]
user32.AppendMenuW.restype = w.BOOL
user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, w.HWND, w.LPVOID]
user32.TrackPopupMenu.restype = w.BOOL
user32.SystemParametersInfoW.argtypes = [w.UINT, w.UINT, w.LPVOID, w.UINT]
user32.SystemParametersInfoW.restype = w.BOOL

gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, w.BOOL, w.BOOL, w.BOOL, w.BYTE, w.BYTE,
                              w.BYTE, w.BYTE, w.BYTE, w.LPCWSTR]
gdi32.CreateFontW.restype = w.HFONT
gdi32.CreateSolidBrush.argtypes = [w.COLORREF]
gdi32.CreateSolidBrush.restype = w.HBRUSH
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, w.COLORREF]
gdi32.CreatePen.restype = w.HPEN
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = w.HGDIOBJ
gdi32.SetTextColor.argtypes = [w.HDC, w.COLORREF]
gdi32.SetTextColor.restype = w.COLORREF
user32.DrawTextW.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.POINTER(w.RECT), w.UINT]
user32.DrawTextW.restype = ctypes.c_int
gdi32.SetBkMode.argtypes = [w.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int
gdi32.Polyline.argtypes = [w.HDC, ctypes.POINTER(w.POINT), ctypes.c_int]
gdi32.Polyline.restype = w.BOOL
# 未声明 argtypes 时 ctypes 默认把指针按 32 位 int 传递，64 位下会截断崩溃，逐一补全
gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
gdi32.SelectObject.restype = w.HGDIOBJ
gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
gdi32.DeleteObject.restype = w.BOOL
gdi32.MoveToEx.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, w.LPVOID]
gdi32.MoveToEx.restype = w.BOOL
gdi32.LineTo.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]
gdi32.LineTo.restype = w.BOOL
gdi32.RoundRect.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.RoundRect.restype = w.BOOL
user32.FillRect.argtypes = [w.HDC, ctypes.POINTER(w.RECT), w.HBRUSH]
user32.FillRect.restype = ctypes.c_int
user32.BeginPaint.argtypes = [w.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = w.HDC
user32.EndPaint.argtypes = [w.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = w.BOOL
user32.InvalidateRect.argtypes = [w.HWND, w.LPVOID, w.BOOL]
user32.InvalidateRect.restype = w.BOOL
user32.MoveWindow.argtypes = [w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.BOOL]
user32.MoveWindow.restype = w.BOOL
user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user32.GetWindowRect.restype = w.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
user32.GetCursorPos.restype = w.BOOL
user32.SetCapture.argtypes = [w.HWND]
user32.SetCapture.restype = w.HWND
user32.ReleaseCapture.restype = w.BOOL
user32.CreatePopupMenu.restype = w.HMENU
user32.DestroyMenu.argtypes = [w.HMENU]
user32.DestroyMenu.restype = w.BOOL
user32.LoadCursorW.argtypes = [w.HINSTANCE, w.LPVOID]  # 第二参数可为 MAKEINTRESOURCE 整数
user32.LoadCursorW.restype = w.HCURSOR
user32.DestroyWindow.argtypes = [w.HWND]
user32.DestroyWindow.restype = w.BOOL
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user32.ShowWindow.restype = w.BOOL
user32.UpdateWindow.argtypes = [w.HWND]
user32.UpdateWindow.restype = w.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), w.HWND, w.UINT, w.UINT]
user32.GetMessageW.restype = w.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = w.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = w.LPARAM
user32.SetWindowLongW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
gdi32.CreateSolidBrush.restype = w.HBRUSH
gdi32.CreatePen.restype = w.HPEN


# ---------------------------------------------------------------------------
# 数据层
# ---------------------------------------------------------------------------
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36 Edg/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]
_ua_seq = [0]


def _headers():
    ua = _UA_POOL[_ua_seq[0] % len(_UA_POOL)]
    _ua_seq[0] += 1
    return {"User-Agent": ua,
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "*/*",
            "Connection": "close"}  # 每次短连接，避免复用被断


def http_get(url, encoding="utf-8", timeout=10, retries=4, referer=None):
    """带重试 + 轮换 UA 的 GET；对公开接口的瞬时断连/限流更稳。"""
    last = None
    for attempt in range(retries):
        try:
            hdrs = _headers()
            if referer:
                hdrs["Referer"] = referer
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode(encoding, errors="replace")
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1) + 0.1 * (_ua_seq[0] % 3))
    raise last


EM_REAL = ("https://push2.eastmoney.com/api/qt/stock/get?secid={secid}"
           "&fields=f43,f44,f45,f46,f58,f59,f60,f169,f170")
EM_KLINE = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}"
            "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55"
            "&klt=101&fqt=1&lmt=30&end=20500101")


# 新浪备用实时接口（东财限流时兜底）
SINA_REALTIME = {
    "1.000001": ("s_sh000001", 2),    # 上证指数: 名称,现价,涨跌额,涨跌幅,...
    "100.HSI": ("int_hangseng", 3),   # 恒生指数: 名称,现价,涨跌额,涨跌幅
    "100.NDX": ("int_nasdaq", 3),     # 纳斯达克
    "133.USDCNH": ("fx_susdcny", 1),  # 在岸人民币
}


def fetch_sina_fallback(secid):
    """新浪实时兜底，返回 (price, change, pct, digit)。"""
    code, _ = SINA_REALTIME[secid]
    raw = http_get("https://hq.sinajs.cn/list=" + code, encoding="gbk",
                   referer="https://finance.sina.com.cn")
    body = raw.split('"')[1]
    parts = body.split(",")
    if code == "fx_susdcny":
        # 时间,买,卖,高,...,名称,涨跌幅,涨跌额,...
        return float(parts[1]), float(parts[11]), float(parts[10]) / 100.0, 4
    # 指数: 名称,现价,涨跌额,涨跌幅
    return float(parts[1]), float(parts[2]), float(parts[3]) / 100.0, 2


def fetch_eastmoney(row):
    """东财实时 + 日K收盘序列；实时失败时自动切新浪兜底。"""
    import json as _json
    secid = row["secid"]
    digit, price, change, pct = 2, 0.0, 0.0, 0.0
    try:
        real = _json.loads(http_get(EM_REAL.format(secid=secid))).get("data")
        if not real:
            raise RuntimeError("no real data")
        digit = int(real.get("f59") or 2)
        scale = 10 ** digit
        price = float(real["f43"]) / scale
        change = float(real.get("f169") or 0) / scale
        pct = float(real.get("f170") or 0) / 10000.0  # 东财 f170 单位 0.01%
    except Exception:
        if secid in SINA_REALTIME:
            price, change, pct, digit = fetch_sina_fallback(secid)
        else:
            raise

    series = []
    try:
        time.sleep(0.15)  # 轻微间隔，降低公开接口限流概率
        kl = _json.loads(http_get(EM_KLINE.format(secid=row.get("kline") or secid))).get("data")
        if kl and kl.get("klines"):
            for line in kl["klines"]:
                parts = line.split(",")
                if len(parts) >= 3:
                    series.append(float(parts[2]))  # f53 收盘
    except Exception:
        pass  # 走势图拿不到不影响价格显示
    return {"price": price, "change": change, "pct": pct,
            "series": series[-30:], "digit": digit}


def fetch_gateio(row):
    """Gate.io 现货 BTC/USDT 行情 + 小时K收盘序列。"""
    import json as _json
    pair = row.get("pair", "BTC_USDT")
    ticker = _json.loads(http_get(
        "https://api.gateio.ws/api/v4/spot/tickers?currency_pair=" + urllib.parse.quote(pair)
    ))[0]
    price = float(ticker["last"])
    pct = float(ticker.get("change_percentage") or 0) / 100.0
    change = price - price / (1 + pct) if pct != -1 else 0.0
    series = []
    try:
        kl = _json.loads(http_get(
            "https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair="
            + urllib.parse.quote(pair) + "&interval=1h&limit=30"
        ))
        for item in kl:
            series.append(float(item[2]))  # close
    except Exception:
        pass
    return {"price": price, "change": change, "pct": pct, "series": series[-30:], "digit": 2}


FETCHERS = {"eastmoney": fetch_eastmoney, "gateio": fetch_gateio}


def fetch_all(rows, state):
    """后台线程：逐条抓取，结果写回共享 state，并通知窗口重绘。"""
    for i, row in enumerate(rows):
        try:
            data = FETCHERS[row["feed"]](row)
            data["ok"] = True
            data["time"] = time.strftime("%H:%M:%S")
        except Exception as exc:
            prev = state["items"][i]
            data = dict(prev) if prev else {
                "price": 0.0, "change": 0.0, "pct": 0.0, "series": [],
                "digit": 2, "ok": False, "time": "--:--:--"
            }
            data["ok"] = False
            data["error"] = f"{type(exc).__name__}: {exc}"
        state["items"][i] = data
    state["updated"] = time.strftime("%H:%M:%S")
    hwnd = state.get("hwnd")
    if hwnd:
        user32.PostMessageW(w.HWND(hwnd), WM_APP_REFRESH, 0, 0)


# ---------------------------------------------------------------------------
# 绘制层
# ---------------------------------------------------------------------------
class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        c = cfg["colors"]
        self.c_card = _rgb(c["card"])
        self.c_border = _rgb(c["border"])
        self.c_text = _rgb(c["text"])
        self.c_muted = _rgb(c["muted"])
        self.c_up = _rgb(c["up"])
        self.c_down = _rgb(c["down"])
        self.c_flat = _rgb(c["flat"])
        self.c_grid = _rgb(c["grid"])
        self.font_name = cfg["font"]
        self.base_size = cfg["font_size"]

    def _font(self, height, bold=False):
        return gdi32.CreateFontW(
            height, 0, 0, 0, 700 if bold else 400, 0, 0, 0,
            DEFAULT_CHARSET, 0, 0, 0, 0, self.font_name)

    def _text(self, hdc, text, x, y, wd, ht, color, size, bold=False, align=DT_LEFT):
        font = self._font(size, bold)
        old_font = gdi32.SelectObject(hdc, font)
        old_color = gdi32.SetTextColor(hdc, color)
        gdi32.SetBkMode(hdc, TRANSPARENT)
        rc = w.RECT(x, y, x + wd, y + ht)
        user32.DrawTextW(hdc, ctypes.c_wchar_p(text), -1, ctypes.byref(rc),
                        align | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)
        gdi32.SetTextColor(hdc, old_color)
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(font)

    def _line(self, hdc, x1, y1, x2, y2, color):
        pen = gdi32.CreatePen(0, 1, color)
        old = gdi32.SelectObject(hdc, pen)
        gdi32.MoveToEx(hdc, x1, y1, None)
        gdi32.LineTo(hdc, x2, y2)
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(pen)

    def _sparkline(self, hdc, series, x, y, wd, ht, color, pen_w=2):
        if len(series) < 2 or wd <= 4 or ht <= 6:
            return
        lo, hi = min(series), max(series)
        span = (hi - lo) or 1.0
        pts = (w.POINT * len(series))()
        for i, v in enumerate(series):
            pts[i].x = int(x + (wd - 2) * i / (len(series) - 1)) + 1
            pts[i].y = int(y + ht - 3 - (ht - 6) * (v - lo) / span)
        pen = gdi32.CreatePen(0, max(1, pen_w), color)
        old = gdi32.SelectObject(hdc, pen)
        gdi32.Polyline(hdc, pts, len(series))
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(pen)

    def draw(self, hdc, state, width, height):
        rows = state["cfg"]["rows"]
        items = state["items"]

        # 基准布局（config 中的默认值）→ 当前窗口尺寸的比例，实现拉伸自动缩放
        base_w = self.cfg["width"]
        base_rh = self.cfg["row_height"]
        base_h = HEADER_H + len(rows) * base_rh + FOOTER_H
        sx = width / float(base_w) if base_w else 1.0
        sy = height / float(base_h) if base_h else 1.0
        sf = min(sx, sy)  # 字体/圆角/线宽统一比例，避免拉伸变形

        def fx(v):
            return int(round(v * sx))

        def fy(v):
            return int(round(v * sy))

        def fs(v):
            return max(7, int(round(v * sf)))

        # 1) 整窗填透明键（洋红会被 SetLayeredWindowAttributes 抠掉）
        bg = gdi32.CreateSolidBrush(COLORKEY)
        rc = w.RECT(0, 0, width, height)
        user32.FillRect(hdc, ctypes.byref(rc), bg)
        gdi32.DeleteObject(bg)

        # 2) 圆角卡片背景（无边框线）：用空画笔让 RoundRect 只填充不描边
        brush = gdi32.CreateSolidBrush(self.c_card)
        null_pen = gdi32.GetStockObject(NULL_PEN)
        old_brush = gdi32.SelectObject(hdc, brush)
        old_pen = gdi32.SelectObject(hdc, null_pen)
        rad = max(4, int(round(14 * sf)))
        gdi32.RoundRect(hdc, 1, 1, width - 1, height - 1, rad, rad)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.DeleteObject(brush)

        # 3) 数据行（无标题栏）
        rh = fy(base_rh)
        top = fy(HEADER_H)
        spark_x = fx(196)
        for i, row in enumerate(rows):
            item = items[i] if i < len(items) else {}
            y = top + i * rh
            if i > 0:
                self._line(hdc, fx(14), y, width - fx(14), y, self.c_grid)

            price = item.get("price") or 0.0
            chg = item.get("change") or 0.0
            pct = item.get("pct") or 0.0
            digit = item.get("digit", 2)
            ok = item.get("ok", False)

            color = self.c_up if pct > 0 else (self.c_down if pct < 0 else self.c_flat)
            sign = "+" if chg > 0 else ""
            price_s = f"{price:,.{digit}f}" if ok else "----"
            chg_s = f"{sign}{chg:,.{digit}f}  {sign}{pct * 100:+.2f}%" if ok else "获取失败"

            # 行内：名称 / 大号现价 / 涨跌，垂直方向在行高内均匀铺开
            self._text(hdc, row["label"], fx(16), y + fy(4), fx(150), fy(22),
                       self.c_text, fs(self.base_size), True)
            self._text(hdc, price_s, fx(16), y + fy(26), fx(170), fy(34),
                       self.c_text, fs(self.base_size + 9), True)
            self._text(hdc, chg_s, fx(16), y + fy(62), fx(180), fy(18),
                       color if ok else self.c_muted, fs(self.base_size))
            self._sparkline(hdc, item.get("series") or [], spark_x, y + fy(10),
                            width - spark_x - fx(14), rh - fy(20), color,
                            pen_w=max(1, int(round(2 * sf))))


# ---------------------------------------------------------------------------
# 窗口与主循环
# ---------------------------------------------------------------------------
class Widget:
    def __init__(self, cfg):
        self.cfg = cfg
        self.renderer = Renderer(cfg)
        self.hwnd = None
        self.rows = cfg["rows"]
        self.base_w = cfg["width"]
        self.row_h = cfg["row_height"]
        self.base_h = HEADER_H + len(self.rows) * self.row_h + FOOTER_H
        self.width = self.base_w
        self.height = self.base_h
        # 恢复上次保存的尺寸与位置
        self.saved_pos = None
        saved = cfg.get("saved") or {}
        if cfg.get("remember_size", True):
            sw = int(saved.get("width") or 0)
            sh = int(saved.get("height") or 0)
            sx, sy = int(saved.get("x", -1)), int(saved.get("y", -1))
            if sw >= self.base_w and sh >= self.base_h:
                self.width, self.height = sw, sh
            if sx >= 0 and sy >= 0:
                self.saved_pos = (sx, sy)
        self.penetrable = cfg["mouse_penetrable"]
        self.visible = True
        self.dragging = False
        self.drag_off = (0, 0)
        self.state = {
            "cfg": cfg,
            "items": [{} for _ in self.rows],
            "updated": None,
            "hwnd": None,
        }
        self._wndproc_ref = WNDPROC(self._wndproc)  # 防止被 GC

    def _screen_workarea(self):
        rc = w.RECT()
        ok = user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0)
        if not ok:
            rc = w.RECT(0, 0, user32.GetSystemMetrics(SM_CXSCREEN),
                        user32.GetSystemMetrics(SM_CYSCREEN))
        return rc

    def _position(self):
        rc = self._screen_workarea()
        if self.saved_pos:
            return self.saved_pos
        x = rc.right - self.width - self.cfg["margin_right"]
        pos = self.cfg["position"]
        if pos == "right-top":
            y = rc.top + 16
        elif pos == "right-bottom":
            y = rc.bottom - self.height - 16
        else:
            y = rc.top + (rc.bottom - rc.top - self.height) // 2
        return int(x), int(y)

    def _apply_layered(self):
        flags = LWA_COLORKEY | LWA_ALPHA
        user32.SetLayeredWindowAttributes(self.hwnd, COLORKEY,
                                          int(self.cfg["opacity"]), flags)
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        if self.penetrable:
            ex |= WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hwnd, -20, ex)  # GWL_EXSTYLE

    def create(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
        wc.lpszClassName = APP_NAME
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = kernel32.GetLastError()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(err)

        x, y = self._position()
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            APP_NAME, APP_NAME, WS_POPUP | WS_THICKFRAME,
            x, y, self.width, self.height, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(kernel32.GetLastError())

        self.state["hwnd"] = int(self.hwnd)
        self._apply_layered()
        user32.ShowWindow(self.hwnd, 5)  # SW_SHOW
        user32.UpdateWindow(self.hwnd)

        user32.RegisterHotKey(self.hwnd, HOTKEY_PEN, MOD_CONTROL | MOD_ALT, VK_T)
        user32.RegisterHotKey(self.hwnd, HOTKEY_VIS, MOD_CONTROL | MOD_ALT, VK_H)
        user32.RegisterHotKey(self.hwnd, HOTKEY_QUIT, MOD_CONTROL | MOD_ALT, VK_Q)
        user32.SetTimer(self.hwnd, 1, max(3, self.cfg["refresh_seconds"]) * 1000, None)
        self._spawn_fetch()

    def _spawn_fetch(self):
        t = threading.Thread(target=fetch_all, args=(self.rows, self.state), daemon=True)
        t.start()

    def _invalidate(self):
        user32.InvalidateRect(self.hwnd, None, True)

    def _reset_size(self):
        """恢复默认尺寸并重新贴回原位置，清除已保存的几何。"""
        self.width, self.height = self.base_w, self.base_h
        self.saved_pos = None
        rc = self._screen_workarea()
        x = rc.right - self.width - self.cfg["margin_right"]
        y = rc.top + (rc.bottom - rc.top - self.height) // 2
        user32.MoveWindow(self.hwnd, x, y, self.width, self.height, True)
        self._save_geometry()

    def _snap_to_edges(self):
        """拖动/拉伸结束后，若靠近屏幕边缘则吸附贴合。"""
        thr = int(self.cfg.get("snap_edge", 12))
        if thr <= 0:
            return
        wa = self._screen_workarea()
        rc = w.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rc)):
            return
        x, y, cw, ch = rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top
        # 左右吸附
        if abs(x - wa.left) <= thr:
            x = wa.left
        elif abs(rc.right - wa.right) <= thr:
            x = wa.right - cw
        # 上下吸附
        if abs(y - wa.top) <= thr:
            y = wa.top
        elif abs(rc.bottom - wa.bottom) <= thr:
            y = wa.bottom - ch
        if x != rc.left or y != rc.top:
            user32.MoveWindow(self.hwnd, x, y, cw, ch, True)

    def _save_geometry(self):
        """把当前窗口尺寸/位置写回 config.json，供下次启动恢复。"""
        if not self.cfg.get("remember_size", True):
            return
        rc = w.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rc)):
            return
        self.width = rc.right - rc.left
        self.height = rc.bottom - rc.top
        try:
            path = os.path.join(app_dir(), CONFIG_FILE)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["saved"] = {
                "width": int(self.width), "height": int(self.height),
                "x": int(rc.left), "y": int(rc.top),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 配置不可写时不影响运行

    def _popup_menu(self, x, y):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, IDM_REFRESH, "立即刷新")
        user32.AppendMenuW(menu, MF_STRING, IDM_PEN,
                           "取消鼠标穿透" if self.penetrable else "开启鼠标穿透")
        user32.AppendMenuW(menu, MF_STRING, IDM_HIDE, "隐藏窗口 (Ctrl+Alt+H)")
        user32.AppendMenuW(menu, MF_STRING, IDM_RESET_SIZE, "重置尺寸")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, IDM_EXIT, "退出 (Ctrl+Alt+Q)")
        user32.TrackPopupMenu(menu, 0x0100, x, y, 0, self.hwnd, None)  # TPM_LEFTALIGN
        user32.DestroyMenu(menu)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_CREATE:
                return 0

            elif msg == WM_PAINT:
                ps = PAINTSTRUCT()
                hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
                self.renderer.draw(hdc, self.state, self.width, self.height)
                user32.EndPaint(hwnd, ctypes.byref(ps))
                return 0

            elif msg == WM_SIZE:
                # lParam: 低位=宽，高位=高。拉伸时实时同步并重绘。
                new_w = lparam & 0xFFFF
                new_h = (lparam >> 16) & 0xFFFF
                if new_w > 0 and new_h > 0:
                    self.width, self.height = int(new_w), int(new_h)
                    self._invalidate()
                return 0

            elif msg == WM_GETMINMAXINFO:
                # 最小尺寸 = 默认尺寸，避免缩到看不清；最大不限制
                mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
                mmi.ptMinTrackSize.x = self.base_w
                mmi.ptMinTrackSize.y = self.base_h
                return 0

            elif msg == WM_NCHITTEST:
                # 边缘 8px 命中用于拉伸；其余按客户区处理（保留左键拖动逻辑）
                if self.penetrable:
                    return HTCLIENT
                pt = w.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                rc = w.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rc))
                edge = 8
                left = abs(pt.x - rc.left) <= edge
                right = abs(pt.x - rc.right) <= edge
                top = abs(pt.y - rc.top) <= edge
                bottom = abs(pt.y - rc.bottom) <= edge
                if top and left:
                    return HTTOPLEFT
                if top and right:
                    return HTTOPRIGHT
                if bottom and left:
                    return HTBOTTOMLEFT
                if bottom and right:
                    return HTBOTTOMRIGHT
                if left:
                    return HTLEFT
                if right:
                    return HTRIGHT
                if top:
                    return HTTOP
                if bottom:
                    return HTBOTTOM
                return HTCLIENT

            elif msg == WM_EXITSIZEMOVE:
                # 拖动/拉伸结束：边缘吸附 + 记住几何
                self._snap_to_edges()
                self._save_geometry()
                return 0

            elif msg == WM_APP_RESET_SIZE:
                self._reset_size()
                return 0

            elif msg == WM_TIMER:
                self._spawn_fetch()
                return 0

            elif msg == WM_APP_REFRESH:
                self._invalidate()
                return 0

            elif msg == WM_APP_TOGGLE_PEN:
                self.penetrable = not self.penetrable
                self._apply_layered()
                return 0

            elif msg == WM_APP_TOGGLE_VIS:
                self.visible = not self.visible
                user32.ShowWindow(hwnd, 5 if self.visible else 0)
                return 0

            elif msg == WM_HOTKEY:
                if wparam == HOTKEY_PEN:
                    user32.PostMessageW(hwnd, WM_APP_TOGGLE_PEN, 0, 0)
                elif wparam == HOTKEY_VIS:
                    user32.PostMessageW(hwnd, WM_APP_TOGGLE_VIS, 0, 0)
                elif wparam == HOTKEY_QUIT:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return 0

            elif msg == WM_LBUTTONDOWN:
                if not self.penetrable:
                    self.dragging = True
                    pt = w.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    rc = w.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rc))
                    self.drag_off = (pt.x - rc.left, pt.y - rc.top)
                    user32.SetCapture(hwnd)
                return 0

            elif msg == WM_MOUSEMOVE:
                if self.dragging and not self.penetrable:
                    pt = w.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    rc = w.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rc))
                    cw = rc.right - rc.left
                    ch = rc.bottom - rc.top
                    user32.MoveWindow(hwnd, pt.x - self.drag_off[0],
                                      pt.y - self.drag_off[1],
                                      cw, ch, True)
                return 0

            elif msg == WM_LBUTTONUP:
                if self.dragging:
                    self.dragging = False
                    user32.ReleaseCapture()
                return 0

            elif msg == WM_RBUTTONUP:
                if not self.penetrable:
                    pt = w.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    self._popup_menu(pt.x, pt.y)
                return 0

            elif msg == WM_COMMAND:
                cmd = wparam & 0xFFFF
                if cmd == IDM_REFRESH:
                    self._spawn_fetch()
                elif cmd == IDM_PEN:
                    user32.PostMessageW(hwnd, WM_APP_TOGGLE_PEN, 0, 0)
                elif cmd == IDM_HIDE:
                    user32.PostMessageW(hwnd, WM_APP_TOGGLE_VIS, 0, 0)
                elif cmd == IDM_RESET_SIZE:
                    user32.PostMessageW(hwnd, WM_APP_RESET_SIZE, 0, 0)
                elif cmd == IDM_EXIT:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return 0

            elif msg in (WM_CLOSE, WM_DESTROY):
                if msg == WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                else:
                    user32.PostQuitMessage(0)
                return 0

        except Exception as exc:
            # 绝不让异常跨过 ctypes 回调边界
            try:
                with open(os.path.join(app_dir(), "market_ticker_error.log"), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} msg={msg} {type(exc).__name__}: {exc}\n")
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        self.create()
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    path = os.path.join(app_dir(), CONFIG_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            for k, v in user_cfg.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as exc:
            print(f"[警告] 配置文件读取失败，使用默认配置：{exc}")
    return cfg


def self_test(cfg):
    print("== 数据源自检 ==")
    state = {"items": [{} for _ in cfg["rows"]], "updated": None, "hwnd": None, "cfg": cfg}
    fetch_all(cfg["rows"], state)
    for row, item in zip(cfg["rows"], state["items"]):
        flag = "OK " if item.get("ok") else "FAIL"
        print(f"[{flag}] {row['label']:<12} "
              f"{item.get('price', 0):>12,.{item.get('digit', 2)}f}  "
              f"{item.get('pct', 0) * 100:+.2f}%  "
              f"series={len(item.get('series') or [])}  "
              f"{item.get('error', '')}")


def main():
    cfg = load_config()
    if "--test" in sys.argv:
        self_test(cfg)
        return
    if sys.platform != "win32":
        print("本程序仅支持 Windows。")
        sys.exit(1)
    # 高 DPI 清晰度
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    # 单实例锁：重复启动不再产生多个窗口，而是把已有窗口显示/置前
    mutex = kernel32.CreateMutexW(None, True, "DesktopMarketTicker_SingleInstance")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        # 已有实例在运行：找到它的窗口并显示，然后本进程直接退出
        user32.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
        user32.FindWindowW.restype = w.HWND
        existing = user32.FindWindowW(APP_NAME, APP_NAME)
        if existing:
            user32.ShowWindow(existing, 5)  # SW_SHOW
            user32.SetForegroundWindow(existing)
        return

    Widget(cfg).run()


if __name__ == "__main__":
    main()
