#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VPN Gate OpenVPN 节点自动提取。

数据源 : http://www.vpngate.net/api/iphone/ (官方 CSV, 含 OpenVPN 配置 base64)
流程   : 拉取 API -> 解码每个服务器的 OpenVPN 配置 -> 提取 remote 地址/端口/协议
          -> 并发 TCP 检查端口可达性 -> 打包 openvpn.zip + 索引 openvpn.txt

只用标准库, 无第三方依赖。

环境变量:
  OVPN_CHECK_TIMEOUT  选填, 单节点 TCP 检查超时秒数, 默认 5
  OVPN_WORKERS        选填, 并发线程数, 默认 32
  OVPN_MAX            选填, 最多保留 N 个 (0 = 全部), 默认 0
  OUT_DIR             选填, 输出目录, 默认脚本所在目录
  VPNGATE_API         选填, 官方 API 地址
  VPNGATE_MIRROR      选填, 官方失败时的回退镜像
"""

import base64
import csv
import json
import os
import re
import socket
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

VPNGATE_API = os.environ.get("VPNGATE_API", "http://www.vpngate.net/api/iphone/")
VPNGATE_MIRROR = os.environ.get(
    "VPNGATE_MIRROR",
    "https://raw.githubusercontent.com/fdciabdul/Vpngate-Scraper-API/main/json/data.json",
)
BEIJING = timezone(timedelta(hours=8))
HTTP_TIMEOUT = 30

REMOTE_RE = re.compile(r"^remote\s+(\S+)\s+(\d+)", re.M)
PROTO_RE = re.compile(r"^proto\s+(\S+)", re.M)
# zip 包时间戳固定, 内容不变时 git diff 无差异, 避免无意义提交
ZIP_DATE = (2020, 1, 1, 0, 0, 0)


def log(msg):
    print(f"[ovpn] {msg}", flush=True)


def die(msg):
    print(f"[ovpn] 致命错误: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; openvp-ovpn)"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def parse_csv_rows(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    hi = next((i for i, ln in enumerate(lines) if ln.lstrip("#").startswith("HostName")), None)
    if hi is None:
        raise RuntimeError("找不到 CSV 表头行 (HostName)")
    header = lines[hi].lstrip("#").split(",")
    idx = {h.strip().lstrip("*").lower(): i for i, h in enumerate(header)}
    rows = []
    for row in csv.reader(lines[hi + 1:]):
        try:
            rows.append({
                "host": row[idx["hostname"]],
                "ip": row[idx["ip"]],
                "country_long": row[idx["countrylong"]],
                "country_short": row[idx["countryshort"]],
                "config_b64": row[idx["openvpn_configdata_base64"]],
            })
        except (IndexError, KeyError):
            continue
    return rows


def parse_mirror_rows(data):
    items = data if isinstance(data, list) else [data]
    servers = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("servers"), list):
            servers.extend(item["servers"])
        elif isinstance(item, dict):
            servers.append(item)
    rows = []
    for s in servers:
        host = str(s.get("hostname") or s.get("host") or "").strip()
        ip = str(s.get("ip") or "").strip()
        if not host or not ip:
            continue
        rows.append({
            "host": host,
            "ip": ip,
            "country_long": str(s.get("countrylong") or s.get("country_long") or s.get("country") or ""),
            "country_short": str(s.get("countryshort") or s.get("country_short") or ""),
            "config_b64": str(s.get("openvpn_configdata_base64") or s.get("config_b64") or ""),
        })
    return rows


def fetch_rows():
    try:
        log(f"拉取官方 API: {VPNGATE_API}")
        rows = parse_csv_rows(http_get(VPNGATE_API))
        if rows:
            log(f"官方 API 拿到 {len(rows)} 行")
            return rows
        raise RuntimeError("官方 API 返回 0 行")
    except Exception as exc:
        log(f"官方 API 失败: {exc}, 尝试回退镜像")
    try:
        rows = parse_mirror_rows(json.loads(http_get(VPNGATE_MIRROR)))
        if rows:
            log(f"回退镜像拿到 {len(rows)} 行")
            return rows
        raise RuntimeError("回退镜像返回 0 行")
    except Exception as exc:
        die(f"官方 API 与回退镜像均失败: {exc}")


def extract_nodes(rows):
    nodes, seen = [], set()
    for r in rows:
        b64 = (r.get("config_b64") or "").strip()
        if not b64:
            continue
        try:
            cfg = base64.b64decode(b64, validate=False).decode("utf-8", "replace")
        except Exception:
            continue
        m = REMOTE_RE.search(cfg)
        if not m:
            continue
        rh, rp = m.group(1), int(m.group(2))
        pm = PROTO_RE.search(cfg)
        proto = pm.group(1).lower() if pm else "udp"
        key = (rh.lower(), rp, proto)
        if key in seen:
            continue
        seen.add(key)
        nodes.append({
            "country_long": r.get("country_long", ""),
            "country_short": r.get("country_short", ""),
            "remote_host": rh,
            "remote_port": rp,
            "proto": proto,
            "config": cfg,
        })
    return nodes


def tcp_ok(node, timeout):
    try:
        with socket.create_connection((node["remote_host"], node["remote_port"]), timeout=timeout):
            return True
    except Exception:
        return False


def check_nodes(nodes, timeout, workers):
    alive = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(tcp_ok, n, timeout): n for n in nodes}
        for fut in as_completed(futs):
            if fut.result():
                alive.append(futs[fut])
    alive.sort(key=lambda n: (n["country_short"], n["remote_host"], n["remote_port"]))
    return alive


def write_outputs(nodes, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    now = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")
    counters = {}
    index_lines = [
        "# VPN Gate OpenVPN 节点 (自动刷新, 每 30 分钟重新提取)",
        f"# 更新时间: {now} (北京时间)",
        f"# 共 {len(nodes)} 个 (已做 TCP 端口可达检查)",
        "# 文件名 | 国家 | 连接地址:端口 (协议)",
        "# 下载 openvpn.zip 解压, 导入客户端即用",
    ]
    entries = []
    for n in nodes:
        cs = re.sub(r"\W+", "", n["country_short"]) or "XX"
        counters[cs] = counters.get(cs, 0) + 1
        fname = f"{cs}-{counters[cs]:02d}.ovpn"
        entries.append((fname, n))
        index_lines.append(
            f"{fname} | {n['country_long']} | {n['remote_host']}:{n['remote_port']} ({n['proto']})"
        )
    zip_path = os.path.join(out_dir, "openvpn.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, n in entries:
            zi = zipfile.ZipInfo(fname, date_time=ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, n["config"])
    txt_path = os.path.join(out_dir, "openvpn.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines) + "\n")
    return zip_path, txt_path


def main():
    timeout = float(os.environ.get("OVPN_CHECK_TIMEOUT", "5"))
    workers = int(os.environ.get("OVPN_WORKERS", "32"))
    max_n = int(os.environ.get("OVPN_MAX", "0"))
    out_dir = os.environ.get("OUT_DIR", os.path.dirname(os.path.abspath(__file__)))

    log("== 1/3 拉取 VPN Gate 数据 ==")
    rows = fetch_rows()

    log("== 2/3 提取 OpenVPN 配置 ==")
    nodes = extract_nodes(rows)
    log(f"提取到 {len(nodes)} 个节点")
    if not nodes:
        die("没有提取到任何 OpenVPN 节点, 拒绝提交空结果")

    log(f"== 3/3 TCP 可达检查 (超时 {timeout}s, 并发 {workers}) ==")
    alive = check_nodes(nodes, timeout, workers)
    log(f"可达: {len(alive)}/{len(nodes)}")
    if not alive:
        die("TCP 检查后剩余 0 个可用节点, 拒绝提交空结果")
    if max_n > 0:
        alive = alive[:max_n]

    zip_path, txt_path = write_outputs(alive, out_dir)
    log(f"已写入 {zip_path} / {txt_path} ({len(alive)} 个节点)")


if __name__ == "__main__":
    main()
