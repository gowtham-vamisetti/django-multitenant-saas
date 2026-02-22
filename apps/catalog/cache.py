import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


class CatalogCacheService:
    """
    Centralizes catalog cache key generation and invalidation logic.
    """

    def __init__(self, schema_name: str | None) -> None:
        self.schema_name = schema_name or 'public'

    def key(self, suffix: str) -> str:
        return f'{self.schema_name}:catalog:{suffix}'

    def product_list_key(self) -> str:
        return self.key('products:list')

    def product_detail_key(self, product_id: int | str) -> str:
        return self.key(f'products:{product_id}')

    def search_version_key(self) -> str:
        return self.key('products:search:version')

    def get_search_version(self) -> int:
        version = cache.get(self.search_version_key())
        if version is None:
            cache.set(self.search_version_key(), 1, timeout=None)
            return 1
        try:
            return int(version)
        except (TypeError, ValueError):
            cache.set(self.search_version_key(), 1, timeout=None)
            return 1

    def bump_search_version(self) -> int:
        version_key = self.search_version_key()
        try:
            return int(cache.incr(version_key))
        except ValueError:
            current = self.get_search_version()
            next_version = current + 1
            cache.set(version_key, next_version, timeout=None)
            return next_version
        except Exception:
            logger.exception('Failed to bump search cache version for schema=%s', self.schema_name)
            return self.get_search_version()

    def invalidate_product_change(self, product_id: int) -> None:
        cache.delete(self.product_list_key())
        cache.delete(self.product_detail_key(product_id))
        self.bump_search_version()
