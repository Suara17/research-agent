# SearXNG 搜索引擎配置和优化总结

## 1. 问题概述
SearXNG实例在API访问时遇到403 Forbidden错误，这是由于SearXNG的bot detection机制，即使在私有实例模式下也会检查X-Forwarded-For或X-Real-IP头。

## 2. 解决方案实施

### 2.1 代码层面修复
修改了 `research_agent/search.py` 文件中的 `_safe_search_searxng` 函数，添加了适当的HTTP头：

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'X-Forwarded-For': '127.0.0.1',
    'X-Real-IP': '127.0.0.1',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
}
```

### 2.2 配置层面修复
在 `searxng/settings.yml` 中进行了以下配置：

- 设置 `limiter: false` 完全禁用速率限制器
- 设置 `public_instance: false` 确保私有实例模式
- 在 `formats` 中添加 `json` 支持API返回JSON格式
- 添加bot detection配置禁用各项检测功能

### 2.3 启用常用搜索引擎
启用了以下常用的搜索引擎：

- **通用搜索引擎**: google, bing, duckduckgo, yandex, yahoo, brave, qwant, startpage
- **图片搜索引擎**: google images, bing images, duckduckgo images, yandex images, flickr, imgur, pixabay, unsplash
- **视频搜索引擎**: youtube, dailymotion, vimeo, google videos, bing videos, duckduckgo videos
- **新闻搜索引擎**: google news, bing news, duckduckgo news, yahoo news, qwant news
- **学术搜索引擎**: google scholar, arxiv, pubmed, semantic scholar
- **维基类引擎**: wikipedia, wikidata, wikinews, wikiquote, wiktionary
- **代码平台**: github, gitlab, stackoverflow, askubuntu, superuser
- **社交媒体**: reddit, hackernews, lobste.rs
- **音乐引擎**: soundcloud, bandcamp, mixcloud, yandex music

## 3. 验證結果

✅ **API访问正常** - 直接访问 `http://localhost:8083/search?q=test&format=json` 返回200状态码
✅ **Python函数正常工作** - `_safe_search_searxng` 函数返回结果
✅ **返回有效JSON数据** - 包含来自多个引擎的搜索结果
✅ **配置正确应用** - settings.yml和代码修复均已生效
✅ **多引擎支持** - 从响应头可见使用了多个搜索引擎

## 4. 技术细节

- **修复前**: API访问返回403 Forbidden错误
- **修复后**: API访问返回200 OK，返回有效的JSON搜索结果
- **搜索质量**: 返回高质量的搜索结果，包含来自多个引擎的数据
- **响应时间**: 虽然由于多引擎查询有一定延迟，但功能正常

## 5. 结论

通过组合使用客户端HTTP头添加和服务器配置优化的方案，成功解决了SearXNG私有实例API访问的403错误问题。此修复方案既保证了客户端的兼容性，又优化了服务器配置，实现了稳定可靠的API访问。

该修复方案采用方案2（在Research Agent代码中添加适当的HTTP头），这是最实用和便捷的解决方案，无需复杂的反向代理配置。