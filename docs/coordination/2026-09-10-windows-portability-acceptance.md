# Windows 异机实测回执

## 验收对象

用户明确当前Windows设备就是相对团队原开发环境的异机，不再要求额外提供机器或SSH。日期2026-09-10；测试固定团队集成版`5611c00cdd214cf0b3c5cf545c918ea90be0f738`，而非当前旧开发分支或说明书450b8eb。已创建忽略目录中的独立detached worktree，测试前后源码无改动，原工作分支及说明书副本保留。

本机：Windows11家庭版64位，10.0.26200；Docker CLI29.7.2、Compose5.5.1；Python3.12.10。WSL2.7.13.0及内核版本见此前环境回执，本轮不重新安装。仅测试AI关闭主链，公开Git开启，端口8081；不启用模型或变更系统安全设置。

## 实际结果：未通过，阻塞于容器运行环境

| 检查 | 命令/断言 | 本轮结果 |
|---|---|---|
| 源码固定 | git rev-parse HEAD / status --short | 指定SHA一致，副本干净 |
| Compose静态 | compose config --quiet / --services | 退出0，api/web |
| Docker Engine | docker version --format '{{json .Server}}' | Server为null，Linux Engine命名管道不存在 |
| 正式部署启动 | compose up -d --build --wait | 退出1，无法连接Docker API；尚未进入镜像构建和服务健康检查 |
| 真实HTTP冒烟 | smoke.py --external-scanners --ai-assets --wait-seconds 900 | 退出1，在首个/app/new-scan请求报WinError10061；未提交扫描任务 |
| Git/ZIP真实扫描、工具输出、报告、持久化 | 需上述服务先可用 | 未执行，不算通过也不作为扫描逻辑失败证据 |

原因链：Docker Engine不可连接 → Compose不能创建服务 → 8081无OpenGuard监听 → 网页连接拒绝。此前Desktop启动曾有残留engine.sock错误1920，详见[环境回执](2026-09-10-environment-followup.md)；本轮没有重新启动Desktop重现该内部错误，因此不把历史日志写成本轮新日志。当前不能区分“引擎未启动”与“再次启动仍会同因失败”，需后续正常启动/诊断确认。

这不是HTTPS协议错误，不是扫描已超时，也不能仅凭本次结果否定Linux容器中的应用兼容性。团队Mac历史验收不作为当前Windows通过证明。当前设备本身可承担异机验收，缺的是可用容器引擎，不是额外设备资料。

## 恢复后原地续测

由用户正常启动Docker Desktop，先确认docker version有Server；若仍报套接字错误，保留日志，按既有故障方案处理。当前任务只测试，不重置Docker、不删卷、不重启系统或擅改扫描代码。

在本机已准备的`.tools/acceptance-windows-5611c00`目录运行（Python可用本机python.exe等价替代）：

```powershell
git rev-parse HEAD
$env:OPENGUARD_ENABLE_PUBLIC_GIT = '1'
$env:OPENGUARD_ENABLE_AI = '0'
$env:OPENGUARD_OLLAMA_DOCKER_HOST = '0'
$env:OPENGUARD_WEB_PORT = '8081'
docker version
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml up -d --build --wait
docker compose -f deploy/compose.yaml ps
# 仅在以上均成功后执行；每次用新的本机输出目录。
py -3.12 deploy/smoke.py --url http://127.0.0.1:8081 --external-scanners --ai-assets --wait-seconds 900 --output ../acceptance-small-retry
```

随后按该固定版本`deploy/README.md`的Windows验收节，依次执行PyPA Git（记录实际revision）、固定smolagents ZIP、无活动任务时的API重建与--verify，并验证浏览器四格式实际落盘摘要。非默认8081端口必须在每条smoke命令中保留`--url http://127.0.0.1:8081`。Git/ZIP观察上限900秒不等于后端总超时，也不等于性能目标；不要通过延长等待掩盖失败。

本轮没有新建scan_id或成功receipt，不能做报告SHA比较。业务源码、接口、Schema、规则和依赖没有变更；未额外运行单元测试，因为不能用单元绿灯代替缺失的部署验收。公开回执和协作记录发布工作分支；独立源码副本、运行目录和个人路径不上传。
