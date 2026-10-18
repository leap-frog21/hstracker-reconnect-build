# HSTracker 重连兼容改进与测试版构建

这是由 leap-frog21 发起和维护的开源兼容改进项目，目标是在同一局战棋多次断线重连后，保留 HSTracker 已采集的对手阵容和已有预测，并继续跟踪后续回合。当前为开发测试阶段，尚未通过完整应用构建和实局验收。

本项目基于 HearthSim/HSTracker 3.7.0，提供最小源码补丁和远程构建脚本。HSTracker 主体与现有追踪、预测功能来自上游；本项目不是 HearthSim 官方发行版。保留上游版权声明，并按本仓库 MIT 许可证提供源码。未收到的战斗过程不会补造。

构建机器使用 GitHub 的标准 `macos-26` 运行器及预装 Xcode 26.6；本机不用安装完整 Xcode。原始上游源码由运行器按固定提交拉取。

本目录只包含重连补丁、构建脚本、工作流、输入摘要和许可证。不包含本机日志、脱敏日志样本、账号凭据、Clash 配置、原聊天记录或 1.0 程序。

## 触发、结果与费用边界

- 仅允许手动触发，不因推送或 PR 自动构建，不自动重试。
- 现有工作流只允许公开仓库的标准运行器；每次最多 45 分钟。不使用 larger runner、Actions 缓存或 Actions artifact 上传。仓库已恢复公开；若将来改为私有，现有保护条件会阻止实际构建，核实额度及费用边界前不移除此条件。
- 构建成功后将测试包和摘要存为 GitHub Release 草稿。草稿不发布为公开版本，供仓库有权限的用户下载。需要 `contents: write` 权限用于创建草稿。
- GitHub 官方文档说明公开仓库的标准运行器免费；Release 资产每个文件小于 2 GiB，总体积及下载带宽无配额上限。该方案不使用 Actions artifact 的计费存储。
- 首批构建范围为最多 3 次，每次上限 45 分钟；失败先读日志再作定点修复，不自动重试。

## 构建内容与验证边界

`manifest.json` 记录上传文件摘要和上游提交。准备步骤先核验摘要、上游提交和干净工作区，再应用补丁。测试版只生成 arm64 架构，沿用上游程序标识与数据路径，关闭测试版自身的自动更新检查；不会安装或启动本机程序。

上游部分二进制依赖使用可变下载地址，构建结果会记录其摘要。测试版以 ad-hoc 签名打包，未公证；构建成功也不代表系统权限、HearthMirror、账号功能或连续重连已经验证。正式实测前先备份 HSTracker 本地数据，退出官方版，再试独立测试包。

下载后先核验 `SHA256SUMS` 与 `build-manifest.json`。验证同局身份、阵容与胜率保留、后续回合更新、新局清理；通过后才决定切换使用入口。

上游来源：https://github.com/HearthSim/HSTracker

费用说明：https://docs.github.com/en/billing/concepts/product-billing/github-actions

Release 限制：https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
