# A2-3a 公开 Git 安全摄取与 TrustedEgress 规格

状态：`implemented-and-bounded`（2026-09-04）

责任范围：项目负责人 A2 输入安全、A3/A4/A6 主链接线

证据候选：`EVD-A2-PUBLIC-GIT-EGRESS-001`

## 1. 本纵切交付什么

当管理员显式设置 `OPENGUARD_ENABLE_PUBLIC_GIT=1` 时，现有
`POST /api/v1/scans` 的 Git JSON 请求会从“只登记 queued”切换为真实后台摄取：

```text
公开 HTTPS URL
  -> 语法规范化
  -> 固定 DoH 解析
  -> 全部 A/AAAA 公网判定
  -> 任务级 CONNECT TrustedEgress
  -> 固定 Git 无 checkout 浅克隆
  -> ls-tree 检查 + cat-file 流式物化
  -> immutable revision / inventory / root digest
  -> A2-2 只读会话
  -> B1 Python/JavaScript 直接依赖
  -> A4/SQLite
  -> A6 四格式阶段性报告
```

当前 B5 许可证规则尚未接入，因此有受支持 manifest 的仓库应诚实终止为
`partial/rules/70`，而不是伪造“合规通过”。摄取阶段的安全失败必须终止为
`failed/ingestion/5`，不得发布阶段性报告。

## 2. 输入契约

- 只接受 `https://DNS-host/path`，端口只能省略或为 `443`；
- 拒绝凭据、query、fragment、IP 字面量、localhost、控制字符、空路径段、`.`/`..`；
- 拒绝一次或二次百分号解码后出现 `/`、反斜杠、`?`、`#`、`@` 的路径段；
- URL 最多 2048 UTF-8 bytes，主机先 IDNA 再小写规范化；
- 不支持 HTTP、SSH、`file://`、私有仓库、OAuth、任意端口或用户提供代理/DNS。

## 3. TrustedEgress

不能先检查 DNS 再让 Git 自行直连；这会留下 DNS 重绑定窗口。本实现让 Git 只连接
`127.0.0.1` 上的任务级 CONNECT 代理。代理对每一个 `CONNECT canonical-host:443`：

1. 通过固定的 Cloudflare DoH bootstrap `1.1.1.1`/`1.0.0.1` 查询 A 与 AAAA；
2. 用系统信任库验证 `cloudflare-dns.com` TLS 证书，要求 HTTP/1.1、
   `application/dns-message`、准确 Content-Length 和有界响应；
3. 检查所有返回地址；任一 loopback/private/link-local/CGNAT/documentation/
   benchmark/metadata/multicast/unspecified/reserved 地址都会使整个解析失败；
4. 立即拨号已经验证的具体 IP，不再按主机名二次解析；
5. 只转发原始 TCP，Git 仍以 canonical host 完成端到端 TLS/SNI；
6. 上下行累计共享 256 MiB 默认硬上限，并记录主机、完整地址集合、实际拨号 IP 和 SNI。

本机代理曾把 `github.com` 系统解析为 Clash Fake-IP `198.18.0.15`。安全策略按设计拒绝
该 benchmark 网段；固定 DoH 是为避免本机代理 DNS 污染而增加的受控解析路径，不是放行
`198.18.0.0/15` 的例外。

## 4. Git 进程与物化

- 可执行文件必须是管理员提供的绝对、可执行、非 group/world-writable 普通文件；当前
  macOS profile 使用 `/usr/bin/git`，实测 `git 2.50.1 (Apple Git-155)`；
- 环境是 allowlist：无用户 HOME/config、无凭据提示、无 SSH agent、无目标 hooks、无 LFS
  smudge、无 replace objects、无可选 locks、无环境代理旁路；
- 固定 Git 配置拒绝重定向和非 HTTPS protocol；clone 固定为 `--no-checkout --depth=1
  --single-branch --no-tags --no-recurse-submodules --template=`；不使用 shell；
- clone 后只读取 `HEAD^{commit}`、`ls-tree -r -l -z --full-tree HEAD` 和
  `cat-file --batch`；不运行 checkout、hooks、build、tests 或包管理器；
- 只接受 `100644`/`100755 blob`，拒绝 symlink、gitlink/submodule、特殊 mode、非 UTF-8、
  `.git` 路径、路径冲突以及数量/单文件/总量/深度/长度超限；
- 所有 blob 以 `0600` descriptor-relative 新文件写入受控 tree，目标 executable bit 不恢复；
- 默认总时限 120 秒、连接时限 10 秒、50,000 文件、单文件 32 MiB、物化 512 MiB；
- consumer 返回前后复验 inventory identity/hash；成功和失败均清理任务 workspace，清理失败
  会毒化当前 service 并失败关闭。

Git 版本、固定 argv/config、稳定环境开关与限额共同生成 `git-client.config_digest`，连同
revision 和 inventory digest 写入 P0 provenance。连接级内部证据当前不进入公共 P0 Schema，
避免为本任务擅自修改冻结契约。

## 5. 启用与复现

公开 Git 真实摄取默认关闭；未设置开关时保留 A3-1 的 queued-only 兼容行为。管理员可在
Python 3.12 环境中启动：

```bash
OPENGUARD_ENABLE_PUBLIC_GIT=1 \
OPENGUARD_DATA_DIR=./data \
PYTHONPATH=backend \
python -m uvicorn app.api.main:create_default_app --factory --host 127.0.0.1 --port 8000
```

离线实现测试：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a2_public_git_ingestion.py
```

公开网络证据必须由操作者显式指定获准仓库：

```bash
OPENGUARD_RUN_LOOPBACK_TESTS=1 \
OPENGUARD_PUBLIC_GIT_TEST_URL=https://github.com/pypa/sampleproject.git \
PYTHONPATH=backend \
python -m pytest -q tests/security/test_a2_public_git_trusted_egress_integration.py
```

2026-09-04 受控完整回归为 `872 passed, 1 warning`。真实 PyPA sampleproject 纵切证明
HTTPS/TrustedEgress、Git object 物化、revision/inventory、B1、SQLite、
`partial/rules/70`、四份报告下载和 workspace 清理。团队仓库默认分支当时没有受支持的
Python/JavaScript manifest，故 A2 摄取成功后在扫描阶段终止为 `failed/scan/35`；这不是
许可证结果，也不能用作当前完整演示仓库。

## 6. 明确未完成

- Linux user/mount/network namespace、seccomp/cgroup profile 与陌生机复现；
- 持久任务队列、lease/heartbeat/retry/stale-running 恢复；
- 私有仓库授权、重定向、submodule 与多分支/完整历史；
- B5 许可证规则、B2/B3 主链接线、A5 AI 主链接线、前端真实 API；
- Bench 多仓库准确率、性能与攻击语料。

因此 `EVD-A2-PUBLIC-GIT-EGRESS-001` 只证明本机 macOS/POSIX 的公开 HTTPS Git P0
纵切，不能外推为 A2 总门禁、Linux 隔离或完整竞赛作品。
