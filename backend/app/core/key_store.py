"""
API Key 内存管理模块
- Key 只存储在内存中，进程重启即清除
- 不写入任何文件
"""
from typing import Dict, Optional
import threading


class KeyStore:
    """线程安全的 API Key 内存存储"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._keys: Dict[str, str] = {}
        return cls._instance

    def set_key(self, provider: str, api_key: str) -> None:
        """设置 provider 的 API Key"""
        with self._lock:
            self._keys[provider] = api_key

    def get_key(self, provider: str) -> Optional[str]:
        """获取 provider 的 API Key"""
        with self._lock:
            return self._keys.get(provider)

    def delete_key(self, provider: str) -> bool:
        """删除 provider 的 API Key"""
        with self._lock:
            if provider in self._keys:
                del self._keys[provider]
                return True
            return False

    def get_status(self) -> Dict[str, bool]:
        """获取所有 provider 的 Key 状态（有/无，不返回实际值）"""
        with self._lock:
            return {provider: True for provider in self._keys}

    def clear_all(self) -> None:
        """清除所有 Key"""
        with self._lock:
            self._keys.clear()


# 全局单例
key_store = KeyStore()


def get_api_key(provider: str, request_key: Optional[str] = None) -> Optional[str]:
    """
    获取 API Key，优先级：
    1. 请求传入的 Key (request_key)
    2. 内存缓存的 Key (key_store)

    不再从环境变量读取
    """
    # 优先使用请求传入的 Key
    if request_key and request_key.strip():
        return request_key.strip()

    # 其次使用内存缓存的 Key
    cached_key = key_store.get_key(provider)
    if cached_key:
        return cached_key

    return None
