# OpenGuard · AIC AI+开源半决赛候选 2026-11-16

本目录是准备录制与评委复核的同版候选，**尚未公开发布**。它来自本地完整P4彩排版本，合入上传文件选择修复，并将启动路径改为包内相对路径。它不是某个历史Git分支的原样检出；历史UI/组员提交只能说明来源。最终文件身份见 `FILE_HASHES.json`，本轮实测结果见 `VALIDATION.md`。

评审入口拟采用仓库中本版的固定提交链接，并配同提交Release ZIP；实际发布后填写确切链接。仓库默认main、旧delivery分支、历史UI分支均不能代替本版。`http://127.0.0.1:端口`只供运行者自己的电脑访问，不是评委远程在线地址。

## 目录与运行要求

- `application/`：后端、前端、规则、合同、测试与样例源码。
- `deployment/`：包内启动、固定依赖及独立HTTP自检入口。
- `web/`：与本版源码同次构建的页面，普通运行无需Node或Vite。
- `samples/`：固定is-number ZIP/LICENSE及兼容原启动器的http-server离线样例。
- `runtime/`：首次运行才创建，账号、会话、扫描、模型调用记录都在此目录；不随公开包提供。

需要CPython **3.12**（含venv/pip）、Git和现代浏览器。目标为macOS/Linux；Windows使用WSL2并放到Linux用户目录，不使用原生Windows Python。实际已验证平台与步骤仅以 `VALIDATION.md` 为准，不能将本机成功推广到所有平台。模型可选；没有模型也能扫描、补材料、比较版本、生成报告。

## 获取并启动

下载正式发布后的Release ZIP（或固定提交源码ZIP），解压到新的用户可写目录，进入含 `openguard.py` 的目录。不要覆盖旧安装。

```sh
python3.12 verify_package.py
python3.12 openguard.py setup
python3.12 openguard.py check
python3.12 openguard.py start --port 19380
```

`setup`仅在本包 `runtime/venv` 安装 `deployment/requirements.lock` 的27项固定依赖，首次默认访问官方PyPI；不修改系统Python。这里没有附带wheelhouse，不能宣称首次安装完全离线。已有适配当前平台/CPython3.12的完整wheelhouse时可替换setup命令：

```sh
python3.12 openguard.py setup --offline-wheelhouse /实际路径/wheelhouse
```

端口被占用时不要停止其他服务，省略 `--port` 让本程序选新端口。打开终端显示的 `READY http://127.0.0.1:实际端口/`，自行注册账号。前后端由此入口同源提供，不需要另开Vite Dev。Ctrl+C仅停止本次服务，数据保留在本包runtime。旧包账号不会被导入。

## 固定演示路径

1. 新建扫描 → 上传 `samples/is-number-7.0.0-derived.zip`，核对 **4,172字节**。它是原npm发行物派生的四文件ZIP，SHA256 `a70563664327b7dc5ad8ee99136c508534e2cef3aeb690beb13b13ed710bca06`，不是评估导出包。
2. 明确一个演示假设：闭源商业交付，商业/分发/修改为是，在线服务/训练/再分发模型数据/公开源码为否；也可如实保留待定。用途是输入事实，不是授权结论。
3. 扫描完成，核对5个资源、7条证据。只对根资源 `is-number@7.0.0` 继续材料演示，其余4个资源不外推。
4. 项目评估 → 查看/创建初始P2结果；查看Material Claims v3中根包用途状态。补充 `samples/is-number-LICENSE.txt`，使用实际材料Hash及明确来源说明，材料按待核验保存。
5. 查看新Revision和旧Result：材料补充前后分开显示，旧结果应可按旧ID重新读取，不覆盖。SUPPORT是保留条件的文本支持；pending、NOT_SIGNED及formal_effect=none仍保留。
6. 有符合下节身份的本地模型时，主动点击评估AI分析或在项目智询提问。AI记录独立保存，不覆盖正式Result；失败记录保留，不自动反复生成。若同一Result有多条AI记录，在导出区明确选择需导出的记录。
7. 查看资源CSV、HTML/JSON报告，创建报告归档并导出固定Result评估包。导出包是结果，不可作为下一次扫描输入。

## 本地Qwen配置

本版固定使用 **Ollama 0.33.3**、`qwen3:4b-instruct-2507-q4_K_M`，模型manifest digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`。评估AI固定连接 `http://127.0.0.1:11434`，不支持用命令参数任意更换端点。

运行时从 [Ollama官方发行页](https://github.com/ollama/ollama/releases/tag/v0.33.3) 取得；模型按 [官方模型页](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M) 获取（约2.5GB，另需推理内存）。**本包不包含模型权重，不自动下载、不启动模型、不调用云服务。** 取得模型需操作者自行确认网络、磁盘和许可条件。

若11434没有已有服务，另开终端：

```sh
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama serve
```

首次获取模型（需要网络，非本包启动步骤）：

```sh
OLLAMA_HOST=127.0.0.1:11434 ollama pull qwen3:4b-instruct-2507-q4_K_M
```

回到本包执行只读身份检查：

```sh
python3.12 openguard.py model-check
```

版本或digest不符应停止，不能改常量绕过。`model-check`仅查询版本和标签，不验证完整推理，也不重新计算全部权重Hash。账户助手与评估AI由用户主动触发，保留单次超时、并发、引用、语义检查和审计；连续使用不等于无保护。自动扫描AI、联网取证和外部扫描器仍关闭。

## 自检与开发

```sh
python3.12 openguard.py self-test
```

自检会新建 `runtime/self-tests/唯一目录`，使用新账号和动态回环端口，实际检查上传、材料、v3建议、旧Result、CAS、报告及账号隔离。它不调用模型，也不修改正常账号库；失败时保留原始日志。

可选重建需要相容Node（本轮使用24.22.3）及锁文件支持的pnpm。安装只写本包前端目录；Vite构建可能使用平台Native组件，需使用可信平台包。普通使用不需要此步骤。

```sh
cd application/frontend
pnpm install --frozen-lockfile
cd ../..
python3.12 openguard.py build
```

不要把package.json的历史完整test脚本当本版全功能验收；部分历史浏览器测试依赖另行准备的测试驱动，未纳入本轮。单测Fixture是测试数据，不是实际项目扫描成绩。

## 排错与边界

- 文件名/字节数不符：重新选择原始ZIP；取消重选会清空旧文件。
- `dependency_manifest_not_found`：查看实际输入，评估输出包没有源码依赖清单；不要通过关闭扫描检查处理。
- 身份/Hash/依赖失败：核对完整包和固定版本，不自动升级或替换pin。
- 模型未运行或身份不符：先model-check；扫描和材料流程可独立完成，不展示假回答。
- 首页背景视频/海报未纳入公开候选，页面仍保留原引用，可能出现媒体404；这不代表扫描失败。录制与交付应采用同一个不含该媒体的候选，不能展示另一份有媒体的旧首页来声称同版。详见RESOURCE_USAGE.md。
- 409：重新读取当前Result，按界面明确操作；不要自动重放旧CAS请求。
- UNKNOWN/pending是证据状态；COMPLETE仅表示引用/Hash闭包，不表示来源认证或法律签署。
- 本地连接保护不是OS级沙箱；此包只用于可信本机TEST_ONLY复核，不直接公网托管。

源码许可和第三方资源范围见 `LICENSE`、`RESOURCE_USAGE.md`。发布包不含账号、密码、会话、数据库、旧模型输出、个人路径、node_modules、虚拟环境、模型权重或无权分发媒体。
