# 重启后环境配置回执（2026-09-10）

## 结果与边界

本机环境配置部分完成，正式部署仍受Docker Desktop启动故障阻塞。没有替换为Mock页面，没有重置Docker、删除卷或修改业务代码。开发分支保持`codex/scan-reliability-integration`，说明书隔离副本保持`450b8ebe3381a6a27ca333ed78c9a7ad572ba65b`。

| 检查 | 实际结果 |
|---|---|
| Windows重启 | 今日14:33已重启，无待重启标记；DISM确认WSL和VirtualMachinePlatform均已启用 |
| WSL安装 | 自带`wsl --install --no-distribution --web-download`返回403；改用微软官方签名MSI安装成功，退出0 |
| WSL版本 | 2.7.13.0，内核6.18.33.2-2；未额外安装Ubuntu或下载模型 |
| 原有工具 | Python3.12.10、Node26.2.0、pnpm10.30.0均可运行；受限终端拒绝访问不等于工具损坏 |
| Docker | Desktop4.90.0、CLI29.7.2、Compose5.5.1已安装；Linux Engine仍无可用命名管道 |
| Compose | 手册Git开启、AI关闭、Ollama关闭配置静态校验通过；启动助手选择本机8081备用端口 |
| 端口 | 8080由ApplicationWebServer.exe占用，HTTP工作台路径返回Mbedthis-Appweb/2.5.0的404，不是OpenGuard；5173未监听；8081未发现监听 |

WSL MSI来源：[微软WSL 2.7.13官方发布](https://github.com/microsoft/WSL/releases/tag/2.7.13)，文件`wsl.2.7.13.0.x64.msi`，SHA-256 `a3505a50f4cc585551d11d9de824ba4375448d7a68f2e71d3fb315fa986fc754`。Microsoft Corporation数字签名Valid；MSI不上传。

## Docker阻塞与安全恢复尝试

启动日志先报`Docker/run/sailor-ingest.sock`无法重新使用。停止失败进程后，确认run目录仅含三个零字节套接字，将整个目录改名为`run-backup-20260910-1530`保留，未删除内容。

后续启动到Secrets Engine时报`docker-secrets-engine/engine.sock`错误1920（系统无法访问此文件）。目录仅含这一个零字节ReparsePoint；AF_UNIX驱动为RUNNING。Docker官方stop与force-stop未完全退出控制进程，随后仅结束已核验路径和PID的本次失败进程；当时没有可用Engine或运行容器。

普通及正常UAC管理员的父目录改名均访问被拒绝；单文件Remove-Item、File.Delete及管理员fsutil query均失败，没有删除任何文件。微软签名Sysinternals Handle5.0在管理员模式下仅查询指定目录，返回`No matching handles found`；没有关闭句柄或用户程序。不能将“没有句柄”推导为磁盘健康，也不能保证再重启一次即可修复。

Docker上游已有同类报告：[issue554](https://github.com/docker/desktop-feedback/issues/554)、[issue536](https://github.com/docker/desktop-feedback/issues/536)。上游建议的父目录改名已实际尝试，本机第二个目录仍被拒绝；没有关闭Docker安全功能或用factory reset绕过。

## 下一步与验收门禁

需用户保存工作后配合安全模式或离线诊断，先仅隔离这个套接字目录；本轮没有修改启动配置、自动重启、运行磁盘修复或重装/重置Docker。解除系统阻塞后由Root继续：

1. Engine Server版本与`docker run --rm hello-world`通过。
2. 设置`OPENGUARD_WEB_PORT=8081`及手册三个开关，运行`docker compose -f deploy/compose.yaml up -d --build --wait`，验证api/web健康。
3. 访问`http://127.0.0.1:8081/app/new-scan`，使用固定版本的`deploy/smoke.py --url http://127.0.0.1:8081 --external-scanners --ai-assets --output <本机新输出目录>`验证真实ZIP、报告与错误路径，随后Git及持久化验收。

目标地址尚未可用。不能声称本机完整部署或异机通过；镜像构建、真实扫描、报告下载、重建持久化及第二机器回执仍缺。AI按手册关闭；报名资格/权属材料、完整作品交付与质量竞争力仍需各自实证门禁，不报百分比。

## 文件与发布

仅公开本回执、共享日志、进度、AI与第三方工具登记。安装器、诊断工具、日志、个人路径和隔离副本均不上传；本机首次启动助手保留在忽略目录，已配置8081。没有API/Schema/规则变化，不重复业务单测；仅环境探针及diff/待提交清单检查。文档由Root提交推送当前功能分支，不修改main。
