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

from .models import Product
from .search import ProductSearchService
from .serializers import ProductSerializer

logger = logging.getLogger(__name__)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = (IsAuthenticated,)

    def _cache_key(self, suffix: str) -> str:
        return f"{connection.schema_name}:catalog:{suffix}"

    def get_queryset(self) -> QuerySet[Product]:
        return Product.objects.filter(is_active=True).order_by('-created_at')

    def list(self, request: Request, *args, **kwargs) -> Response:
        key = self._cache_key('products:list')
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, timeout=120)
        return response

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        key = self._cache_key(f"products:{kwargs['pk']}")
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().retrieve(request, *args, **kwargs)
        cache.set(key, response.data, timeout=120)
        return response

    def perform_create(self, serializer: ProductSerializer) -> None:
        product = serializer.save()
        self._invalidate_cache(product.id)

    def perform_update(self, serializer: ProductSerializer) -> None:
        product = serializer.save()
        self._invalidate_cache(product.id)

    def perform_destroy(self, instance: Product) -> None:
        product_id = instance.id
        instance.delete()
        self._invalidate_cache(product_id)

    def _invalidate_cache(self, product_id: int) -> None:
        cache.delete(self._cache_key('products:list'))
        cache.delete(self._cache_key(f'products:{product_id}'))

    @action(detail=False, methods=['get'])
    def search(self, request: Request) -> Response:
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'detail': 'Missing query parameter q'}, status=status.HTTP_400_BAD_REQUEST)

        digest = hashlib.sha1(query.lower().encode('utf-8')).hexdigest()
        cache_key = self._cache_key(f'products:search:{digest}')
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            product_ids = ProductSearchService().search(query)
        except Exception:
            logger.exception('Elasticsearch search failed')
            return Response({'detail': 'Search temporarily unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        queryset = Product.objects.filter(id__in=product_ids)
        ordered = sorted(queryset, key=lambda product: product_ids.index(product.id))
        data = ProductSerializer(ordered, many=True).data
        cache.set(cache_key, data, timeout=60)
        return Response(data)
