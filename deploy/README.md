# 部署目标

比赛版提供 Docker Compose 单机部署：

- `web`：前端；
- `api`：FastAPI；
- `scanner`：受限扫描进程；
- `ollama`：可选本地模型服务；
- `data`：SQLite 和缓存卷。

不得把 API 密钥写入镜像、仓库、演示视频或报告。
