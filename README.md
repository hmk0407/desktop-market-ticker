# Desktop Market Ticker

一个常驻 Windows 桌面右侧的单列行情看板：把 **A股上证指数、港股恒生指数、美股纳斯达克、美元/人民币汇率、BTC** 五类数据竖排显示在一个半透明、置顶、贴右边缘的小窗口里，每行带迷你走势图，红涨绿跌。

> 界面：桌面右侧一块圆角半透明面板，自上而下五列资产，每列含「名称 / 大号现价 / 涨跌额与涨跌幅 / 迷你走势图」。

## 特性

- **零第三方依赖**：只用 Python 3 标准库 + Windows 原生 API（ctypes 调 user32/gdi32），**不需要 pip install 任何东西**。
- **真正的桌面 widget**：无边框、半透明、始终置顶、默认贴屏幕右侧；不出现在任务栏、Alt+Tab 里。
- **5 类资产一列排开**：上证指数 / 恒生指数 / 纳斯达克 / 美元人民币 / BTC-USDT，可自由增删、换代码。
- **每行迷你走势图**：日K（BTC 为小时K）收盘价 sparkline，涨跌自动染色。
- **自动刷新 + 限流兜底**：默认 10 秒刷新；东财被限流时自动切新浪接口兜底，断网时保留上次数据。
- **老板键**：`Ctrl+Alt+H` 显示/隐藏窗口，`Ctrl+Alt+T` 切换鼠标穿透。
- **右键菜单**：立即刷新、切换鼠标穿透、隐藏、退出。
- **可拖动**：左键拖动窗口到任意位置（仍保持置顶）。

## 依赖与环境

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 7 及以上（推荐 Win10/11） |
| Python | **3.8+**，任意官方或便携版（本仓库在 3.13 验证） |
| 第三方库 | **无**。无需 pip install，无需 pyinstaller，无需 Visual Studio |
| 字体 | 使用系统自带的「Microsoft YaHei（微软雅黑）」，Win7+ 均有 |

> 如果你希望双击 `.py` 就能运行又不想装 Python，可以用 `pyinstaller` 自行打包成 exe（可选，非必需）；打包不是运行的前提。

## 运行

```powershell
python market_ticker.py
```

自检数据源（只抓数据打印，不开窗口）：

```powershell
python market_ticker.py --test
```

## 配置

首次运行会在脚本同目录读取 `config.json`（仓库已附一份）。常用项：

```json
{
  "refresh_seconds": 10,      // 刷新间隔（秒）
  "opacity": 220,             // 不透明度 0-255，越小越透
  "position": "right-center", // right-top / right-center / right-bottom
  "margin_right": 16,         // 距右边缘像素
  "mouse_penetrable": false,  // true = 鼠标完全穿透（点不到窗口）
  "rows": [ ... ]             // 5 行资产，可增删改
}
```

改标的：编辑 `rows`，`feed` 支持 `eastmoney`（A股/港股/美股/外汇指数，`secid` 为「市场.代码」）与 `gateio`（加密货币，`pair` 如 `BTC_USDT`）。

常用 secid 速查：
- 上证指数 `1.000001`，深证成指 `0.399001`，创业板指 `0.399006`
- 恒生指数 `100.HSI`，恒生科技 `100.HSTECH`
- 纳斯达克 `100.NDX`，道琼斯 `100.DJIA`，标普500 `100.SPX`
- 离岸人民币 `133.USDCNH`

## 数据源

| 资产 | 实时数据 | 走势图 |
|---|---|---|
| 上证 / 恒生 / 纳斯达克 / 汇率 | 东方财富 push2 接口，失败自动切新浪财经 | 东方财富日K |
| BTC | Gate.io 现货 ticker | Gate.io 小时K |

均为公开接口，可能有分钟级延迟或偶发限流，**仅供个人看盘参考，不构成投资建议**。

## 快捷键

| 按键 | 作用 |
|---|---|
| `Ctrl + Alt + H` | 显示 / 隐藏窗口 |
| `Ctrl + Alt + T` | 开启 / 关闭鼠标穿透 |
| 鼠标左键拖动 | 移动窗口位置 |
| 鼠标右键 | 打开菜单 |

## 文件说明

- `market_ticker.py` — 全部逻辑（数据 / 绘制 / 窗口），单文件即可运行
- `config.json` — 可编辑配置
- `README.md` — 本说明

## 推送到 GitHub

本地已初始化 Git 仓库并完成首次提交。要同步到自己的 GitHub：

1. 在 https://github.com/settings/tokens 生成一个 Personal Access Token（勾选 `repo` 权限）；
2. 双击 `push_to_github.bat`，按提示粘贴 token，脚本会自动创建远程仓库并推送；
3. 推送成功后按脚本提示清除 remote 中明文保存的 token。

也可手动执行：

```powershell
git remote add origin https://github.com/<你的用户名>/desktop-market-ticker.git
git branch -M main
git push -u origin main
```

## 许可

MIT
