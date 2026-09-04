# 第三方资源台账

正式台账字段：

| 名称 | 类型 | 版本/提交 | 官方来源 | 许可证/授权 | 使用方式 | 关键义务 | 自研边界 | 合规状态 | 开放方式 |
|---|---|---|---|---|---|---|---|---|---|
| React Flow (@xyflow/react) | 前端图谱库 | 12.11.6 | https://reactflow.dev/learn | MIT | 懒加载缩放/平移/节点交互；不复制 Pro 模板 | 保留许可与版权声明 | 风险/证据关联及业务 UI 自行实现 | 已登记，待团队复核 | 锁文件安装；声明随静态站点发布 |
| React Flow 运行时依赖 | npm 包 | 详见 frontend/public/THIRD_PARTY_NOTICES.txt | 各上游链接见声明文件 | MIT / ISC / BSD-3-Clause | @xyflow/system、Zustand、classcat、D3、use-sync-external-store | 保留各包授权文本；不将上游代码计为自研 | 仅通用交互基础库 | 已核对安装包声明 | 声明随静态站点发布 |

2026-09-03 前端记录：React / ReactDOM / scheduler 的运行时声明也一并保留。完整使用边界见 frontend/THIRD_PARTY_UI.md；构建工具及既有资源的全项目台账仍需各负责人持续维护，本记录不代表完成整仓合规审计。

所有依赖、模型、数据、框架、组件、工具、素材和第三方服务在首次引入时登记，不在提交前集中补录。
