# cf-edge-pool

Cloudflare 边缘优选池自动刷新。数据源是 Cloudflare 官方公布的 IP 段，
每周自动采样、测速，保留延迟最低的一批 IP，替代手动维护的优选域名列表。

## 文件

- `refresh_pool.py` — 主脚本，只用 Python 标准库，无第三方依赖
- `edge_pool.txt` — 生成的优选池（`IP:443` 每行一个），可直接用作 edgetunnel 自定义优选
- `edge_pool.json` — 同上，带延迟等元数据
- `sub.txt` — vless 订阅（需配置 `EDT_UUID` secret）：每个池子 IP 一条直连节点，
  `vless://UUID@IP:443?security=tls&type=ws&sni=你的域名&path=/video/`，客户端直接导入即用
- `.github/workflows/refresh.yml` — 每周自动刷新 + 手动触发

## 工作原理

1. 拉取 `https://www.cloudflare.com/ips-v4` 和 `/ips-v6`（官方段，保证都是 CF 边缘）；
2. 按网段大小加权随机采样（默认 300 个 IP）；
3. 64 并发对每个 IP 做 443 端口 TLS 握手，SNI 用你自己的域名——
   握手成功即证明该 IP 是可用 CF 边缘，记录握手延迟；
4. 按延迟排序取前 N 个（默认 40），写入 `edge_pool.txt` / `edge_pool.json` 并提交。

## 部署步骤

1. 在 GitHub 新建公开仓库（名字随意，如 `cf-edge-pool`），把本目录所有文件推上去；
2. 仓库 Settings → Actions → General → Workflow permissions 选 **Read and write permissions**；
3. 仓库 Settings → Secrets and variables → Actions → New repository secret，
   建 `EDT_DOMAIN`，值填你自己的 edgetunnel 域名（SNI 测试用）；
4. **手动**在 GitHub 网页创建 `.github/workflows/refresh.yml`
   （App 没有 workflows 权限，API 推不上去，内容就是本目录同名文件）；
5. 到 Actions 页手动点一次 Run workflow，确认 `edge_pool.txt` 生成成功。

之后每周日 11:00（北京时间）自动刷新一次；池子变化时自动提交，
没变化则跳过。

## 与 gate 联动（下一步）

gate 仓库的 `vpngate.py` 可以加一个 `POOL_URL`（指向
`https://raw.githubusercontent.com/gxjxzgx/openvp/main/edge_pool.txt`），
每次检测时先拉这个池子作为优选入口，拉不到再回退到内置的 `EDGE_HOSTS`。
等这个仓库建好推上去后，我来改 gate 那边。
