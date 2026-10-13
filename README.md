# EPD-skill

让 AI 通过蓝牙更新墨水屏，把任务、计划或自定义图片放到桌面上。

基于 [EPD-nRF5](https://github.com/tsl0922/EPD-nRF5) 开源固件，通过 Python 调用本机 BLE 接口上传图片，无需厂商 APP。感谢原项目作者提供的固件与通信协议。

## 效果展示

### 实体屏幕

![墨水屏显示效果](https://github.com/user-attachments/assets/f1e776fe-66bf-493a-aad8-69c6506e2810)

### 网页编辑器

![墨水屏网页编辑器](https://github.com/user-attachments/assets/75f07587-1837-4859-bb15-6da8319c1ec5)

## 功能与目录

| 组件 | 用途 | 入口 |
| --- | --- | --- |
| `epd-control` | 查询设备、上传已有图片并刷新屏幕 | [Skill 说明](epd-control/SKILL.md) |
| `epd-planner` | 生成任务面板、网页预览与编辑、蓝牙上传 | [Skill 说明](epd-planner/SKILL.md) |
| `epd-editor` | 独立离线网页编辑器，可直接打开使用 | [使用说明](epd-editor/使用说明.md) |

`epd-planner` 内已包含网页编辑器，单独使用该 skill 无需另外复制 `epd-editor`。

## 已验证设备

| 参数 | 配置 |
| --- | --- |
| 蓝牙名称 | `NRF_EPD_A571` |
| 屏幕 | 4.2 英寸，400 × 300，黑白红三色 |
| 驱动 | UC8176，型号 ID `0x03` |
| 实机固件 | `v1.10-nrf52811` |
| 验证环境 | macOS，通过 Bleak / CoreBluetooth 通信 |

当前上传脚本针对以上配置校验。其他型号需要适配，不能直接视为兼容。执行上传的电脑需具备蓝牙硬件、系统蓝牙权限，并能连接设备；云端 AI 需要通过本机执行工具调用。

## 快速开始

### 1. 获取项目

```sh
git clone https://github.com/ybyllc/EPD-skill.git
cd EPD-skill
```

### 2. 使用网页编辑器

直接用 Chrome 或 Edge 打开 `epd-editor/index.html`，或启动本地服务：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory epd-editor
```

访问 <http://127.0.0.1:8765>，选择版式、编辑内容，再导出图片。

- 四种示例：今日清单、三件要事、时间安排、任务看板。
- 可调整字体、字号、红色强调、阈值与抖动效果。
- 导出 400 × 300 PNG，或保存、导入可编辑 JSON。
- 字体与脚本均随项目提供，可离线运行。

网页只负责预览与编辑，不会连接或刷新设备。预览不模拟实体屏幕的残影、实际色彩与刷新过程。

### 3. 安装蓝牙上传依赖

```sh
python3 -m venv .epd-venv
.epd-venv/bin/python -m pip install -r epd-control/scripts/requirements.txt
```

以下命令使用 macOS / Linux 风格路径；Windows 虚拟环境解释器位于 `.epd-venv\Scripts\python.exe`，蓝牙兼容性需自行验证。

### 4. 查询或更新屏幕

查询设备配置，不刷新屏幕：

```sh
.epd-venv/bin/python epd-control/scripts/inspect_epd.py \
  --name NRF_EPD_A571 --output device-info.json
```

上传从编辑器导出的图片并刷新：

```sh
.epd-venv/bin/python epd-control/scripts/upload_epd.py \
  /absolute/path/epd-panel.png --name NRF_EPD_A571
```

图片必须恰好为 **400 × 300**，脚本不自动裁剪或缩放。建议使用黑白红 RGB PNG，透明图片先合成到白底。上传会替换当前画面；刷新指令获确认不等同于已验证实体显示效果。

## 让 AI 调用

将需要的 skill 文件夹放入 AI 工具的技能目录。例如 Codex 使用 `~/.codex/skills/`，复制整个 `epd-control` 或 `epd-planner` 目录，保留其中的脚本和资源。

调用示例：

> 使用 $epd-control，把这张 400×300 图片显示到墨水屏。

> 使用 $epd-planner，帮我预览一个今日任务面板，先不要上传。

其他能够读取文件并执行 Python 的 AI，也可以按对应 `SKILL.md` 的说明调用。消息端 AI 可以负责接收和整理任务，显示端负责排版与上传；详见 [任务显示接口](epd-planner/examples/DISPLAY-INTERFACE.md)。

网页导出的 `tasks` JSON 与脚本排版使用的 `rows` JSON 不同。保留网页版式时，请直接上传网页导出的 PNG，不要把 `tasks` JSON 交给 `render_card.py` 重新排版。

## 致谢

- [EPD-nRF5](https://github.com/tsl0922/EPD-nRF5)：墨水屏固件、蓝牙协议与日历字体参考。
- [固件网页工具](https://tsl0922.github.io/EPD-nRF5)：原项目的 Web Bluetooth 上位机。
- 编辑器字体来源与许可见 [字体说明](epd-editor/FONT-SOURCE.txt) 和 [随附许可证](epd-editor/LICENSE)。
