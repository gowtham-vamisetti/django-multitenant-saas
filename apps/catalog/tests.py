from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from . import signals
from .search import ProductSearchService
from .views import ProductViewSet


class ProductSecurityTests(SimpleTestCase):
    def test_viewset_requires_authentication(self):
        self.assertEqual(ProductViewSet.permission_classes, (IsAuthenticated,))

    def test_list_endpoint_requires_authentication(self):
        request = APIRequestFactory().get('/api/catalog/products/')
        response = ProductViewSet.as_view({'get': 'list'})(request)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class ProductCachingTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ProductViewSet()

    @patch('apps.catalog.views.cache.get', return_value=[{'id': 1, 'name': 'Cached'}])
    @patch('apps.catalog.views.viewsets.ModelViewSet.list')
    @patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:list')
    def test_list_endpoint_uses_cache_on_hit(self, _cache_key_mock, super_list_mock, _cache_get_mock):
        request = self.factory.get('/api/catalog/products/')
        response = self.view.list(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 1, 'name': 'Cached'}])
        super_list_mock.assert_not_called()

    @patch('apps.catalog.views.cache.set')
    @patch('apps.catalog.views.cache.get', return_value=None)
    @patch('apps.catalog.views.viewsets.ModelViewSet.list', return_value=Response([{'id': 2, 'name': 'DB'}]))
    @patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:list')
    def test_list_endpoint_sets_cache_on_miss(self, _cache_key_mock, _super_list_mock, _cache_get_mock, cache_set_mock):
        request = self.factory.get('/api/catalog/products/')
        response = self.view.list(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 2, 'name': 'DB'}])
        cache_set_mock.assert_called_once_with('public:catalog:products:list', [{'id': 2, 'name': 'DB'}], timeout=120)

    @patch('apps.catalog.views.cache.set')
    @patch('apps.catalog.views.cache.get', return_value=None)
    @patch('apps.catalog.views.viewsets.ModelViewSet.retrieve', return_value=Response({'id': 7, 'name': 'DB'}))
    @patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:7')
    def test_retrieve_endpoint_sets_cache_on_miss(self, _cache_key_mock, _super_retrieve_mock, _cache_get_mock, cache_set_mock):
        request = self.factory.get('/api/catalog/products/7/')
        response = self.view.retrieve(request, pk='7')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'id': 7, 'name': 'DB'})
        cache_set_mock.assert_called_once_with('public:catalog:products:7', {'id': 7, 'name': 'DB'}, timeout=120)


class ProductSearchTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ProductViewSet()

    def _drf_request(self, url: str) -> Request:
        return Request(self.factory.get(url))

    def test_search_requires_query(self):
        request = self._drf_request('/api/catalog/products/search/')
        response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Missing query parameter q')

    @patch('apps.catalog.views.cache.get', return_value=[{'id': 1, 'name': 'Cached Search'}])
    @patch('apps.catalog.views.ProductSearchService')
    @patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:search:abc')
    def test_search_uses_cache_on_hit(self, _cache_key_mock, search_service_cls, _cache_get_mock):
        request = self._drf_request('/api/catalog/products/search/?q=phone')
        response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 1, 'name': 'Cached Search'}])
        search_service_cls.return_value.search.assert_not_called()

    @patch('apps.catalog.views.cache.set')
    @patch('apps.catalog.views.cache.get', return_value=None)
    @patch('apps.catalog.views.ProductSerializer')
    @patch('apps.catalog.views.Product.objects.filter')
    @patch('apps.catalog.views.ProductSearchService')
    @patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:search:abc')
    def test_search_endpoint_uses_search_service(
        self,
        _cache_key_mock,
        search_service_cls,
        filter_mock,
        serializer_cls,
        _cache_get_mock,
        cache_set_mock,
    ):
        search_service_cls.return_value.search.return_value = [1]
        filter_mock.return_value = [SimpleNamespace(id=1)]
        serializer_cls.return_value.data = [{'id': 1, 'name': 'Phone'}]

        request = self._drf_request('/api/catalog/products/search/?q=phone')
        response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 1, 'name': 'Phone'}])
        search_service_cls.return_value.search.assert_called_once_with('phone')
        filter_mock.assert_called_once_with(id__in=[1])
        cache_set_mock.assert_called_once_with('public:catalog:products:search:abc', [{'id': 1, 'name': 'Phone'}], timeout=60)

    @patch('apps.catalog.views.cache.get', return_value=None)
    @patch('apps.catalog.views.ProductSearchService')
    @patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:search:abc')
    def test_search_returns_service_unavailable_on_errors(self, _cache_key_mock, search_service_cls, _cache_get_mock):
        search_service_cls.return_value.search.side_effect = Exception('es-down')

        request = self._drf_request('/api/catalog/products/search/?q=phone')
        response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['detail'], 'Search temporarily unavailable')


class ProductSignalTests(SimpleTestCase):
    @patch('apps.catalog.signals.connection')
    @patch('apps.catalog.signals.push_user_notification')
    @patch('apps.catalog.signals.Notification')
    @patch('apps.catalog.signals.get_user_model')
    @patch('apps.catalog.signals.ProductSearchService')
    @patch('apps.catalog.signals._invalidate_product_cache')
    def test_product_create_generates_notification(
        self,
        invalidate_mock,
        search_service_cls,
        get_user_model_mock,
        notification_mock,
        push_mock,
        connection_mock,
    ):
        fake_user = SimpleNamespace(id=101)
        get_user_model_mock.return_value.objects.filter.return_value = [fake_user]
        connection_mock.schema_name = 'acme'
        product = SimpleNamespace(id=11, name='Laptop')

        signals.notify_staff_on_product_create(sender=None, instance=product, created=True)

        invalidate_mock.assert_called_once_with(11)
        search_service_cls.return_value.index_product.assert_called_once_with(product)
        notification_mock.objects.create.assert_called_once_with(user=fake_user, message='New product created: Laptop')
        push_mock.assert_called_once_with(101, 'New product created: Laptop', schema_name='acme')

    @patch('apps.catalog.signals.push_user_notification')
    @patch('apps.catalog.signals.Notification')
    @patch('apps.catalog.signals.get_user_model')
    @patch('apps.catalog.signals.ProductSearchService')
    @patch('apps.catalog.signals._invalidate_product_cache')
    def test_product_update_does_not_generate_staff_notification(
        self,
        invalidate_mock,
        search_service_cls,
        _get_user_model_mock,
        notification_mock,
        push_mock,
    ):
        product = SimpleNamespace(id=11, name='Laptop')

        signals.notify_staff_on_product_create(sender=None, instance=product, created=False)

        invalidate_mock.assert_called_once_with(11)
        search_service_cls.return_value.index_product.assert_called_once_with(product)
        notification_mock.objects.create.assert_not_called()
        push_mock.assert_not_called()

    @patch('apps.catalog.signals.ProductSearchService')
    @patch('apps.catalog.signals._invalidate_product_cache')
    def test_product_delete_cleans_dependencies(self, invalidate_mock, search_service_cls):
        product = SimpleNamespace(id=99)
        signals.cleanup_product_dependencies(sender=None, instance=product)

        invalidate_mock.assert_called_once_with(99)
        search_service_cls.return_value.delete_product.assert_called_once_with(99)


class ProductSearchServiceTests(SimpleTestCase):
    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_init_builds_tenant_scoped_index_name(self, es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()

        es_cls.assert_called_once_with('http://es:9200')
        self.assertEqual(service.index_name, 'saas_acme_products')

    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_ensure_index_skips_when_exists(self, _es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.client.indices.exists.return_value = True

        service.ensure_index()

        service.client.indices.create.assert_not_called()

    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_ensure_index_creates_when_missing(self, _es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.client.indices.exists.return_value = False

        service.ensure_index()

        service.client.indices.create.assert_called_once()

    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_index_product_indexes_float_price(self, _es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.ensure_index = MagicMock()
        product = SimpleNamespace(id=5, name='Phone', description='Smart phone', price=Decimal('99.50'))

        service.index_product(product)

        service.ensure_index.assert_called_once()
        service.client.index.assert_called_once_with(
            index='saas_acme_products',
            id=5,
            document={'name': 'Phone', 'description': 'Smart phone', 'price': 99.5},
            refresh=True,
        )

    @patch('apps.catalog.search.logger')
    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_delete_product_logs_errors(self, _es_cls, settings_mock, connection_mock, logger_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.client.delete.side_effect = Exception('delete-failed')

        service.delete_product(77)

        logger_mock.exception.assert_called_once()

    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_search_returns_integer_ids(self, _es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.ensure_index = MagicMock()
        service.client.search.return_value = {'hits': {'hits': [{'_id': '10'}, {'_id': '20'}]}}

        result = service.search('phone')

        service.ensure_index.assert_called_once()
        self.assertEqual(result, [10, 20])
