"""
网络容错与回退策略模块 - 通用优化方案2
当主要数据源失败时，自动尝试多种替代方案
"""
import json
import re
from typing import Dict, List, Optional, Callable
from .utils import get_llm_client


class FallbackStrategy:
    """回退策略基类"""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority  # 数值越高优先级越高

    def can_handle(self, url: str, error_type: str) -> bool:
        """判断是否能处理该类型的失败"""
        raise NotImplementedError

    def execute(self, url: str, entity_name: str, search_func: Callable) -> Optional[Dict]:
        """执行回退策略"""
        raise NotImplementedError


class WikipediaInfoboxFallback(FallbackStrategy):
    """维基百科信息框回退策略"""

    def __init__(self):
        super().__init__("Wikipedia Infobox", priority=90)

    def can_handle(self, url: str, error_type: str) -> bool:
        # 适用于所有类型的访问失败
        return error_type in ["timeout", "ssl_error", "403", "404", "dns_error"]

    def execute(self, url: str, entity_name: str, search_func: Callable) -> Optional[Dict]:
        """搜索维基百科信息框"""
        try:
            print(f"[Fallback:Wikipedia] 尝试从Wikipedia获取 '{entity_name}' 的信息")

            # 生成Wikipedia搜索查询
            queries = [
                f'site:wikipedia.org "{entity_name}" infobox',
                f'site:en.wikipedia.org "{entity_name}"',
                f'site:wikipedia.org "{entity_name}" founded OR established OR opened'
            ]

            for query in queries:
                result = search_func(query=query)
                if result and "results" in result:
                    results_list = result.get("results", [])
                    if results_list:
                        print(f"[Fallback:Wikipedia] 成功找到 {len(results_list)} 个结果")
                        return {
                            "source": "wikipedia_fallback",
                            "strategy": self.name,
                            "results": results_list[:3],
                            "original_url": url
                        }

            return None

        except Exception as e:
            print(f"[Fallback:Wikipedia] 失败: {e}")
            return None


class WikidataFallback(FallbackStrategy):
    """Wikidata结构化数据回退策略"""

    def __init__(self):
        super().__init__("Wikidata", priority=85)

    def can_handle(self, url: str, error_type: str) -> bool:
        return error_type in ["timeout", "ssl_error", "403", "404", "dns_error"]

    def execute(self, url: str, entity_name: str, search_func: Callable) -> Optional[Dict]:
        """搜索Wikidata"""
        try:
            print(f"[Fallback:Wikidata] 尝试从Wikidata获取 '{entity_name}' 的结构化数据")

            queries = [
                f'site:wikidata.org "{entity_name}" inception',
                f'"{entity_name}" wikidata P571',  # P571 是 inception (成立日期) 的属性ID
            ]

            for query in queries:
                result = search_func(query=query)
                if result and "results" in result:
                    results_list = result.get("results", [])
                    if results_list:
                        return {
                            "source": "wikidata_fallback",
                            "strategy": self.name,
                            "results": results_list[:3],
                            "original_url": url
                        }

            return None

        except Exception as e:
            print(f"[Fallback:Wikidata] 失败: {e}")
            return None


class ArchiveOrgFallback(FallbackStrategy):
    """Internet Archive回退策略"""

    def __init__(self):
        super().__init__("Archive.org", priority=70)

    def can_handle(self, url: str, error_type: str) -> bool:
        # 仅用于404和内容已删除的情况
        return error_type in ["404", "410"]

    def execute(self, url: str, entity_name: str, search_func: Callable) -> Optional[Dict]:
        """搜索Internet Archive的存档版本"""
        try:
            print(f"[Fallback:Archive] 尝试从Archive.org获取 '{url}' 的历史快照")

            # 搜索该URL的存档
            archive_query = f'site:web.archive.org "{url}"'
            result = search_func(query=archive_query)

            if result and "results" in result:
                results_list = result.get("results", [])
                if results_list:
                    return {
                        "source": "archive_fallback",
                        "strategy": self.name,
                        "results": results_list[:3],
                        "original_url": url,
                        "hint": "这些是历史存档版本，信息可能不是最新的"
                    }

            return None

        except Exception as e:
            print(f"[Fallback:Archive] 失败: {e}")
            return None


class AlternativeSourceFallback(FallbackStrategy):
    """替代信息源回退策略"""

    def __init__(self):
        super().__init__("Alternative Sources", priority=80)

    def can_handle(self, url: str, error_type: str) -> bool:
        return True  # 总是可以尝试

    def execute(self, url: str, entity_name: str, search_func: Callable) -> Optional[Dict]:
        """搜索替代信息源"""
        try:
            print(f"[Fallback:AltSource] 搜索 '{entity_name}' 的替代信息源")

            # 根据实体类型生成不同的查询
            queries = self._generate_alternative_queries(entity_name, url)

            for query in queries:
                result = search_func(query=query)
                if result and "results" in result:
                    results_list = result.get("results", [])
                    if results_list:
                        return {
                            "source": "alternative_sources",
                            "strategy": self.name,
                            "results": results_list[:5],
                            "original_url": url
                        }

            return None

        except Exception as e:
            print(f"[Fallback:AltSource] 失败: {e}")
            return None

    def _generate_alternative_queries(self, entity_name: str, original_url: str) -> List[str]:
        """生成替代查询"""
        queries = []

        # 检测实体类型
        if "museum" in entity_name.lower():
            queries.extend([
                f'"{entity_name}" official website -site:{self._extract_domain(original_url)}',
                f'"{entity_name}" history opening date',
                f'"{entity_name}" visitor information',
            ])
        elif "stadium" in entity_name.lower() or "arena" in entity_name.lower():
            queries.extend([
                f'"{entity_name}" UEFA rating OR FIFA rating',
                f'"{entity_name}" capacity opened year',
                f'"{entity_name}" official venue information',
            ])
        elif "university" in entity_name.lower() or "college" in entity_name.lower():
            queries.extend([
                f'"{entity_name}" founded established',
                f'"{entity_name}" history timeline',
            ])
        else:
            # 通用查询
            queries.extend([
                f'"{entity_name}" about information',
                f'"{entity_name}" history background',
                f'"{entity_name}" official',
            ])

        return queries

    def _extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc
        except:
            return ""


class FallbackManager:
    """回退策略管理器"""

    def __init__(self):
        self.strategies = [
            WikipediaInfoboxFallback(),
            WikidataFallback(),
            AlternativeSourceFallback(),
            ArchiveOrgFallback(),
        ]
        # 按优先级排序
        self.strategies.sort(key=lambda x: x.priority, reverse=True)
        self.attempt_history = {}  # 记录尝试历史避免重复

    def handle_fetch_failure(
        self,
        url: str,
        entity_name: str,
        error_type: str,
        search_func: Callable
    ) -> Optional[Dict]:
        """
        处理网页抓取失败

        Args:
            url: 失败的URL
            entity_name: 目标实体名称
            error_type: 错误类型 (timeout, ssl_error, 403, 404, dns_error等)
            search_func: web_search函数引用

        Returns:
            成功时返回结果字典，失败返回None
        """
        print(f"[FallbackManager] 处理抓取失败: url={url}, error={error_type}")

        # 检查是否已经尝试过
        cache_key = f"{url}:{entity_name}"
        if cache_key in self.attempt_history:
            print(f"[FallbackManager] 该URL已尝试过回退策略，跳过")
            return None

        self.attempt_history[cache_key] = True

        # 尝试所有适用的策略
        for strategy in self.strategies:
            if not strategy.can_handle(url, error_type):
                continue

            print(f"[FallbackManager] 尝试策略: {strategy.name}")
            result = strategy.execute(url, entity_name, search_func)

            if result:
                print(f"[FallbackManager] 策略 {strategy.name} 成功!")
                return result

        print(f"[FallbackManager] 所有回退策略均失败")
        return None

    def clear_history(self):
        """清除尝试历史"""
        self.attempt_history.clear()


def detect_error_type(error_message: str) -> str:
    """
    从错误消息中检测错误类型

    Args:
        error_message: 错误消息字符串

    Returns:
        错误类型字符串
    """
    error_message_lower = error_message.lower()

    if "timeout" in error_message_lower or "timed out" in error_message_lower:
        return "timeout"
    elif "ssl" in error_message_lower or "certificate" in error_message_lower:
        return "ssl_error"
    elif "403" in error_message_lower or "forbidden" in error_message_lower:
        return "403"
    elif "404" in error_message_lower or "not found" in error_message_lower:
        return "404"
    elif "410" in error_message_lower or "gone" in error_message_lower:
        return "410"
    elif "dns" in error_message_lower or "resolve" in error_message_lower or "getaddrinfo failed" in error_message_lower:
        return "dns_error"
    elif "connection" in error_message_lower:
        return "connection_error"
    else:
        return "unknown"


def extract_entity_name_from_url(url: str) -> str:
    """
    从URL中提取实体名称

    例如: https://www.scottishfootballmuseum.org.uk/ -> Scottish Football Museum
    """
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc

        # 移除常见后缀
        domain = re.sub(r'\.(org|com|co|uk|net|edu|gov|io|ai).*$', '', domain)
        domain = domain.replace('www.', '')

        # 将连字符和下划线替换为空格
        name = domain.replace('-', ' ').replace('_', ' ')

        # 首字母大写
        name = ' '.join(word.capitalize() for word in name.split())

        return name
    except:
        return ""
