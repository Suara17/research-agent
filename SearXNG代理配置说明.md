# SearXNG 代理配置说明

## 概述

本文档记录了 SearXNG 在远程服务器上的配置修改，以及如何通过 Xray 代理实现对海外搜索引擎（Google、DuckDuckGo 等）的访问。

---

## 服务器信息

- **服务器 IP**: 116.62.78.162
- **SearXNG 端口**: 8080
- **SearXNG 访问地址**: http://116.62.78.162:8080/

---

## 一、SearXNG 配置

### 1.1 部署位置

```
/opt/searxng/searxng/settings.yml
```

### 1.2 当前配置的搜索引擎

#### 通用搜索
| 搜索引擎 | Engine | Shortcut | 状态 | 说明 |
|---------|--------|----------|------|------|
| Bing | bing | bi | ✅ 正常 | 必应搜索（国内可用） |
| DuckDuckGo | duckduckgo | ddg | ✅ 正常 | 通过代理访问 |
| Google | google | go | ✅ 正常 | 通过代理访问 |

#### 图片搜索
| 搜索引擎 | Engine | Shortcut | 状态 | 说明 |
|---------|--------|----------|------|------|
| Bing Images | bing_images | bii | ✅ 正常 | 必应图片 |
| Google Images | google_images | goi | ✅ 正常 | 通过代理访问 |

#### 视频搜索
| 搜索引擎 | Engine | Shortcut | 状态 | 说明 |
|---------|--------|----------|------|------|
| YouTube | youtube | yt | ✅ 正常 | 通过代理访问 |
| PeerTube | peertube | pt | ✅ 正常 | 去中心化视频 |
| Vimeo | vimeo | vm | ✅ 正常 | 通过代理访问 |

#### IT/代码搜索
| 搜索引擎 | Engine | Shortcut | 状态 | 说明 |
|---------|--------|----------|------|------|
| GitHub | github | gh | ✅ 正常 | 代码仓库搜索 |
| AskUbuntu | askubuntu | ubuntu | ✅ 正常 | Ubuntu问答 |
| SuperUser | superuser | su | ✅ 正常 | 技术问答 |

#### 学术搜索
| 搜索引擎 | Engine | Shortcut | 状态 | 说明 |
|---------|--------|----------|------|------|
| arXiv | arxiv | arx | ✅ 正常 | 学术论文预印本 |
| Google Scholar | google_scholar | gos | ✅ 正常 | 学术搜索 |
| PubMed | pubmed | pub | ✅ 正常 | 生物医学文献 |
| Semantic Scholar | semantic_scholar | se | ✅ 正常 | 学术搜索 |

#### 百科
| 搜索引擎 | Engine | Shortcut | 状态 | 说明 |
|---------|--------|----------|------|------|
| Wikipedia | wikipedia | wp | ✅ 正常 | 维基百科 |
| Wikidata | wikidata | wd | ✅ 正常 | 结构化数据 |

#### 已禁用的引擎
| 搜索引擎 | Engine | 原因 |
|---------|--------|------|
| Brave | brave | 崩溃 (unexpected crash) |
| Qwant | qwant | 解析错误 (parsing error) |
| Startpage | startpage | 无结果返回 |
| Yahoo | yahoo | 无结果返回 |
| Reddit | reddit | 访问被拒绝 (access denied) |
| Dailymotion | dailymotion | 崩溃 (unexpected crash) |

### 1.3 配置文件内容

```yaml
use_default_settings: true

general:
  debug: false
  instance_name: SearXNG Remote

server:
  port: 8080
  bind_address: "0.0.0.0"
  base_url: "http://116.62.78.162:8080/"
  limiter: false
  secret_key: "searxng_remote_secret_key_2024"

search:
  safe_search: 0
  formats:
    - html
    - json
  default_lang: all

outgoing:
  request_timeout: 15.0
  max_request_timeout: 30.0
  pool_connections: 100
  pool_maxsize: 20
  proxies:
    http://:
      - socks5://127.0.0.1:1080
    https://:
      - socks5://127.0.0.1:1080

engines:
  # 通用搜索
  - name: bing
    engine: bing
    shortcut: bi
    timeout: 8.0

  - name: google
    engine: google
    shortcut: go
    timeout: 12.0

  - name: duckduckgo
    engine: duckduckgo
    shortcut: ddg
    timeout: 12.0

  # 图片搜索
  - name: bing images
    engine: bing_images
    shortcut: bii
    timeout: 8.0

  - name: google images
    engine: google_images
    shortcut: goi
    timeout: 12.0

  # 视频搜索
  - name: youtube
    engine: youtube
    shortcut: yt
    timeout: 12.0

  - name: peertube
    engine: peertube
    shortcut: pt
    timeout: 12.0

  - name: vimeo
    engine: vimeo
    shortcut: vm
    timeout: 10.0

  # IT/代码搜索
  - name: github
    engine: github
    shortcut: gh
    timeout: 10.0

  - name: askubuntu
    engine: askubuntu
    shortcut: ubuntu
    timeout: 10.0

  - name: superuser
    engine: superuser
    shortcut: su
    timeout: 10.0

  # 学术搜索
  - name: arxiv
    engine: arxiv
    shortcut: arx
    timeout: 15.0

  - name: google scholar
    engine: google_scholar
    shortcut: gos
    timeout: 15.0

  - name: pubmed
    engine: pubmed
    shortcut: pub
    timeout: 15.0

  # 百科
  - name: wikipedia
    engine: wikipedia
    shortcut: wp
    timeout: 10.0

  - name: wikidata
    engine: wikidata
    shortcut: wd
    timeout: 10.0

  # 禁用不可用的引擎
  - name: brave
    engine: brave
    disabled: true

  - name: qwant
    engine: qwant
    disabled: true

  - name: startpage
    engine: startpage
    disabled: true

  - name: yahoo
    engine: yahoo
    disabled: true

  - name: reddit
    engine: reddit
    disabled: true

  - name: dailymotion
    engine: dailymotion
    disabled: true
```

### 1.4 关键配置说明

- **limiter: false** - 禁用速率限制，提高搜索效率
- **proxies** - 配置所有出站请求使用本地 SOCKS5 代理
- **request_timeout: 15.0** - 请求超时设置为 15 秒（适合代理环境）
- **max_request_timeout: 30.0** - 最大请求超时 30 秒
- **disabled: true** - 禁用不可用的搜索引擎

---

## 二、Xray 代理配置

### 2.1 部署位置

```
/opt/xray/config.json
```

### 2.2 代理服务信息

- **订阅服务**: GLaDOS
- **协议**: Trojan + gRPC + TLS
- **SOCKS5 端口**: 1080
- **HTTP 代理端口**: 1081

### 2.3 Xray 配置文件

```json
{
  "inbounds": [
    {
      "port": 1080,
      "listen": "0.0.0.0",
      "protocol": "socks",
      "settings": {
        "udp": true
      }
    },
    {
      "port": 1081,
      "listen": "0.0.0.0",
      "protocol": "http"
    }
  ],
  "outbounds": [
    {
      "protocol": "trojan",
      "settings": {
        "servers": [
          {
            "address": "2ac4b5f.ha.glados-config.com",
            "port": 443,
            "password": "301ccd4869dc04cf"
          }
        ]
      },
      "streamSettings": {
        "network": "grpc",
        "security": "tls",
        "tlsSettings": {
          "serverName": "n2.gladns.com"
        },
        "grpcSettings": {
          "serviceName": "db",
          "mode": "gun"
        }
      }
    }
  ]
}
```

### 2.4 关键配置说明

- **serverName**: 必须使用 `n2.gladns.com`（不是 `n2.gladns.net`）
- **grpcSettings**: 使用 gRPC 传输模式
- **inbounds**: 提供 SOCKS5 和 HTTP 两种代理接口

### 2.5 Docker 运行命令

```bash
docker run -d \
  --name xray \
  --restart always \
  --network host \
  -v /opt/xray/config.json:/etc/xray/config.json \
  teddysun/xray
```

---

## 三、网络架构

```
┌─────────────────────────────────────────────────────────────┐
│                     SearXNG 容器                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  搜索请求 → 使用代理 socks5://127.0.0.1:1080        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Xray 容器 (Host 网络)                    │
│  ┌─────────────────┐    ┌─────────────────────────────┐    │
│  │ SOCKS5 :1080    │───▶│ Trojan + gRPC + TLS         │    │
│  │ HTTP   :1081    │    │ → GLaDOS 服务器              │    │
│  └─────────────────┘    └─────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  海外搜索引擎    │
                    │  Google, DDG... │
                    └─────────────────┘
```

---

## 四、常用运维命令

### 4.1 查看服务状态

```bash
# 查看容器状态
docker ps | grep -E "searxng|xray"

# 查看 SearXNG 日志
docker logs searxng-remote --tail 50

# 查看 Xray 日志
docker logs xray --tail 50
```

### 4.2 重启服务

```bash
# 重启 SearXNG
docker restart searxng-remote

# 重启 Xray
docker restart xray
```

### 4.3 测试代理连通性

```bash
# 测试 SOCKS5 代理
curl -x socks5://127.0.0.1:1080 https://www.google.com -I

# 测试 HTTP 代理
curl -x http://127.0.0.1:1081 https://www.google.com -I
```

### 4.4 测试 SearXNG 搜索

```bash
# JSON 格式搜索测试
curl "http://116.62.78.162:8080/search?q=test&format=json" | jq '.results | length'

# 测试 Google 搜索
curl "http://116.62.78.162:8080/search?q=python&engines=google&format=json" | jq '.results[:3]'

# 测试多个引擎
curl "http://116.62.78.162:8080/search?q=python&engines=bing,duckduckgo,github&format=json" | jq '.results[:3]'

# 测试学术搜索
curl "http://116.62.78.162:8080/search?q=machine learning&engines=arxiv,google scholar&format=json" | jq '.results[:3]'
```

---

## 五、故障排除

### 5.1 代理连接失败

**症状**: Google 等海外搜索引擎超时

**排查步骤**:
1. 检查 Xray 容器是否运行: `docker ps | grep xray`
2. 测试代理连通性: `curl -x socks5://127.0.0.1:1080 https://www.google.com -I`
3. 查看 Xray 日志: `docker logs xray --tail 50`

### 5.2 TLS 证书错误

**症状**: 日志显示 TLS handshake failed

**解决方案**: 确保 `serverName` 配置为 `n2.gladns.com`

### 5.3 SearXNG 无法启动

**症状**: 容器反复重启

**排查步骤**:
1. 检查配置文件格式: `cat /opt/searxng/searxng/settings.yml`
2. 查看错误日志: `docker logs searxng-remote`

---

## 六、本地调用方式

在 `research_agent/search.py` 中，SearXNG 通过以下方式调用：

```python
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://116.62.78.162:8080")

# 搜索请求
response = requests.get(
    f"{SEARXNG_URL}/search",
    params={
        "q": query,
        "format": "json",
        "engines": "bing,duckduckgo,google"
    },
    timeout=30
)
```

### 推荐的引擎组合

| 场景 | 推荐引擎 | 说明 |
|------|---------|------|
| 通用搜索 | bing,duckduckgo,google | 综合结果最佳 |
| 代码搜索 | github,askubuntu,superuser | IT相关问题 |
| 学术搜索 | arxiv,google scholar,pubmed | 论文和研究 |
| 视频搜索 | youtube,peertube,vimeo | 视频内容 |
| 图片搜索 | bing images,google images | 图片搜索 |

---

## 更新记录

| 日期 | 修改内容 |
|------|---------|
| 2024-02-19 | 初始配置，部署 SearXNG |
| 2024-02-19 | 安装 Xray 代理，配置 Trojan+gRPC |
| 2024-02-19 | 修复 TLS 证书域名（n2.gladns.com） |
| 2024-02-19 | 将 SearXNG 改为 host 网络模式 |
| 2024-02-19 | 配置全局 SOCKS5 代理（127.0.0.1:1080） |
| 2024-02-19 | 测试确认 Bing、DuckDuckGo、GitHub、Wikipedia 可用 |
| 2026-02-19 | 全面测试所有搜索引擎可用性 |
| 2026-02-19 | 增加 request_timeout 到 15 秒，max_request_timeout 到 30 秒 |
| 2026-02-19 | 启用 DuckDuckGo、PeerTube、AskUbuntu、SuperUser |
| 2026-02-19 | 禁用 Brave、Qwant、Startpage、Yahoo、Reddit、Dailymotion |
| 2026-02-19 | 确认 Google、Google Images、arXiv、YouTube 正常可用 |
| 2026-02-19 | 添加推荐引擎组合说明 |
