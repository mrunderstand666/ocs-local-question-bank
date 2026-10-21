# 国科大工程伦理慕课OCS本地题库

一个带中文界面的 Windows 本地题库服务。双击单个 EXE 后，OCS 可以通过本机 HTTP 接口查询内置答案。

当前版本 **v1.1.0**，内置工程伦理（玉泉路）39 个章节测验、150 道题。适用于 Windows x64，下载后双击即可使用，无需安装 Python。

**[下载 Windows 单文件版](https://github.com/mrunderstand666/ocs-local-question-bank/releases/latest)** · **[版本说明](CHANGELOG.md)**

[![程序实际界面高清截图](screenshot-hd.png)](screenshot-hd.png)

## 目录

- [快速开始](#快速开始)
- [界面功能](#界面功能)
- [接入 OCS](#接入-ocs)
- [题库内容与匹配规则](#题库内容与匹配规则)
- [HTTP 接口](#http-接口)
- [从源码运行](#从源码运行)
- [常见问题](#常见问题)
- [许可与反馈](#许可与反馈)

## 快速开始

1. 在 [Releases](https://github.com/mrunderstand666/ocs-local-question-bank/releases) 下载 `OCS-Local-Question-Bank-v1.1.0-windows-x64.exe`。
2. 双击运行，等待服务启动。界面显示绿色的“服务运行中”后即可使用。
3. 已配置过 `http://127.0.0.1:18651/search` 的 OCS 可继续使用；第一次使用时点击“复制 OCS 配置”，按下文添加。
4. 使用 OCS 时保持程序运行，可以最小化。点击“停止服务”或确认退出会停止查询接口。

软件为免安装单文件版，使用时保持 EXE 运行。首次启动可能需要等待片刻。

### 文件校验

Release 同时提供 `SHA256SUMS.txt`。在 PowerShell 中运行：

```powershell
Get-FileHash .\OCS-Local-Question-Bank-v1.1.0-windows-x64.exe -Algorithm SHA256
```

将输出与校验文件对应行比较。v1.1.0 发布 EXE 为 12,878,854 字节。当前二进制未做代码签名。

## 界面功能

| 功能 | 行为 |
| --- | --- |
| 自动启动 | 打开窗口后加载内置题库并监听本机 18651 端口 |
| 启动／停止服务 | 在同一窗口中控制服务，停止后可以重新启动 |
| 复制 OCS 配置 | 将完整 JSON 配置复制到剪贴板 |
| 检测连接 | 检查本地服务状态和题目查询是否可用 |
| 查询统计 | 显示本次运行的请求数、命中数、最近查询时间与结果 |
| 配置与帮助 | 展示配置内容和接入步骤 |
| 退出提醒 | 提醒退出会停止查询，确认后释放服务端口 |
| 端口占用提示 | 已有服务或端口冲突时给出提示，不结束其他进程 |

查询统计在内存中保存，重启程序后归零。“检测连接”会计入查询次数。

## 接入 OCS

### 第一次配置

1. 启动本程序，确认显示“服务运行中”。
2. 点击“复制 OCS 配置”。
3. 在 OCS 面板进入“通用 → 全局设置 → 题库配置”（不同版本的名称可能略有不同）。
4. 只有本题库时可粘贴完整数组；已有其他题库时，把下面的对象追加到原有数组中，保留其他配置，注意逗号和方括号。
5. 保存配置，按 OCS 页面提示完成对本机地址的访问授权，再执行连接检查。

```json
[
  {
    "name": "工程伦理（玉泉路）个人作答题库",
    "homepage": "http://127.0.0.1:18651/",
    "url": "http://127.0.0.1:18651/search",
    "method": "get",
    "contentType": "json",
    "type": "GM_xmlhttpRequest",
    "data": {
      "title": "${title}",
      "type": "${type}",
      "options": "${options}"
    },
    "handler": "return (res) => res.code === 1 ? res.results.map(r => [r.question, r.answer]) : undefined"
  }
]
```

配置采用 OCS 的 AnswererWrapper 结构。`GM_xmlhttpRequest` 用于脚本跨域请求；脚本管理器需要允许访问 `127.0.0.1`。如果出现域名权限提示，请核对目标是本机地址。可参考 [OCS 官方开发文档](https://docs.ocsjs.com/docs/other/api) 中的题库配置和 `@connect` 说明。

OCS 必须与本 EXE 运行在同一台电脑上；另一台电脑访问自己的 `127.0.0.1` 不会连接到本机。服务只监听回环地址，没有对局域网或互联网开放。

### 使用题库

完成配置后，在课程习题页使用 OCS 的搜题功能。本程序提供本地答案查询；网页题目识别、选项匹配与填写由 OCS 处理。

- 使用期间保持本程序显示“服务运行中”。
- 在 OCS 查询结果中查看题库来源及返回答案。
- 可在程序窗口查看查询次数、命中次数和最近查询结果。
- 保存或提交答案前，请核对题目与答案内容，并按需设置 OCS 的提交行为。

## 题库内容与匹配规则

| 题型 | 数量 | 内部类型 |
| --- | ---: | --- |
| 单选题 | 71 | `single` |
| 多选题 | 36 | `multiple` |
| 判断题 | 17 | `judgement` |
| 填空题 | 26 | `completion` |
| 合计 | **150** | |

题库数据保存在 `seed.json`，包含题目、选项、答案和章节信息。题库为个人整理资料，供学习参考，使用时请结合课程内容核对。

匹配策略：

- 对题干进行 Unicode NFKC 规范化，处理开头的题型标签、题号与末尾分值，并忽略非字母数字字符。
- 使用规范化后的题干精确匹配；不做语义检索或模糊猜答。
- 调用方提供有效题型时按题型筛选。
- 提供选项时比较选项文本集合，支持 `A.`、`A、` 等常见前缀和选项乱序。
- `undefined`、`null` 以及未替换的选项占位符按空选项处理，兼容 OCS 的部分请求形式。
- 同题干但题型、选项或答案有歧义时返回未命中，要求提供更多题目信息。
- 多选和多空答案采用 `#` 分隔；选择题返回选项文本，方便 OCS 根据当前顺序匹配。

## HTTP 接口

默认基础地址：`http://127.0.0.1:18651`。接口无账号登录，只供本机只读查询；没有添加、修改或删除题目的 HTTP 入口。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET / HEAD | `/health` | 服务标识、版本、题量和可查询数量 |
| GET / HEAD | `/`、`/index.html` | 同健康检查 |
| GET / HEAD | `/search` | 题干、题型与选项查询 |
| GET / HEAD | `/ocs-config` | 返回当前端口对应的 OCS 配置数组 |

`HEAD` 返回相应状态码和头部，不返回正文。未知路径返回 404；非本机 Host 请求被拒绝。此限制不等同于身份认证，本机程序仍可访问服务。

### 请求参数

| 参数 | 必需 | 说明 |
| --- | --- | --- |
| `title` | 是 | 完整题干，使用 URL 编码 |
| `type` | 否 | `single` / `multiple` / `judgement` / `completion` |
| `options` | 否 | 换行分隔的完整选项，建议包含选项文本 |

```python
import json
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

query = urlencode({
    "title": "伦理是处理人与人、人与社会、( )相互关系时应遵循的道理和准则。",
    "type": "single"
})
with build_opener(ProxyHandler({})).open(
    "http://127.0.0.1:18651/search?" + query, timeout=5
) as response:
    print(json.load(response))
```

命中响应示意：

```json
{
  "code": 1,
  "msg": "找到匹配答案",
  "results": [
    {
      "id": "53463",
      "question": "伦理是处理人与人、人与社会、( )相互关系时应遵循的道理和准则。",
      "answer": "人与自然",
      "chapter": "1.1.1",
      "answer_source": "graded_answer"
    }
  ]
}
```

无匹配或题干歧义时，返回 `code: 0` 和空的 `results`，不会凭空生成答案。

## 从源码运行

源码运行需要 Python 3 及可用的 Tkinter / Tcl/Tk，运行依赖均来自 Python 标准库。

```powershell
git clone https://github.com/mrunderstand666/ocs-local-question-bank.git
cd ocs-local-question-bank
python gui.py
```

如使用源码启动纯命令行服务：

```powershell
python bank_server.py --check
python bank_server.py --bank .\seed.json --port 18651
```

GUI 默认使用随源码或 EXE 内置的 `seed.json`。`--bank`、`--port` 和 `--check` 属于命令行服务 `bank_server.py`，不是 GUI EXE 的参数。命令行版本在 Windows 可通过另一个终端运行 `python bank_server.py --stop --port 18651` 停止；GUI 服务请使用窗口按钮停止。

## 常见问题

### OCS 提示连接失败

确认 EXE 显示“服务运行中”，地址是 `http://127.0.0.1:18651/search`，浏览器与 EXE 在同一电脑。先用“检测连接”确认服务，再检查 OCS 的配置是否保存、脚本管理器是否允许访问本机地址。不要把 JSON 中的 `GM_xmlhttpRequest` 随意改成普通 `fetch`。

### 为什么显示“已有题库服务运行”或端口占用？

同一端口只能由一个服务监听。请关闭重复运行的题库窗口后重试。程序不会强制停止其他进程。GUI 固定使用 18651；开发者需要其他端口时可使用命令行服务并同步调整 OCS 配置。

### 为什么有题目但没有返回答案？

题目可能不在这 150 道中；题干有实质性差异；选项缺失、重复或不同；或者同题干存在歧义。服务选择返回未命中，避免把不同题目错误匹配。

### 程序能独立操作课程网站吗？

不能。它只提供本地题库查询服务。网页题目识别、选项匹配、填写、保存或提交由 OCS 及课程平台控制，请在对应软件中核对这些行为。

### 能直接在 EXE 旁边放一个题库文件来更新吗？

当前 GUI 版本始终读取内置数据，不会自动读取旁边的 JSON。修改源码中的 `seed.json` 并重新打包，或者用命令行服务的 `--bank` 指定外部文件。

### 关闭窗口后为什么不能查询？

服务随窗口退出而停止。需要持续查询时请最小化，重启电脑后需再次打开程序。

### 是否支持 macOS / Linux？

当前提供 Windows x64 发行版。

## 许可与反馈

本仓库原创程序代码按 [MIT License](LICENSE) 开源。该许可不授予第三方课程材料、题目文本或 OCS 自身的知识产权；数据使用及再分发应遵守其原有权利和使用条件。本项目是独立的本地服务，与 OCS 官方及课程平台无隶属关系。

问题反馈时请提供软件版本、界面提示和脱敏后的请求示例；不要上传 Cookie、课程登录链接、账号口令或其他题库的密钥。
