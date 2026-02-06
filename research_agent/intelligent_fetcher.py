"""
智能网络请求模块
实现失败分类、自适应重试、域名黑名单等机制
"""
import time
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


class DomainStatus:
    """域名状态管理"""

    def __init__(self):
        self.status_cache: Dict[str, Dict[str, Any]] = {}
        self.cooldown_period = 300  # 5分钟冷却期

    def is_blocked(self, domain: str) -> bool:
        """检查域名是否在黑名单中"""
        if domain not in self.status_cache:
            return False

        status = self.status_cache[domain]
        if status['state'] == 'unreachable':
            # 检查冷却期
            if time.time() - status['last_failure'] < self.cooldown_period:
                return True

        return False

    def mark_unreachable(self, domain: str, reason: str, error_type: str):
        """标记域名为不可达"""
        self.status_cache[domain] = {
            'state': 'unreachable',
            'last_failure': time.time(),
            'reason': reason,
            'error_type': error_type
        }
        logger.warning(f"Domain {domain} marked as unreachable: {error_type} - {reason}")

    def mark_reachable(self, domain: str):
        """标记域名为可达"""
        self.status_cache[domain] = {
            'state': 'reachable',
            'last_success': time.time()
        }

    def get_recommended_timeout(self, domain: str, attempt: int) -> int:
        """获取推荐的超时时间"""
        # 首次尝试：5秒快速失败
        # 后续尝试：逐渐增加
        base_timeout = 5
        return min(base_timeout + attempt * 5, 15)  # 最多15秒


class ErrorClassifier:
    """错误分类器"""

    # 永久性错误：立即放弃
    PERMANENT_ERRORS = {
        'SSLError': 'SSL握手失败',
        'SSLEOFError': 'SSL连接中断',
        'NameResolutionError': 'DNS解析失败',
        'ConnectionRefusedError': '连接被拒绝',
        '404': '页面不存在',
        '403': '禁止访问',
        '401': '需要认证',
        '410': '资源已删除',
    }

    # 暂时性错误：可以重试
    TRANSIENT_ERRORS = {
        'ConnectionError': '网络连接问题',
        'Timeout': '请求超时',
        'ReadTimeout': '读取超时',
        'ConnectTimeout': '连接超时',
        '503': '服务不可用',
        '502': '网关错误',
        '429': '请求过多',
        '500': '服务器内部错误',
    }

    @classmethod
    def classify(cls, exception: Exception) -> str:
        """
        分类错误类型

        Returns:
            'PERMANENT': 永久性错误，不应重试
            'TRANSIENT': 暂时性错误，可以重试
            'UNKNOWN': 未知错误
        """
        error_str = str(exception)
        error_class = exception.__class__.__name__

        # 检查永久性错误
        for keyword in cls.PERMANENT_ERRORS.keys():
            if keyword in error_class or keyword in error_str:
                return 'PERMANENT'

        # 检查暂时性错误
        for keyword in cls.TRANSIENT_ERRORS.keys():
            if keyword in error_class or keyword in error_str:
                return 'TRANSIENT'

        return 'UNKNOWN'

    @classmethod
    def get_error_description(cls, exception: Exception) -> str:
        """获取错误的友好描述"""
        error_class = exception.__class__.__name__

        # 先检查永久性错误
        for keyword, description in cls.PERMANENT_ERRORS.items():
            if keyword in error_class or keyword in str(exception):
                return description

        # 再检查暂时性错误
        for keyword, description in cls.TRANSIENT_ERRORS.items():
            if keyword in error_class or keyword in str(exception):
                return description

        return f"未知错误: {error_class}"


class IntelligentFetcher:
    """
    智能网络请求器

    功能：
    1. 失败类型分类（永久性/暂时性）
    2. 自适应重试（指数退避）
    3. 域名黑名单管理
    4. 快速失败（避免长时间等待）
    """

    def __init__(self):
        self.domain_status = DomainStatus()
        self.error_classifier = ErrorClassifier()

        # 预定义的问题域名（从日志中提取）
        self.initialize_known_problematic_domains()

    def initialize_known_problematic_domains(self):
        """初始化已知的问题域名"""
        problematic_domains = [
            'nationalminingmuseum.org.uk',  # SSL频繁失败
            'www.nationalminingmuseum.org.uk',
            'instagram.com',  # 连接超时
            'www.instagram.com',
            'facebook.com',  # 连接超时
            'www.facebook.com',
            'www.cia.gov',  # 已有黑名单
            'www.state.gov',  # 已有黑名单
        ]

        for domain in problematic_domains:
            self.domain_status.mark_unreachable(
                domain,
                "Known problematic domain from historical data",
                "PRECONFIGURED"
            )

    def should_attempt_fetch(self, url: str) -> tuple[bool, Optional[str]]:
        """
        判断是否应该尝试获取URL

        Returns:
            (should_fetch, skip_reason)
        """
        domain = urlparse(url).netloc

        if self.domain_status.is_blocked(domain):
            status = self.domain_status.status_cache[domain]
            reason = f"Domain blocked: {status['error_type']} - {status['reason']}"
            return False, reason

        return True, None

    def fetch_with_retry(
        self,
        url: str,
        session,
        max_retries: int = 1,  # 默认只重试1次
        verify_ssl: bool = False
    ) -> tuple[Optional[requests.Response], Optional[str]]:
        """
        带智能重试的网络请求

        Args:
            url: 目标URL
            session: requests.Session对象
            max_retries: 最大重试次数（默认1次，比原来的3次减少）
            verify_ssl: 是否验证SSL证书

        Returns:
            (response, error_message)
        """
        domain = urlparse(url).netloc

        for attempt in range(max_retries + 1):
            # 自适应超时
            timeout = self.domain_status.get_recommended_timeout(domain, attempt)

            try:
                logger.debug(f"Fetching {url} (attempt {attempt + 1}/{max_retries + 1}, timeout={timeout}s)")

                response = session.get(
                    url,
                    timeout=timeout,
                    verify=verify_ssl
                )
                response.raise_for_status()

                # 成功 → 标记域名为可达
                self.domain_status.mark_reachable(domain)
                return response, None

            except Exception as e:
                error_type = self.error_classifier.classify(e)
                error_desc = self.error_classifier.get_error_description(e)

                logger.info(f"Fetch error for {url}: {error_desc} (type={error_type})")

                # 永久性错误 → 立即放弃
                if error_type == 'PERMANENT':
                    self.domain_status.mark_unreachable(domain, str(e), error_type)
                    return None, f"Permanent error: {error_desc}"

                # 暂时性错误 → 判断是否继续重试
                elif error_type == 'TRANSIENT':
                    if attempt < max_retries:
                        wait_time = min(2 ** attempt, 5)  # 指数退避，最多等5秒
                        logger.info(f"Transient error, retrying after {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return None, f"Max retries reached: {error_desc}"

                # 未知错误 → 谨慎重试一次
                else:
                    if attempt == 0:
                        logger.warning(f"Unknown error, trying once more: {e}")
                        continue
                    else:
                        return None, f"Unknown error: {str(e)}"

        return None, "All retry attempts failed"


# 全局单例
_intelligent_fetcher = None

def get_intelligent_fetcher() -> IntelligentFetcher:
    """获取智能请求器的全局单例"""
    global _intelligent_fetcher
    if _intelligent_fetcher is None:
        _intelligent_fetcher = IntelligentFetcher()
    return _intelligent_fetcher
