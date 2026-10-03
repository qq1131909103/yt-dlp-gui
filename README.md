# yt-dlp 图形下载助手

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的桌面视频下载工具，使用 [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) 构建现代深色界面，支持多任务队列、实时日志、进度显示等功能。

## 功能特性

- 多任务下载队列，同时管理多个下载
- 实时进度条、下载速度、剩余时间显示
- 终端风格实时日志面板
- 格式选择：最高画质 / 指定清晰度 / 仅音频 MP3
- 播放列表支持（可仅下载第一集）
- 字幕下载
- 偏好自动保存（格式、保存路径等）
- 快捷保存路径（下载 / 桌面 / 视频）
- 顶部状态指示（yt-dlp / FFmpeg 可用性）
- 底部状态栏（任务统计）

## 界面预览

采用 terminal-gui-hybrid 设计风格：深色终端配色（#0B1220）+ 青色强调（#38BDF8）+ 成功绿（#22C55E），圆角卡片，统一间距系统。

## 开发环境

### 依赖

- Python 3.10+
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) >= 5.0
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（运行时调用，需放在同目录或桌面）
- [FFmpeg](https://ffmpeg.org/)（高清合并与音频转码需要）

### 安装

```bash
pip install -r requirements.txt
```

### 运行

```bash
python yt_dlp_gui.pyw
```

或双击 `启动yt-dlp下载助手.bat`（需确保 Python 已加入 PATH）。

## 打包发布

使用 PyInstaller 打包为独立 EXE：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "yt-dlp下载助手" \
  --add-data "path/to/customtkinter/assets;customtkinter/assets" \
  yt_dlp_gui.pyw
```

打包后将 `yt-dlp.exe`、`ffmpeg.exe`、`ffprobe.exe` 与生成的 EXE 放在同一目录，即可分发。

## 第三方依赖与致谢

本项目站在以下优秀开源项目的肩膀上：

| 项目 | 用途 | 协议 |
|------|------|------|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 视频下载内核 | Unlicense（公有领域） |
| [FFmpeg](https://ffmpeg.org/) | 视频合并与音频转码 | LGPL 2.1+ / GPL 2+ |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | 现代 UI 组件库 | MIT |
| [PyInstaller](https://pyinstaller.org/) | 打包为独立 EXE | GPL（含 bootloader 例外） |

发布包中包含的 `yt-dlp.exe`、`ffmpeg.exe`、`ffprobe.exe` 均为上述项目的官方预编译二进制，版权归各自项目所有。本项目的源代码不包含这些二进制文件。

## 免责声明

请仅下载你有权下载的内容，遵守相关网站的使用条款和所在地区的版权法律法规。本工具仅供学习与个人合法使用。

## 协议

本项目源代码采用 [MIT License](LICENSE) 开源。
