# openvp

两个独立的自动刷新流水线，互不联动：

1. **Cloudflare 边缘优选池**（`refresh_pool.py`）：每周从官方 IP 段采样测速，
   生成 `sub.txt`（vless 明文订阅）/ `clash.yaml`（Clash 订阅）。
2. **VPN Gate OpenVPN 节点提取**（`refresh_ovpn.py`）：每 30 分钟从 VPN Gate API
   解码 OpenVPN 配置，做 TCP 存活检查，生成 `openvpn.yaml`（Clash 订阅）。

数据文件只在工作流运行时生成，直接发布到 GitHub Pages，**不提交到仓库**
（仓库里只有脚本和页面源码，保持干净）。
`edge_pool.json` / `openvpn.json` 也会生成，仅供监控页读取，不作为下载提供。

## 源码文件（仓库里实际有的）

- `refresh_pool.py` — 优选池主脚本，只用 Python 标准库
- `refresh_ovpn.py` — OpenVPN 提取脚本，只用 Python 标准库
- `web/index.html` — 监控页（优选池 Top10 + OpenVPN 国家卡片）
- `.github/workflows/refresh.yml` — 唯一的工作流：每 30 分钟运行，
  每次刷新 OpenVPN 节点，仅周日 11:00（北京时间）刷新优选池，刷完自动发到 Pages

## 访问地址（GitHub Pages）

- https://gxjxzgx.github.io/openvp/ — 监控页
- https://gxjxzgx.github.io/openvp/sub.txt — CF 优选 vless 订阅（明文）
- https://gxjxzgx.github.io/openvp/clash.yaml — CF 优选 Clash 订阅
- https://gxjxzgx.github.io/openvp/openvpn.yaml — OpenVPN Clash 订阅

## 部署步骤

1. 仓库 Settings → Actions → General → Workflow permissions 选 **Read and write permissions**；
2. 仓库 Settings → Secrets and variables → Actions → New repository secret：
   - `EDT_DOMAIN`：你的 edgetunnel 域名（优选池 SNI 测试用）；
   - `EDT_UUID`：你的 edgetunnel UUID（生成 `sub.txt` / `clash.yaml` 用）；
3. **手动**在 GitHub 网页创建 `.github/workflows/refresh.yml`
   （App 没有 workflows 权限，API 推不上去，内容就是本目录同名文件）。
4. 到 Actions 页手动点一次 Run workflow，确认成功。

说明：本仓库与 `gxjxzgx/gate`（SSTP 节点检测）互不联动，各自独立运行。
