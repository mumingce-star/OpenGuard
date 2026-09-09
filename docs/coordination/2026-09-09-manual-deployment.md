# 说明书 v1.0 安装部署回执（2026-09-09）

## 使用的版本与边界

按用户提供的《OpenGuard 安装部署与使用说明书》v1.0（7页，标注更新日期2026-09-06）执行。原PDF只在本机读取，不复制或上传。

- 指定源码：`450b8ebe3381a6a27ca333ed78c9a7ad572ba65b`。
- 部署副本：仓库内被忽略的 `.tools/deploy-manual-450b8e`，独立detached worktree；当前开发分支不切换、不覆盖。
- 运行设置：公开Git开启，AI关闭，Ollama Docker宿主连接关闭。
- 正式网页目标：`http://127.0.0.1:8080/app/new-scan`，本轮尚未启动成功。5173属于此前Mock演示，不等于正式部署。

## 已完成与实际验证

| 项目 | 实测结果 |
|---|---|
| 运行环境 | Windows 11 Home 64-bit，build26200，约15.3GiB内存；固件虚拟化已开启；安装前系统盘约59GiB、项目盘约335GiB可用 |
| 安装器 | Docker官方安装器约605MB，Authenticode状态Valid，签名方Docker Inc；文件版本4.90.0.238679 |
| WSL/虚拟机平台组件 | 使用正常Windows UAC运行DISM启用；日志显示两组件Installed，`Reboot required=yes`，未自动重启 |
| Docker Desktop | 管理员标准安装成功，退出码0，日志`Installation succeeded`；选择WSL2后端 |
| Docker CLI | `docker --version` 为29.7.2 |
| Docker Compose | `docker compose version` 为v5.5.1 |
| 源码固定 | worktree HEAD为说明书指定SHA，工作区干净 |
| Compose静态配置 | 三个环境开关按手册设置后，`compose config --quiet`退出0；默认服务为api、web |
| Docker Engine | 未启动：`docker desktop status`为stopped；后端stopReason为Virtual Machine Platform not enabled / No virtualization available |
| hello-world | 未通过，退出1：Docker Desktop Linux Engine的`_ping`返回500；不作为镜像/应用失败证据 |

先前用户级安装尝试退出后没有可用安装文件；随后通过正常UAC执行标准管理员安装成功。没有绕过UAC、签名校验、系统防护或配置privileged容器。

组件安装日志和Docker错误相互印证：固件虚拟化已开启，但Windows新启用的虚拟机平台尚待重启生效。不能通过继续构建镜像解决此启动前置问题。需要用户保存工作并重启Windows；本轮不自动重启或中断用户应用。

官方参考：[Docker Desktop Windows安装说明](https://docs.docker.com/desktop/setup/install/windows-install/)。后续若Docker仍提示WSL版本不足，再按官方指引核验/更新WSL运行时，不将Windows可选组件启用等同于WSL运行时/内核已全部就绪。

## 说明书与代码的一处差异

说明书称Web、API、Scanner都应running/healthy，并建议queued时检查scanner。固定源码的Compose实际将scanner置于`profiles: [tools]`，它是按需执行并退出的工具检查；生产扫描在api进程中执行。默认只有api、web常驻，不能把scanner未常驻判为故障。队列问题优先检查api任务分发和日志。

## 重启后继续

1. 打开Docker Desktop，等待Linux引擎就绪；验证`docker version`同时含Client/Server，`docker compose version`成功，`docker run --rm hello-world`成功。
2. 进入已准备好的`.tools/deploy-manual-450b8e`副本。不要在父目录的另一个Git仓库或旧Mock分支执行Compose。
3. 在无现存活动扫描时，设置并启动：

```powershell
$env:OPENGUARD_ENABLE_PUBLIC_GIT = '1'
$env:OPENGUARD_ENABLE_AI = '0'
$env:OPENGUARD_OLLAMA_DOCKER_HOST = '0'
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml up -d --build --wait
docker compose -f deploy/compose.yaml ps
```

本机另备`.tools/start-manual-deployment.cmd`供首次部署续跑：核验源码SHA、Docker引擎、配置后再构建启动；不修改执行策略。该脚本是被忽略的本机助手，不作为团队公共源码交付，以上命令为可复现入口。

4. api/web健康后打开8080工作台，提交源码ZIP，并用现有`deploy/smoke.py --external-scanners --ai-assets --output <本机新输出目录>`核验真实任务、工具事实、Evidence和报告。该旧版脚本没有最新版`--wait-seconds`选项，不混用其他提交的命令。
5. 验证公开Git、四格式报告及浏览器实际保存；确认无queued/running任务后再做容器重建与原报告SHA复验。禁止用`down -v`清理数据。

## 未完成和发布范围

尚未执行镜像构建、容器健康、正式8080页面、真实Git/ZIP扫描、报告下载、重建持久化及异机验收。AI按手册保持关闭，不额外下载模型。重启后的版本/引擎变化要以实际新探针为准。

发布仅含本回执、共享日志、进度和AI记录、第三方工具登记；不上传PDF、安装器、临时pypdf库、浏览器数据、虚拟环境、worktree副本或本机脚本。无业务接口/Schema/规则变更。
