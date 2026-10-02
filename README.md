# openvp

两个独立的自动刷新流水线，互不联动：

1. **Cloudflare 边缘优选池**（`refresh_pool.py`）：每周从官方 IP 段采样测速，
   生成 `edge_pool.txt` / `edge_pool.json` / `sub.txt`（vless 订阅）。
2. **VPN Gate OpenVPN 节点提取**（`refresh_ovpn.py`）：每 30 分钟从 VPN Gate API
   解码 OpenVPN 配置，做 TCP 存活检查，打包 `openvpn.zip` + 索引 `openvpn.txt`。

## 文件

- `refresh_pool.py` — 优选池主脚本，只用 Python 标准库
- `edge_pool.txt` — 优选池（`IP:443` 每行一个），可直接用作 edgetunnel 自定义优选
- `edge_pool.json` — 同上，带延迟等元数据
- `sub.txt` — vless 订阅（需配置 `EDT_UUID` secret）：每个池子 IP 一条直连节点，
  `vless://UUID@IP:443?security=tls&type=ws&sni=你的域名&path=/video/`，客户端直接导入即用
- `refresh_ovpn.py` — OpenVPN 提取脚本，只用 Python 标准库
- `openvpn.zip` — 全部可用 OpenVPN 配置打包（每 30 分钟刷新）
- `openvpn.txt` — OpenVPN 节点索引清单（文件名 | 国家 | 地址:端口）
- `openvpn.yaml` — Clash 可直接用的 OpenVPN 订阅（`proxies:` 列表，证书用 YAML 锚点复用）
- `.github/workflows/refresh.yml` — 唯一的工作流：每 30 分钟运行，
  每次刷新 OpenVPN 节点，仅周日 11:00（北京时间）刷新优选池，刷完自动发到 Pages

## 访问地址（GitHub Pages，和 gate 一样）

- https://gxjxzgx.github.io/openvp/edge_pool.txt
- https://gxjxzgx.github.io/openvp/sub.txt
- https://gxjxzgx.github.io/openvp/openvpn.zip
- https://gxjxzgx.github.io/openvp/openvpn.txt
- https://gxjxzgx.github.io/openvp/openvpn.yaml

## 部署步骤

1. 仓库 Settings → Actions → General → Workflow permissions 选 **Read and write permissions**；
2. 仓库 Settings → Secrets and variables → Actions → New repository secret：
   - `EDT_DOMAIN`：你的 edgetunnel 域名（优选池 SNI 测试用）；
   - `EDT_UUID`：你的 edgetunnel UUID（生成 `sub.txt` 用）；
3. **手动**在 GitHub 网页创建 `.github/workflows/refresh.yml`
   （App 没有 workflows 权限，API 推不上去，内容就是本目录同名文件）；
   如果之前建过 `refresh-ovpn.yml` / `deploy-pages.yml`，把那两个删掉，
   只留这一个。
4. 到 Actions 页手动点一次 Run workflow，确认成功。

说明：本仓库与 `gxjxzgx/gate`（SSTP 节点检测）互不联动，各自独立运行。
