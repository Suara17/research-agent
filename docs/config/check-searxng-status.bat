@echo off
echo SearXNG for Research Agent - 状态检查
echo ==========================================

docker ps -f name=searxng-agent

echo.
echo 访问地址: http://localhost:8083
echo.
echo 要停止服务，运行: docker stop searxng-agent
echo 要重启服务，运行: docker restart searxng-agent
echo.
pause