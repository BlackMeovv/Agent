# 服务器部署指南（在线 Demo）

目标：把 DeepQuery 部署到你自己的服务器上，简历里放一个链接 + 访问口令，
面试官/HR 打开就能真实提问。全程约 10 分钟。

## 0. 前提

- 一台能访问外网的 Linux 服务器（1核2G 足够），已安装 Docker 与 compose 插件
- 验证：`docker compose version` 能输出版本号
- 服务器安全组/防火墙放行你要用的端口（默认 8000）

## 1. 拉代码

```bash
git clone https://github.com/BlackMeovv/Agent.git
cd Agent
```

## 2. 配置 .env

```bash
cp .env.example .env
vim .env
```

必改四项：

```
LLM_API_KEY=你的key
LLM_BASE_URL=你的中转地址/v1
LLM_MODEL=模型名
DEMO_ACCESS_CODE=给面试官的访问口令
```

公网演示建议：

- **口令必配**。配了之后提问与记忆读写都要口令，前端会自动弹窗询问并记住；
  不配等于把你的 API Key 开放给全网刷
- **模型选快的便宜的**（如 deepseek-chat）。演示场景 5 秒出结果比 40 秒的
  推理模型体验好得多，效果差距在演示库这种难度下几乎看不出来
- 保留 `AGENT_MAX_COST_PER_RUN` 预算熔断，单次提问花费有上限

## 3. 启动

只起应用和缓存（演示够用，省内存）：

```bash
docker compose up -d --build app redis
```

想要完整监控大盘（Prometheus + Grafana）就全起：

```bash
docker compose up -d --build
```

首次构建约 3-5 分钟（含 Vue 前端构建）。起来后：

```bash
curl http://localhost:8000/healthz
```

看到 `"ok":true,"protected":true` 即成功。浏览器打开
`http://服务器IP:8000`，输入口令即可提问。

## 4. 域名 + HTTPS（可选，更体面）

有域名的话加一层 nginx 反代，简历上的链接就是 `https://dq.你的域名`：

```nginx
server {
    server_name dq.example.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

注意 `proxy_buffering off` 与长超时——SSE 流式必需，否则运行过程不会实时推送。
证书用 certbot 一条命令：`certbot --nginx -d dq.example.com`。

## 5. 日常运维

```bash
docker compose logs -f app
git pull
docker compose up -d --build app
docker compose down
```

依次是：看日志、更新代码后重建、整体下线。数据（演示库/记忆/图表）在
named volume `app-data` 里，重建不丢。

## 6. 安全边界（面试可讲）

- 数据库三重只读 + AST 守卫，演示库随时可由 `deepquery.demo_data` 重新生成，
  没有可损毁的东西
- 访问口令用 `hmac.compare_digest` 比较（防时序侧信道）；因 SSE 的
  EventSource 无法携带自定义请求头，口令走查询参数——这也是为什么建议上 HTTPS
- 图表代码在容器内以 subprocess + rlimit 执行，容器本身是隔离边界
- 预算熔断兜底：口令泄露最坏情况也只是有限的 API 花费
- 表级权限：`.env` 配 `ALLOWED_TABLES=orders,products` 可让公开演示只暴露
  部分表——schema 注入、守卫白名单、前端库表树、MCP 工具同步过滤
