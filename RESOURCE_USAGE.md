# 资源、模型及贡献说明

OpenGuard团队自主代码采用根LICENSE的Apache-2.0；第三方权利不因本项目许可而改变。历史源码贡献归属保留；本次候选不是单一历史Git提交。

## 直接使用与公开范围

- 后端：FastAPI/Starlette、Pydantic、Uvicorn、httpx2及其传递依赖，精确版本见deployment/requirements.lock；包内不附这些Python安装文件。接收者从官方包源取得，遵守对应包许可。
- 前端：React/ReactDOM及Tailwind。构建工具TypeScript/Vite等由pnpm-lock.yaml固定；本包不附node_modules或Native二进制。预构建web会包含运行时代码，随附从现有安装包取得的许可证文本见THIRD_PARTY_LICENSES；详细UI声明见application/frontend/THIRD_PARTY_UI.md。
- is-number@7.0.0演示输入：npm发行物派生ZIP，保留MIT LICENSE，作者版权声明不改；原始来源profile及metadata在application/tests/fixtures/task33/is-number-7.0.0。历史绝对采集路径已改为不含个人信息的说明，原始发行物、profile及材料字节未改变。来源记录不表示适用性签署。
- http-server固定离线样例：仅供现有启动器兼容入口，保留samples/http-server-LICENSE.txt；不是本轮录制主线，不能混用其资源计数或成绩。
- Qwen3-4B-Instruct-2507 Q4_K_M：仅提供本机调用代码和获取说明，不分发权重；官方模型页标示Apache-2.0。Ollama运行时独立获取。模型标签/digest及运行时版本须通过本版身份门，不因“同名”而默认可替代。
- 外部ScanCode/Syft等代码适配存在，但本版启动配置关闭外部扫描器；不附其可执行文件，不声称本轮执行过。
- 不包含第三方视频、图片或字体文件。UI1首页使用代码绘制的HeroEvidenceScene，未使用旧HeroBackground媒体；旧视频/海报不分发。新增圆形箭头玻璃按钮的MIT许可与署名保存在application/frontend/UIVERSE_CSSBUTTONS_IO_LICENSE.txt及web/third-party-licenses.txt。没有新增运行依赖。

## 本次来源

完整P4应用来自本地workbench-full-rehearsal-20261116候选，包含Material Claims v3、Qwen修复及独立AI导出选择；上传选择修复来自workbench-upload-selection-fix-20261116。便携部署入口来自已有交付版，改为本包路径与完整P4配置。历史xzb资源下载贡献commit dae821df76c7ee530d13affc3f2d98f4b0d179ee及Owner UI线5656608d9d5dafebc9acdd44fa9fae4cf4acbb41仅为来源参考，不能作为本版完整commit。

测试中的虚构邮箱、/Users/synthetic路径、PRIVATE KEY头和token负例是拒绝测试文字，不是可用凭据。实际个人路径已移除。历史浏览器runner的Playwright模块路径改为显式OPENGUARD_PLAYWRIGHT_MODULE或包解析，原测试断言保留；它们未在本轮执行，不作为复现主入口。

## 随附前端许可证

- scheduler 0.27.0：MIT，`THIRD_PARTY_LICENSES/scheduler-0.27.0-LICENSE`
- vite 8.2.2：MIT，`THIRD_PARTY_LICENSES/vite-8.2.2-LICENSE.md`
- tailwindcss 4.3.3：MIT，`THIRD_PARTY_LICENSES/tailwindcss-4.3.3-LICENSE`
- react 19.2.8：MIT，`THIRD_PARTY_LICENSES/react-19.2.8-LICENSE`
- typescript 5.9.2：Apache-2.0，`THIRD_PARTY_LICENSES/typescript-5.9.2-LICENSE.txt`
- react-dom 19.2.8：MIT，`THIRD_PARTY_LICENSES/react-dom-19.2.8-LICENSE`

## UI1增量

2026-11-16录制UI来源上限3cee1edb160360b6dafc673f229bcd933a786887，主要视觉提交07b6e3d5061fa8dea277c91bd0b03c92da3ceabb，贡献者xzb123-hash；这些不是整个交付项目的commit。源代码与当前19380工作台相同，公开副本仅整理版本/验证文档，并不附本机为旧打开页面保留的两个未使用历史构建chunk；当前index/about使用的新JS/CSS保持原字节。
