# 独立 Java 扫描与报告核心

本期 Web 继续使用 Python API；本模块独立执行受信本地目录扫描和 JSON/CSV/HTML 报告，不启动 Spring Boot，也不调用 Python、ScanCode、Syft 或被扫描项目。

要求与 pom 保持一致：JDK 25、Maven。2026-10-22 本轮实际环境为 Temurin 25.0.2、Maven 3.9.16；Spring Boot parent 4.1.1、exec-maven-plugin 3.6.2 及其余依赖均未升级。第一次构建/执行需要下载未缓存依赖；本机沿已有 Maven 阿里云镜像。依赖缓存完整后可加 -o 离线执行。

在仓库根目录 PowerShell 执行：

~~~powershell
mvn -f backend/java/pom.xml test
$samplePath = (Resolve-Path examples/delivery-remediation/after).Path
$outputPath = Join-Path $env:TEMP ('openguard-java-' + [guid]::NewGuid().ToString('N'))
$scanArgs = '--trusted-checkout "' + $samplePath + '" self-authored-delivery "' + $outputPath + '"'
mvn -f backend/java/pom.xml org.codehaus.mojo:exec-maven-plugin:3.6.2:java '-Dexec.mainClass=dev.openguard.scan.RealRepositoryScan' ('-Dexec.args=' + $scanArgs)
Get-ChildItem -LiteralPath $outputPath
~~~

输出目录必须是全新、位于输入目录之外；已存在的目录会拒绝，避免覆盖旧报告或把报告扫回输入。三文件为 scan-result.json、resource-inventory.csv、report.html；JSON 包含随机独立 scan_id、时间、来源标识、证据与待核验状态。HTML 可直接在浏览器打开。CLI 输出单行 scan_id/status/counts，失败返回非零；保留控制台排查，不把失败目录当完整交付。

支持边界：

- 有界读取受信检出目录，最多4,000个常规文件，单文件512 KiB；不跟随文件符号链接，忽略根 .git。超出总文件数拒绝，跳过大文件或解析失败保留诊断并标 partial。
- Python requirements*.txt 与根 pyproject.toml 的有限直接依赖提取；精确 ==/=== 声明记录版本，范围约束仍 unknown。不是完整 PEP508/TOML/锁文件解析器。
- 根 package.json 的 dependencies/devDependencies 仅保留声明字符串，不解析或安装依赖，不把范围字符串当锁定安装版本。
- LICENSE/NOTICE/COPYING 的标题启发式只产生 pending 候选。泛 GNU GPL 标题不会猜版本或 or-later 权利，未知保留 NOASSERTION。根许可不映射为第三方组件授权。
- 静态 Hugging Face/Kaggle/ModelScope URL 仅为资源引用；既有本地 HF metadata 样例解析保持观察语义，不访问远程。
- 本模块 DTO contract_version=0.1.1 是独立 Java DTO，不等价于完整 Python P0 ScanRun；Java CSV 为现有五列，不冒充 Web 的竞赛七组字段清单。无 ZIP/Git 安全接入、P2、AI、HTTP队列或Web迁移承诺。

本轮验证：mvn test 实际35项通过；两个自有受信样例均真实产生三格式，requests 从 unknown 变为2.32.3，Apache候选仍pending、finding仍review_required。原始控制台与target运行产物只在本地保留。该结果只支持 F07，本轮 Python Web 的真实复扫须单独验收。
