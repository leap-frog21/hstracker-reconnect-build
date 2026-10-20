# 炉石拔线助手套件 3.0

本包供 Apple 芯片 Mac 自用重装，包含手动拔线按钮及基于 HSTracker 3.7.0 的重连兼容构建。3.0.1 是套件版本号，HSTracker 内部版本仍为 3.7.0.DEV。

## 安装

1. 保留现有炉石、Clash Verge 和 Python 3.10+ 环境。默认使用 `~/miniconda3/bin/python3`；Clash Verge 需要启用 TUN。
2. 正常退出炉石，解压整个安装包，双击 `安装3.0.command`。安装期间不需要完整 Xcode，不会下载或重装 Python。
3. 安装完成后，炉石启动时会自动打开拔线按钮和 HSTracker；炉石退出时两者一起关闭。快捷键仍是 Control + Option + D。断线仅由你手动触发。每次从当前对局日志读取游戏服 IP 和端口；无有效目标或匹配不唯一时取消，保留战网连接。
4. 如 macOS 提示辅助功能或游戏读取授权，请为 `/Applications/HSTracker.app` 完成系统确认。本包为 ad-hoc 签名，未公证。

使用其他 Python 时，在终端执行：

```bash
HS_SUITE_PYTHON=/你的/Python路径/python3 bash 安装3.0.command
```

安装后 App、后台程序及配置分别位于：

- `/Applications/HSDisconnect.app`、`/Applications/HSTracker.app`
- `~/Library/LaunchAgents/com.leap.hsautostart.plist`
- `~/Library/Application Support/HSDisconnect/`
- 日志：`~/Library/Logs/HSDisconnect/`

运行时不依赖安装包或旧项目文件夹，但仍依赖上述现有 Python。HSTracker 保持原有数据位置，安装器不清理对局数据和偏好设置。已有配置不覆盖，安装替换的文件会在用户支持目录下留备份。

## 检查与恢复

只读检查安装包：`~/miniconda3/bin/python3 install.py --check`。

只读检查已安装的按钮与后端：`/Applications/HSDisconnect.app/Contents/MacOS/HSDisconnect --diagnose`。

停用自动启停：`launchctl bootout gui/$(id -u)/com.leap.hsautostart`。恢复启用：`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.leap.hsautostart.plist`。

安装备份位置见 `~/Library/Application Support/HSDisconnect/installation-3.json`。失败安装会尝试恢复被替换的 App 与自启配置。需要恢复官方 HSTracker 时，可重新从 HearthSim 下载；退出运行中的跟踪器后再替换 App。

源码与构建方法：https://github.com/leap-frog21/hstracker-reconnect-build 。上游：https://github.com/HearthSim/HSTracker 。本项目不是暴雪或 HearthSim 官方发行版。
