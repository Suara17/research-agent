# 解决SearXNG 403 Forbidden问题

# 问题分析
# SearXNG的bot detection功能在private instance模式下仍然需要X-Forwarded-For或X-Real-IP头
# 即使设置了limiter: false和public_instance: false，某些保护机制仍然生效

# 解决方案1: 创建更完整的配置文件，明确禁用所有限制

# 首先备份当前配置
copy E:\Research_Agent\searxng-config\settings.yml E:\Research_Agent\searxng-config\settings.yml.backup

# 创建新的配置文件，完全禁用限制功能