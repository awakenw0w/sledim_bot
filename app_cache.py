import time
from typing import Any, Callable

# Словрь для хранения кэшей. Формат: { cache_name: { key: (value, expire_at) } }
_caches: dict[str, dict[str, tuple[Any, float]]] = {}


def ttl_cache(ttl_seconds: float = 60.0):
    """
    Декоратор для асинхронных функций, реализующий in-memory TTL кэш.
    Имя кэша генерируется автоматически на основе модуля и имени функции.
    """
    def decorator(func: Callable):
        cache_name = f"{func.__module__}.{func.__name__}"
        _caches[cache_name] = {}
        
        async def wrapper(*args):
            # Простой ключ по всем позиционным аргументам (хватает для ID чата)
            cache_key = str(args)
            now = time.time()
            
            cache_store = _caches[cache_name]
            
            if cache_key in cache_store:
                val, expire_at = cache_store[cache_key]
                if now < expire_at:
                    return val
                else:
                    # Экспирация
                    del cache_store[cache_key]
                    
            # Если нет в кэше или протухло -- вызываем оригинал
            result = await func(*args)
            cache_store[cache_key] = (result, now + ttl_seconds)
            return result
            
        # Привязываем метод инвалидации
        wrapper.invalidate = lambda *k_args: _caches[cache_name].pop(str(k_args), None)
        return wrapper
    return decorator


def invalidate_cache(func: Callable, *args):
    """Инвалидирует кэш конкретной функции для конкретных аргументов."""
    if hasattr(func, "invalidate"):
        func.invalidate(*args)
