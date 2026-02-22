import logging
import hashlib

from django.core.cache import cache
from django.db import connection
from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .cache import CatalogCacheService
from .models import Product
from .search import ProductSearchService
from .serializers import ProductSerializer

logger = logging.getLogger(__name__)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = (IsAuthenticated,)

    def _cache_service(self) -> CatalogCacheService:
        return CatalogCacheService(connection.schema_name)

    def _cache_key(self, suffix: str) -> str:
        return self._cache_service().key(suffix)

    def get_queryset(self) -> QuerySet[Product]:
        return Product.objects.filter(is_active=True).order_by('-created_at')

    def list(self, request: Request, *args, **kwargs) -> Response:
        key = self._cache_service().product_list_key()
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, timeout=120)
        return response

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        key = self._cache_service().product_detail_key(kwargs['pk'])
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().retrieve(request, *args, **kwargs)
        cache.set(key, response.data, timeout=120)
        return response

    @action(detail=False, methods=['get'])
    def search(self, request: Request) -> Response:
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'detail': 'Missing query parameter q'}, status=status.HTTP_400_BAD_REQUEST)

        digest = hashlib.sha1(query.lower().encode('utf-8')).hexdigest()
        search_version = self._cache_service().get_search_version()
        cache_key = self._cache_key(f'products:search:v{search_version}:{digest}')
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            product_ids = ProductSearchService().search(query)
        except Exception:
            logger.exception('Elasticsearch search failed')
            return Response({'detail': 'Search temporarily unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        queryset = Product.objects.filter(id__in=product_ids, is_active=True)
        products_by_id = {product.id: product for product in queryset}
        ordered = [products_by_id[product_id] for product_id in product_ids if product_id in products_by_id]
        data = ProductSerializer(ordered, many=True).data
        cache.set(cache_key, data, timeout=60)
        return Response(data)
