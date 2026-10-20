# 3.0 源码与打包

目标是同一台 Apple 芯片 Mac 的可重装安装包；不是通用安装器。Python 不随包分发，使用现有环境。按钮界面、快捷键、单次零等待断线和连接筛选在 3.0.1 改为当前日志目标的 IP 和端口精确匹配。

## 文件

- `helper/main.swift`：小型 Cocoa 按钮；从 App Resources 加载后端，从用户支持目录读 Python 路径和配置。
- `helper/hsd.py`：后端，动态读取当前游戏服 IP 和端口；无目标或有歧义时取消，保留战网登录连接。
- `session_manager.py`：检测炉石进程的启停，仅打开/关闭已安装 App，不调用断线 API。
- `install.py`、`安装3.0.command`：校验、迁移安装、配置用户级 LaunchAgent；当前炉石仍在运行时拒绝切换，避免打断对局。
- `build.py`、`package.py`：本机 Command Line Tools 编译按钮、复用已验收 HSTracker 并打包。
- `hstracker-build.json`：已验收构建的来源与依赖摘要。
- `HSTracker.Package.resolved`：已验收构建使用的 14 项 Swift 包锁定信息。
- `tests/test_runtime.py`：合成连接筛选与生命周期回归，不读取真实游戏记录，也不真正断线。

## 重建按钮和安装包

先获取已验收的 HSTracker 构建。该构建保存在仓库的未发布草稿中，需要仓库所有者身份：

```bash
gh release download hs2-build-39111059922-1 --repo leap-frog21/hstracker-reconnect-build --dir /你的/输出目录
```

按该草稿的 `SHA256SUMS` 核验后解压。或者使用已安装的同一份 HSTracker。以下命令在仓库根目录运行，选一个尚未使用的输出目录：

```bash
~/miniconda3/bin/python3 -m unittest discover -s suite/tests -v
~/miniconda3/bin/python3 suite/package.py --hstracker-app /Applications/HSTracker.app --output dist/rebuild
```

本机需有 Command Line Tools 才能重建按钮；安装和使用不需要编译器。打包器会校验 HSTracker 可执行文件摘要，拒绝混入其他构建。输出包含两个 App、安装器、清单和 SHA256SUMS，编译缓存会自动清理。

HSTracker 的完整上游源码固定在 `8d5ff46962ad485136cbc863ab62752004bdbe49`，本仓库 `reconnect.patch` 是全部源码修改。需要从源码重新构建时，使用根目录的 `prepare_source.py` 和 `build_remote.sh`；这需要完整 Xcode，不能假定一次构建就通过。根目录工作流仅手动触发，本次 3.0 打包不需要再次运行它。

上游部分二进制依赖采用可变下载地址；已验收摘要保存在 `hstracker-build.json`。3.0 不重新下载这些依赖，而复用已验收的 App。重新源码构建不保证与原包逐字节相同。

源码沿用 MIT 许可证并保留上游声明；HSTracker 内第三方组件继续保留各自随附声明。安装包仅存为自用草稿，不包含游戏日志、聊天、账号数据、个人配置和历史备份。
