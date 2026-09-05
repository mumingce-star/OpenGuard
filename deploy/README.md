# 最小本机部署

当前提供两个常驻容器：`web`（生产静态文件与同源代理）、`api`（现有单进程 FastAPI、ZIP dispatcher、SQLite、报告）。API 复用 Dockerfile.scanner 的工具阶段，在现有 ZIP 生命周期内执行 ScanCode/Syft；scanner 保留为按需独立工具检查。当前 Compose 只启用 ZIP；AI、公开 Git 关闭。

## 启动

准备 Docker Engine + Compose，或按[官方 Mac 安装说明](https://docs.docker.com/desktop/setup/install/mac-install/)安装 Docker Desktop。首次构建需要联网下载官方基础镜像和依赖；后续运行不安装目标项目依赖。工具镜像约需数 GB 磁盘空间，建议 Docker 可用内存至少 6 GB；这是配置建议，尚未测定最低资源需求。

在仓库根目录运行：

```bash
docker compose -f deploy/compose.yaml up -d --build --wait
```

在 **Chrome** 打开 <http://127.0.0.1:8080/app/new-scan>，选择 ZIP 并提交。含 npm 依赖的输入可完成资源、待核验风险和报告；缺少许可证声明保留 NOASSERTION，工具失败或漏扫则显示部分完成。Web 仅监听本机回环，API 不映射宿主端口。无需账号、API 密钥或新增接口。

端口占用时可在命令前加 `OPENGUARD_WEB_PORT=8081`。Docker CLI 未加入 PATH 时，使用 Docker Desktop 中配置的 CLI 路径；不要修改应用安全策略或跳过签名检查。

## 实际验收与重建

以下只使用 Python 标准库。输出目录应在仓库外，包含生成的 ZIP、任务 ID 和报告摘要：

```bash
python3 deploy/smoke.py --external-scanners --output /tmp/openguard-compose-check
# 可把上一步生成的 compose-demo.zip 用 Chrome 页面再次上传。
docker compose -f deploy/compose.yaml up -d --force-recreate --no-deps --wait api
python3 deploy/smoke.py --output /tmp/openguard-compose-check --verify
```

首条验收真实 SPA 深链接、ZIP 完成、三个资源（含 Syft 识别的项目自身）、pending 许可证、两工具版本和来源 SHA、风险/Evidence、四报告 SHA-256、缺声明输入、路径穿越 ZIP 失败、未知任务 404；第二次只读验证重建后原任务和四报告字节相同。只重启 API 时 nginx 通过 Docker DNS 重新解析服务地址。

```bash
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs --tail 50 api web
docker compose -f deploy/compose.yaml stop
# 移除容器但保留 data 卷：
docker compose -f deploy/compose.yaml down
```

不要使用 `down -v`，除非确实要永久删除扫描和报告。数据存于 `data` named volume，首次从镜像初始化 UID/GID 10001、0700；运行时不以 root 修复权限。已有卷权限错误应先备份并核对，不应放宽后端权限检查。API 和 Web 根文件系统只读，临时区可写但不可执行，不挂 Docker socket 或用户目录。

## 扫描工具环境

```bash
docker compose -f deploy/compose.yaml --profile tools build scanner
docker compose -f deploy/compose.yaml --profile tools run --rm scanner
```

默认执行 `tool-smoke.py`：临时生成 MIT 文本和 npm lock，真实执行 ScanCode 许可证扫描与 Syft SBOM，核对 MIT、相对 LICENSE 定位、`pkg:npm/is-number@7.0.0` 与 lock 来源，并输出原始 JSON 的 SHA-256。不运行样例代码、不安装样例依赖、不联网扫描；容器 `network_mode: none`、非 root、只读、无额外 capability、4 GB 内存/2 CPU 上限，输出不保存进仓库。

ScanCode 官方 Linux 包包含 x86_64 wheels，因此 **API 和 scanner 固定 linux/amd64**；Apple silicon 通过 Docker 的 Linux amd64 支持运行。Web 使用本机架构，API 的 /opt/api venv 与 ScanCode venv 分离。

| 工具 | 锁定版本 | 官方 Linux 包 SHA-256 |
|---|---|---|
| [ScanCode Toolkit](https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0) | 32.5.0 / Python 3.12 / amd64 | `638adcd0af576d1f4d5b64dde228724b3ca4fdee2c4de20d88e4356be353f027` |
| [Syft](https://github.com/anchore/syft/releases/tag/v1.51.0) | 1.51.0 / linux_amd64 | `2a2e837a2c8d59ec9af5472ee22d3b04ee463c4e44476ecf993fd1e5ab6ebc7f` |

下载后先校验再解包；工具与随包许可证保留在镜像，仓库不存安装包。ScanCode 使用官方发行包的离线 wheels，构建期预热许可证索引，运行缓存仅写 `/tmp`。Syft 更新检查关闭。基础 Python、Node、nginx 镜像按 Dockerfile 中的 manifest digest 固定；前端使用既有 pnpm 锁文件，后端沿用 pyproject 的精确直接依赖。系统包和后端传递依赖尚非完整离线锁，不能宣称两次镜像构建必然逐字节一致。

## 本轮实测边界（2026-09-05）

- Apple silicon Docker Desktop 4.89.0、Engine 29.7.2、Compose 5.5.0；Docker 官方包摘要、签名与公证核验通过。
- API/Web 镜像构建与健康检查通过；Python 3.12.14、nginx 1.30.4；真实 HTTP 9 项和容器重建后四报告摘要通过。
- Chrome **extension 插件**完成 ZIP 选择、提交、完成报告与页面恢复；JSON 下载点击后插件未返回 download 事件，下载管理页被插件策略禁止，浏览器保存结果未确认。下载接口/文件内容另由 HTTP 四格式摘要验证，不能混记成 Chrome 保存已验。
- 断网 amd64 scanner 真实 MIT 与 npm SBOM 检查通过。本轮 API 工具事实接线及真实 Chrome 报告已通过；AI 资产、Compose 内 Ollama/Git、陌生机复现仍未完成。

工具版本在调用前核验，ScanCode 文件覆盖及两工具 locator 必须匹配 A2 inventory，Evidence SHA 来自封印文件。根 LICENSE 只作文件候选，不自动赋给依赖。宿主机开关 OPENGUARD_ENABLE_EXTERNAL_SCANNERS 默认 0，Compose 明确启用；接受时固定开关，旧排队任务仍关闭。API 使用现有 Compose 网络，只有独立 scanner probe 设置 network_mode:none，不能声称 API 子进程拥有单独网络隔离。

下一步接最小 AI 资产事实，再做首批样例与陌生机验收。
