# B01 元数据复现与脱敏回执

状态：2026-09-30 本机离线复现通过；真实上游探针超时；异机复现和 G8 工厂回归待完成。

从仓库根目录、Python 3.12 且已安装项目锁定依赖的环境执行：

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.scanners.b01_reproduce
.\.venv\Scripts\python.exe -m app.scanners.b01_reproduce --live
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_p1_profile_production_wiring.py
```

在 Linux/其他机器上，将解释器路径换成该机 Python 3.12。第一条只读本地 Hugging Face v1/v2 固定样本，分别核验 5 个 model、5 个 dataset 的每个文件 SHA-256 和 manifest SHA-256。第二条只访问固定的公开 ModelScope 模型与数据集元数据 API；输出 provider、kind、identity、固定 URL、UTC 获取时间、响应字节 SHA-256/长度、descriptor/transport/parser 版本、版本状态、字段定位与 coverage gap。原始响应、cookie、鉴权头、模型权重和数据内容不写入回执。`--live` 遇到失败只输出受控错误码并以非零状态退出。

本机 2026-09-30 14:18（Asia/Shanghai）回执摘要：Windows `win32`、Python `3.12.10`；v1 manifest SHA-256 `2474035e7182f8140fbe4e71dad1b9035aa598873aa483dab010a7c17dde28b6`，v2 manifest SHA-256 `8d031e89f34db5640e87770b0f3d82b09136a9b155525e02fce1b0a5df61e6ef`；两套均为 5 model + 5 dataset，全部 20 条文件哈希匹配。对应实现基线为本地 `ae73755b950eb4f113085b57e0057050bb2164c9` 加未提交 B01 工作树改动，因此该 HEAD 不能单独复现本轮结果。

同日 B01 定向及安全测试 `171 passed`。真实探针两次均在受控网络预算内返回 `timeout`，未取得本轮成功的响应哈希；2026-09-29 曾成功访问一条 model 和一条 dataset 的记录只作为历史观察，不能代替今天的独立回执。工厂测试在收集阶段因 `app.pipeline.zip_dispatcher` 无条件导入 Windows 不存在的 `fcntl` 失败（G8），尚无通过结果。

2026-09-30 19:25（Asia/Shanghai）本机再次执行 `--live`：首次仍为 `timeout`，随后两次均完整成功。以下记录取第二次成功执行的同一回执，时间均为 UTC；响应原文不落盘，SHA-256 只绑定该次获取的响应字节，不代表资源固定 revision 或授权结论。

| 类型与固定资源 | 获取时间（UTC） | 响应 SHA-256 | 字节数 | transport / parser |
|---|---|---|---:|---|
| model `Qwen/Qwen3.5-27B` | `2026-09-30T11:25:40.025678Z` | `e1a46a5905706cb33bdeff098fd9cfad3ef127263ae2282737810629cc48f11d` | 125367 | `modelscope-metadata-transport/1` / `openguard-modelscope-metadata/1` |
| dataset `AI-ModelScope/train_1M_CN` | `2026-09-30T11:25:45.497729Z` | `427fd2a05ab6073477ec170f0e36c59bb794d8157d36c94d357bc7686084bbd2` | 3900 | `modelscope-metadata-transport/1` / `openguard-modelscope-metadata/1` |

两条均由 `metadata-source/1` descriptor 绑定固定 ModelScope API URL、`default_observation`，解析结果为 `verification_status=pending`、`version_status=bounded_content_revision_unconfirmed`、`resolved_revision=null`；coverage gaps 为 `gate_value_unavailable`、`metadata_revision_unavailable`、`unsupported_last_modified_value`、`unsupported_visibility_value`。本机 Python `3.12.10` / `win32`，执行时 HEAD 为 `ae73755b950eb4f113085b57e0057050bb2164c9` 加未提交 B01 改动；因此该 HEAD 单独不能复现本次版本。矛盾 `Success`/`Message` 包络现由 transport/parser 同一规则失败关闭，B01 unit/security `177 passed`。此回执为本机成功观察，仍须 Luna 异机独立签收；G8 工厂回归与 GitHub 发布未因本回执自动通过。

异机签收需保存命令退出码、上述 JSON 回执、该机 Python/平台版本、仓库提交 SHA、是否有工作树改动，以及 Profile 工厂测试输出。不得将某台机器的离线样本验证、真实上游成功或工厂回归相互替代；发布时以签收机器和最终提交的实际回执为准。
