# Research Agent 部署到阿里云EAS指南

## 概述

本文档介绍如何将Research Agent（集成了SearXNG搜索功能的LLM Agent）部署到阿里云PAI-EAS服务。

## 重要提醒：EAS网络访问配置

**注意：根据阿里云EAS服务的安全策略，EAS实例默认无法访问公网。如需访问百炼大模型API或其他公网服务，必须配置VPC以允许公网访问。**

## 项目架构

Research Agent是一个基于LLM的智能搜索代理，主要特性包括：

- 集成SearXNG作为主要搜索API
- 多层搜索策略（SearXNG优先，其他提供商回退）
- 网页内容提取和智能总结功能
- 基于FastAPI的Web服务接口

## 部署前准备

### 1. 确保SearXNG实例可通过公网访问

由于EAS默认无法访问公网，您需要确保SearXNG实例可以通过公网访问：

**选项A：本地SearXNG公网暴露**
- 使用内网穿透工具（如frp、ZeroTier、ngrok等）
- 将本地SearXNG服务映射到公网可访问的地址

**选项B：云端SearXNG部署**
- 将SearXNG部署到阿里云ECS或容器服务
- 与EAS部署在同一VPC内（推荐）

**测试SearXNG实例可达性：**
```bash
# 测试公网可访问的SearXNG实例
curl "http://your-public-searxng-domain:8080/search?q=test&format=json"
```

### 2. 准备API密钥

- 阿里云DashScope API密钥（用于LLM调用）
- 其他搜索API密钥（可选，作为SearXNG的回退选项）

### 3. VPC网络配置准备

由于EAS默认无法访问公网，您需要提前准备好VPC配置：
- VPC实例
- NAT网关（用于公网访问）
- 安全组规则（允许访问百炼API和SearXNG服务）

## 部署步骤

### 步骤1：准备部署包

确保以下文件在项目根目录中：

```
project/
├── agent.py              # 主入口文件（必需）
├── agent_loop.py         # Agent核心循环
├── research_agent/       # 核心模块目录
│   ├── search.py         # 搜索功能（包含SearXNG集成）
│   ├── content_enhancer.py # 内容增强功能
│   └── ...
├── requirements.txt      # 依赖文件
├── README.md             # 说明文档
└── ...
```

### 步骤2：配置VPC网络（必需）

**由于EAS默认无法访问公网，必须先配置VPC：**

1. **创建或选择现有VPC**
   - 确保VPC中有可用的交换机（subnet）
   
2. **配置NAT网关**
   - 创建NAT网关并绑定弹性公网IP
   - 配置SNAT规则允许EAS访问公网

3. **配置安全组**
   - 允许出站流量到百炼API（`dashscope.aliyuncs.com:443`）
   - 允许出站流量到SearXNG服务地址和端口

### 步骤3：上传到EAS

1. 登录阿里云控制台，进入PAI-EAS服务
2. 点击"创建在线服务"
3. 选择"通过部署包创建"
4. 上传项目ZIP压缩包

### 步骤4：配置服务参数

#### 基础配置
- **服务名称**：输入有意义的服务名称
- **实例规格**：建议选择至少2C4G规格以支持搜索和LLM调用
- **实例数量**：建议初始设置为1个实例
- **网络配置**：选择已配置好的VPC和交换机

#### 环境变量配置
在"环境配置"中添加以下环境变量：

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| SEARXNG_BASE_URL | SearXNG实例的基础URL（公网可访问地址） | http://your-searxng-domain:8080 |
| DASHSCOPE_API_KEY | 阿里云DashScope API密钥 | sk-xxxxxx |
| ENHANCE_SEARCH_CONTENT | 是否启用搜索结果内容增强 | true |
| SERPER_API_KEY | Serper API密钥（可选，回退用） | xxxxxx |

#### 启动命令
```
python agent.py
```

或者使用uvicorn：
```
uvicorn agent:app --host 0.0.0.0 --port 8000
```

### 步骤5：部署服务

1. 点击"部署"按钮开始部署
2. 等待部署完成（通常需要几分钟）
3. 查看部署日志确认服务正常启动

## 验证部署

### 1. 检查服务状态

部署完成后，在EAS控制台查看服务状态是否为"运行中"。

### 2. 测试API接口

获取服务的Endpoint和Token，然后进行测试：

```bash
# 测试普通接口
curl -X POST "https://[your-endpoint]/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer [your-token]" \
  -d '{"question": "今天天气如何？"}'
```

### 3. 验证SearXNG集成

在服务日志中确认SearXNG搜索请求是否正常发出和接收。

## 常见问题及解决方案

### 问题1：VPC配置相关错误

**现象**：服务启动失败，提示网络连接错误

**解决方案**：
1. 确认VPC配置正确，包含有效的交换机
2. 检查NAT网关是否正确配置并绑定公网IP
3. 确认安全组规则允许出站流量到百炼API（443端口）和SearXNG服务

### 问题2：SearXNG连接失败

**现象**：日志显示无法连接到SearXNG实例

**解决方案**：
1. 检查`SEARXNG_BASE_URL`环境变量是否正确
2. 确认SearXNG实例可以从公网访问
3. 检查安全组是否允许访问SearXNG的端口
4. 验证SearXNG服务是否正常运行

### 问题3：百炼API调用失败

**现象**：LLM调用返回网络错误

**解决方案**：
1. 检查`DASHSCOPE_API_KEY`环境变量
2. 确认VPC安全组允许访问百炼API（`dashscope.aliyuncs.com:443`）
3. 确认API密钥余额充足
4. 检查API调用频率限制

### 问题4：API调用超时

**现象**：搜索请求长时间无响应

**解决方案**：
1. 在SearXNG配置中增加超时时间
2. 检查网络连接稳定性
3. 调整EAS实例规格以获得更好性能
4. 确认VPC网络配置正确

## 性能优化建议

### 1. 缓存策略
- 启用搜索结果缓存以减少重复请求
- 使用内容缓存避免重复提取网页内容

### 2. 并发设置
- 根据负载情况调整并发请求数量
- 合理设置连接池大小

### 3. 资源配置
- 根据QPS需求调整实例规格
- 监控资源使用情况并适时调整

## 监控和维护

### 日志监控
- 定期检查EAS服务日志
- 监控SearXNG请求成功率
- 跟踪LLM调用次数和费用

### 性能指标
- 响应时间
- 错误率
- 吞吐量（QPS）

## 安全建议

1. 保护API密钥，不要硬编码在代码中
2. 使用HTTPS加密传输
3. 限制服务访问权限
4. 定期轮换API密钥
5. 配置安全组规则，限制不必要的网络访问
6. 使用最小权限原则配置VPC访问策略

## 更新和维护

### 代码更新
1. 修改代码后重新打包
2. 在EAS控制台上传新版本
3. 执行滚动更新以避免服务中断

### 配置更新
- 可以直接修改环境变量配置
- 修改后重启服务使配置生效

## VPC网络配置详细说明

### NAT网关配置
1. **创建NAT网关**
   - 选择可用区和VPC
   - 绑定弹性公网IP
   
2. **配置SNAT条目**
   - 指定源网段（EAS所在交换机网段）
   - 指定公网IP（绑定的弹性公网IP）

### 安全组配置
1. **出站规则配置**
   - 协议类型：TCP
   - 端口：443（百炼API）
   - 目标：`dashscope.aliyuncs.com`
   
   - 协议类型：TCP  
   - 端口：SearXNG服务端口（通常是80或443）
   - 目标：SearXNG服务公网地址

### 路由表配置
1. **添加默认路由**
   - 目标网段：0.0.0.0/0
   - 下一跳：NAT网关

## 联系支持

如遇到部署问题，请参考：
- 阿里云EAS官方文档
- 本项目GitHub Issues
- 联系技术支持团队