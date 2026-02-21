# SearXNG 自建实例使用指南

## 概述

本文档详细介绍如何使用部署在ECS上的SearXNG搜索实例。该实例已配置Xray代理，可直接访问海外搜索引擎（Google、DuckDuckGo等）。

---

## 服务器信息

| 项目 | 值 |
|-----|-----|
| 服务器IP | 116.62.78.162 |
| SSH端口 | 22 |
| SearXNG端口 | 8080 |
| SearXNG访问地址 | http://116.62.78.162:8080/ |
| 用户名 | root |
| SSH密钥 | `C:\Users\forzr\es.pem` |

---

## 快速开始

### 直接访问SearXNG

打开浏览器访问: **http://116.62.78.162:8080**

> ✅ **无需本地代理**: 服务器已配置Xray代理，可直接访问Google等海外搜索引擎

---

## 网络架构

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

## 搜索引擎使用

### 可用引擎 - 通用搜索

| 引擎 | Engine | Shortcut | 状态 | 说明 |
|-----|--------|----------|------|------|
| **Bing** | bing | bi | ✅ 正常 | 必应搜索（国内可用） |
| **DuckDuckGo** | duckduckgo | ddg | ✅ 正常 | 通过代理访问 |
| **Google** | google | go | ✅ 正常 | 通过代理访问 |

### 可用引擎 - 图片搜索

| 引擎 | Engine | Shortcut | 状态 | 说明 |
|-----|--------|----------|------|------|
| **Bing Images** | bing_images | bii | ✅ 正常 | 必应图片 |
| **Google Images** | google_images | goi | ✅ 正常 | 通过代理访问 |

### 可用引擎 - 视频搜索

| 引擎 | Engine | Shortcut | 状态 | 说明 |
|-----|--------|----------|------|------|
| **YouTube** | youtube | yt | ✅ 正常 | 通过代理访问 |
| **PeerTube** | peertube | pt | ✅ 正常 | 去中心化视频 |
| **Vimeo** | vimeo | vm | ✅ 正常 | 通过代理访问 |

### 可用引擎 - IT/代码搜索

| 引擎 | Engine | Shortcut | 状态 | 说明 |
|-----|--------|----------|------|------|
| **GitHub** | github | gh | ✅ 正常 | 代码仓库搜索 |
| **AskUbuntu** | askubuntu | ubuntu | ✅ 正常 | Ubuntu问答 |
| **SuperUser** | superuser | su | ✅ 正常 | 技术问答 |

### 可用引擎 - 学术搜索

| 引擎 | Engine | Shortcut | 状态 | 说明 |
|-----|--------|----------|------|------|
| **arXiv** | arxiv | arx | ✅ 正常 | 学术论文预印本 |
| **Google Scholar** | google_scholar | gos | ✅ 正常 | 学术搜索 |
| **PubMed** | pubmed | pub | ✅ 正常 | 生物医学文献 |
| **Semantic Scholar** | semantic_scholar | se | ✅ 正常 | 学术搜索 |

### 可用引擎 - 百科

| 引擎 | Engine | Shortcut | 状态 | 说明 |
|-----|--------|----------|------|------|
| **Wikipedia** | wikipedia | wp | ✅ 正常 | 维基百科 |
| **Wikidata** | wikidata | wd | ✅ 正常 | 结构化数据 |

### 已禁用引擎

| 引擎 | Engine | 原因 |
|-----|--------|------|
| Brave | brave | 崩溃 (unexpected crash) |
| Qwant | qwant | 解析错误 (parsing error) |
| Startpage | startpage | 无结果返回 |
| Yahoo | yahoo | 无结果返回 |
| Reddit | reddit | 访问被拒绝 (access denied) |
| Dailymotion | dailymotion | 崩溃 (unexpected crash) |

---

## 推荐引擎组合

| 场景 | 推荐引擎 | 说明 |
|------|---------|------|
| 通用搜索 | bing,duckduckgo,google | 综合结果最佳 |
| 代码搜索 | github,askubuntu,superuser | IT相关问题 |
| 学术搜索 | arxiv,google scholar,pubmed | 论文和研究 |
| 视频搜索 | youtube,peertube,vimeo | 视频内容 |
| 图片搜索 | bing images,google images | 图片搜索 |

---

## 搜索优化技巧

### 1. 使用分类过滤

```
# 科学搜索
?q=machine+learning&category=science

# IT/技术搜索  
?q=python+tutorial&category=it

# 图片搜索
?q=landscape&category=images
```

### 2. 指定语言

```
# 英文结果
?q=python+tutorial&language=en

# 中文结果
?q=人工智能&language=zh
```

### 3. 高级搜索语法

```
# 精确匹配
q="exact phrase"

# 排除关键词
q=python -javascript

# 指定网站
q=site:github.com searxng

# 指定文件类型
q=filetype:pdf machine learning
```

### 4. 选择特定引擎

```
# 只用Bing
q=test&engines=bing

# 只用Google
q=python&engines=google

# 只用GitHub
q=searxng&engines=github

# 只用arXiv
q=neural+network&engines=arxiv

# 组合多个引擎
q=python&engines=bing,duckduckgo,github
```

---

## API调用方式

### JSON格式搜索

```bash
# 基本搜索
curl "http://116.62.78.162:8080/search?q=python&format=json"

# 测试Google搜索
curl "http://116.62.78.162:8080/search?q=python&engines=google&format=json"

# 测试多个引擎
curl "http://116.62.78.162:8080/search?q=python&engines=bing,duckduckgo,github&format=json"

# 测试学术搜索
curl "http://116.62.78.162:8080/search?q=machine+learning&engines=arxiv,google_scholar&format=json"
```

### Python代码示例

```python
import requests

SEARXNG_URL = "http://116.62.78.162:8080"

# 搜索请求
response = requests.get(
    f"{SEARXNG_URL}/search",
    params={
        "q": "python tutorial",
        "format": "json",
        "engines": "bing,duckduckgo,google"
    },
    timeout=30
)

results = response.json()
for result in results.get("results", [])[:5]:
    print(f"- {result['title']}: {result['url']}")
```

---

## Docker管理

### 查看容器状态

```bash
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "docker ps | grep -E 'searxng|xray'"
```

### 重启服务

```bash
# 重启SearXNG
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "docker restart searxng-remote"

# 重启Xray代理
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "docker restart xray"
```

### 查看日志

```bash
# SearXNG日志
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "docker logs searxng-remote --tail 50"

# Xray日志
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "docker logs xray --tail 50"
```

### 测试代理连通性

```bash
# 在服务器上测试SOCKS5代理
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "curl -x socks5://127.0.0.1:1080 https://www.google.com -I"

# 测试HTTP代理
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "curl -x http://127.0.0.1:1081 https://www.google.com -I"
```

---

## 故障排除

### 问题1：搜索超时

可能原因：
- Xray代理容器未运行
- 代理配置问题

解决步骤：
1. 检查Xray容器状态: `docker ps | grep xray`
2. 检查SearXNG容器状态: `docker ps | grep searxng`
3. 测试代理连通性: `curl -x socks5://127.0.0.1:1080 https://www.google.com -I`
4. 查看日志排查问题

### 问题2：特定引擎无结果

某些引擎可能被禁用或有临时问题：
- 检查是否在已禁用列表中
- 尝试使用替代引擎

### 问题3：无法连接到服务器

检查：
1. 网络连接是否正常
2. 服务器是否在线
3. 防火墙是否开放8080端口

### 问题4：TLS证书错误

如果日志显示TLS handshake failed，确保Xray配置中的`serverName`为`n2.gladns.com`。

---

## 常见问题

### Q: 为什么现在不需要SSH隧道了？

A: 服务器已部署Xray代理，SearXNG通过本地SOCKS5代理(127.0.0.1:1080)访问海外网站，无需再从本地转发流量。

### Q: 代理服务使用的是什么协议？

A: 使用Trojan + gRPC + TLS协议，订阅服务为GLaDOS。

### Q: 可以同时运行多个搜索请求吗？

A: 可以，SearXNG支持并发搜索请求。配置中已设置：
- pool_connections: 100
- pool_maxsize: 20

### Q: 如何更新SearXNG版本？

A: 拉取最新镜像并重新创建容器：
```bash
ssh -i "C:\Users\forzr\es.pem" root@116.62.78.162 "docker pull searxng/searxng:latest"
# 然后重新创建容器
```

### Q: 配置文件在哪里？

A: 
- SearXNG配置: `/opt/searxng/searxng/settings.yml`
- Xray配置: `/opt/xray/config.json`

---

## 相关文件

- SSH密钥: `C:\Users\forzr\es.pem`
- 本项目配置目录: `E:\Research_Agent\`
- 详细配置说明: `E:\Research_Agent\SearXNG代理配置说明.md`

---

*最后更新: 2026-02-20*