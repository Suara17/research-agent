# 由于SearXNG的bot detection机制导致的403错误解决方案

# 问题分析：
# SearXNG的bot detection功能在private instance模式下仍然需要X-Forwarded-For或X-Real-IP头
# 即使设置了limiter: false和public_instance: false，某些保护机制仍然生效

# 解决方案：
# 使用Nginx作为反向代理，添加必要的HTTP头信息

# 1. 首先，停止当前的SearXNG容器
docker stop searxng-agent

# 2. 重新启动SearXNG容器，但只绑定到本地端口（不暴露到外部）
docker run -d --name searxng-agent-internal -p 127.0.0.1:8080:8080 -v E:\Research_Agent\searxng-config:/etc/searxng -e SEARXNG_BASE_URL=http://localhost:8083/ -e SEARXNG_PORT=8080 -e SEARXNG_LIMITER=false -e SEARXNG_PUBLIC_INSTANCE=false searxng/searxng:latest

# 3. 创建Nginx配置文件
# nginx.conf内容：
events {
    worker_connections 1024;
}

http {
    upstream searxng_backend {
        server 127.0.0.1:8080;
    }

    server {
        listen 8083;
        server_name localhost;

        location / {
            proxy_pass http://searxng_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $server_name;
        }
    }
}

# 4. 使用Nginx作为反向代理
# docker run -d --name nginx-proxy -p 8083:8083 -v /path/to/nginx.conf:/etc/nginx/nginx.conf:ro nginx:alpine

# 5. 或者，我们可以尝试使用Docker网络和自定义headers
# 但这可能需要更复杂的配置