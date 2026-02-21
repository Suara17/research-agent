# 如何部署自己的SearXNG实例

## 概述

SearXNG是一个开源的元搜索引擎，允许您部署自己的隐私友好的搜索实例。以下是详细的部署指南。

## 部署方式

### 方式1：Docker部署（推荐）

#### 1. 安装Docker
确保系统已安装Docker和Docker Compose

#### 2. 创建项目目录
```bash
mkdir searxng-docker
cd searxng-docker
```

#### 3. 创建docker-compose.yml文件
```yaml
version: '3.7'
services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8080:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=https://your-domain.com/
      - SEARXNG_PORT=8080
      - SEARXNG_BIND_ADDRESS=0.0.0.0
    restart: unless-stopped
```

#### 4. 初始化配置
```bash
# 创建配置目录
mkdir searxng

# 获取默认配置文件
docker run --rm -e "SEARXNG_PORT=8080" -v "$PWD/searxng:/etc/searxng" searxng/searxng:latest sh -c "searxng-check-instance-settings --create-settings /etc/searxng/settings.yml"

# 或者手动创建配置
docker run --rm searxng/searxng:latest sh -c "cat /etc/searxng/settings.yml" > searxng/settings.yml
```

#### 5. 启动服务
```bash
docker-compose up -d
```

### 方式2：直接Docker运行
```bash
docker run -d --name searxng \
  -p 8080:8080 \
  -v ./searxng:/etc/searxng \
  -e SEARXNG_BASE_URL=http://localhost:8080/ \
  -e SEARXNG_PORT=8080 \
  searxng/searxng:latest
```

### 方式3：源码部署

#### 1. 安装依赖
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y git build-essential libxml2-dev libxslt1-dev lib32z1-dev \
    python3 python3-dev python3-setuptools python3-pip python3-cffi \
    libcairo2 libjpeg-dev libgif-dev libffi-dev

# CentOS/RHEL/Fedora
sudo yum install -y git gcc libxml2-devel libxslt-devel python3 python3-devel \
    python3-pip python3-cffi cairo-devel libjpeg-turbo-devel giflib-devel \
    libffi-devel
```

#### 2. 克隆源码
```bash
git clone https://github.com/searxng/searxng.git
cd searxng
```

#### 3. 安装Python依赖
```bash
python3 -m pip install --user -r requirements.txt
```

#### 4. 生成配置文件
```bash
python3 -m searxng webapp --set-secret-key
```

#### 5. 启动服务
```bash
python3 -m searxng webapp
```

## 配置优化

### 1. 编辑settings.yml配置文件
```yaml
general:
  debug: false
  instance_name: "My SearXNG Instance"

server:
  port: 8080
  bind_address: "127.0.0.1"
  secret_key: "your-secret-key-here"  # 生成一个安全的密钥
  base_url: false  # 或设置为 "https://your-domain.com/"

ui:
  static_use_hash: false

search:
  safe_search: 0  # 0: disabled, 1: moderate, 2: strict
  max_page: 0
  default_lang: "auto"  # 设置默认语言

engines:
  - name: google
    shortcut: g
    disabled: false
  - name: duckduckgo
    shortcut: d
    disabled: false
  # 根据需要启用/禁用引擎

outgoing:
  request_timeout: 3.00  # 增加超时时间
  max_request_timeout: 10.0
```

### 2. 生成安全密钥
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 反向代理配置

### Nginx配置示例
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Apache配置示例
```apache
<VirtualHost *:80>
    ServerName your-domain.com
    
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8080/
    ProxyPassReverse / http://127.0.0.1:8080/
    
    # 设置请求头
    RequestHeader set X-Forwarded-Proto "http"
</VirtualHost>
```

## 安全配置

### 1. 限制访问
- 使用防火墙限制访问端口
- 配置访问控制列表
- 启用HTTPS

### 2. 防止滥用
```yaml
# 在settings.yml中配置
server:
  limiter: true  # 启用请求限制
  public_instance: true  # 如果是公共实例

redis:
  url: redis://localhost:6379/0  # 需要Redis服务
```

### 3. 配置robots.txt
在web根目录放置robots.txt文件：
```
User-agent: *
Disallow: /
```

## 性能优化

### 1. 启用缓存
```yaml
redis:
  url: redis://localhost:6379/0

# 或使用其他缓存后端
cache:
  type: redis  # 或 'memcached'
```

### 2. 调整超时设置
```yaml
outgoing:
  request_timeout: 5.00  # 增加请求超时时间
  max_request_timeout: 15.0  # 最大超时时间
```

## 监控和维护

### 1. 日志配置
```yaml
logging:
  version: 1
  disable_existing_loggers: false
  formatters:
    simple:
      format: '%(asctime)-15s %(levelname)-8s %(name)s:%(lineno)s %(message)s'
  handlers:
    console:
      class: logging.StreamHandler
      formatter: simple
      level: INFO
  loggers:
    searxng:
      level: INFO
      handlers: [console]
      propagate: false
```

### 2. 定期更新
```bash
# Docker方式
docker pull searxng/searxng:latest
docker-compose up -d

# 源码方式
git pull origin master
pip install -r requirements.txt --upgrade
```

## 故障排除

### 常见问题
1. **端口冲突** - 检查端口是否已被占用
2. **权限问题** - 确保配置文件有正确权限
3. **网络问题** - 检查防火墙和网络连接

### 调试命令
```bash
# 检查配置
docker exec -it searxng searxng-check-instance-settings

# 查看日志
docker logs searxng

# 交互式调试
docker exec -it searxng bash
```

## 与Research Agent集成

### 1. 设置环境变量
```bash
export SEARXNG_BASE_URL="http://your-searxng-instance.com"
```

### 2. 验证连接
```bash
curl "http://your-searxng-instance.com/search?q=test&format=json"
```

通过部署自己的SearXNG实例，您可以获得更好的性能、可靠性和控制权，避免公共实例的限制和不稳定问题。