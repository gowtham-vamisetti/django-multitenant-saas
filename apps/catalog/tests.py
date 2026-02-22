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
from .cache import CatalogCacheService
from .search import ProductSearchService
from .services import ProductEventService
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

    def test_list_endpoint_uses_cache_on_hit(self):
        cache_service = MagicMock()
        cache_service.product_list_key.return_value = 'public:catalog:products:list'

        with (
            patch.object(ProductViewSet, '_cache_service', return_value=cache_service),
            patch('apps.catalog.views.cache.get', return_value=[{'id': 1, 'name': 'Cached'}]),
            patch('apps.catalog.views.viewsets.ModelViewSet.list') as super_list_mock,
        ):
            request = self.factory.get('/api/catalog/products/')
            response = self.view.list(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 1, 'name': 'Cached'}])
        super_list_mock.assert_not_called()

    def test_list_endpoint_sets_cache_on_miss(self):
        cache_service = MagicMock()
        cache_service.product_list_key.return_value = 'public:catalog:products:list'

        with (
            patch.object(ProductViewSet, '_cache_service', return_value=cache_service),
            patch('apps.catalog.views.cache.get', return_value=None),
            patch('apps.catalog.views.cache.set') as cache_set_mock,
            patch('apps.catalog.views.viewsets.ModelViewSet.list', return_value=Response([{'id': 2, 'name': 'DB'}])),
        ):
            request = self.factory.get('/api/catalog/products/')
            response = self.view.list(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 2, 'name': 'DB'}])
        cache_set_mock.assert_called_once_with('public:catalog:products:list', [{'id': 2, 'name': 'DB'}], timeout=120)

    def test_retrieve_endpoint_sets_cache_on_miss(self):
        cache_service = MagicMock()
        cache_service.product_detail_key.return_value = 'public:catalog:products:7'

        with (
            patch.object(ProductViewSet, '_cache_service', return_value=cache_service),
            patch('apps.catalog.views.cache.get', return_value=None),
            patch('apps.catalog.views.cache.set') as cache_set_mock,
            patch('apps.catalog.views.viewsets.ModelViewSet.retrieve', return_value=Response({'id': 7, 'name': 'DB'})),
        ):
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

    def test_search_uses_cache_on_hit(self):
        cache_service = MagicMock()
        cache_service.get_search_version.return_value = 2

        with (
            patch.object(ProductViewSet, '_cache_service', return_value=cache_service),
            patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:search:v2:abc'),
            patch('apps.catalog.views.cache.get', return_value=[{'id': 1, 'name': 'Cached Search'}]),
            patch('apps.catalog.views.ProductSearchService') as search_service_cls,
        ):
            request = self._drf_request('/api/catalog/products/search/?q=phone')
            response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 1, 'name': 'Cached Search'}])
        search_service_cls.return_value.search.assert_not_called()

    def test_search_endpoint_uses_search_service_and_active_filter(self):
        cache_service = MagicMock()
        cache_service.get_search_version.return_value = 2

        with (
            patch.object(ProductViewSet, '_cache_service', return_value=cache_service),
            patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:search:v2:abc'),
            patch('apps.catalog.views.cache.get', return_value=None),
            patch('apps.catalog.views.cache.set') as cache_set_mock,
            patch('apps.catalog.views.ProductSearchService') as search_service_cls,
            patch('apps.catalog.views.Product.objects.filter') as filter_mock,
            patch('apps.catalog.views.ProductSerializer') as serializer_cls,
        ):
            search_service_cls.return_value.search.return_value = [2, 1]
            filter_mock.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
            serializer_cls.return_value.data = [{'id': 2, 'name': 'Phone'}, {'id': 1, 'name': 'Case'}]

            request = self._drf_request('/api/catalog/products/search/?q=phone')
            response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [{'id': 2, 'name': 'Phone'}, {'id': 1, 'name': 'Case'}])
        search_service_cls.return_value.search.assert_called_once_with('phone')
        filter_mock.assert_called_once_with(id__in=[2, 1], is_active=True)
        ordered_products = serializer_cls.call_args.args[0]
        self.assertEqual([product.id for product in ordered_products], [2, 1])
        cache_set_mock.assert_called_once_with(
            'public:catalog:products:search:v2:abc',
            [{'id': 2, 'name': 'Phone'}, {'id': 1, 'name': 'Case'}],
            timeout=60,
        )

    def test_search_returns_service_unavailable_on_errors(self):
        cache_service = MagicMock()
        cache_service.get_search_version.return_value = 2

        with (
            patch.object(ProductViewSet, '_cache_service', return_value=cache_service),
            patch.object(ProductViewSet, '_cache_key', return_value='public:catalog:products:search:v2:abc'),
            patch('apps.catalog.views.cache.get', return_value=None),
            patch('apps.catalog.views.ProductSearchService') as search_service_cls,
        ):
            search_service_cls.return_value.search.side_effect = Exception('es-down')

            request = self._drf_request('/api/catalog/products/search/?q=phone')
            response = self.view.search(request)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['detail'], 'Search temporarily unavailable')


class ProductSignalTests(SimpleTestCase):
    @patch('apps.catalog.signals.ProductEventService')
    @patch('apps.catalog.signals.connection')
    def test_product_create_delegates_to_event_service(self, connection_mock, event_service_cls):
        connection_mock.schema_name = 'acme'
        product = SimpleNamespace(id=11, name='Laptop')

        signals.notify_staff_on_product_create(sender=None, instance=product, created=True)

        event_service_cls.assert_called_once_with(schema_name='acme')
        event_service_cls.return_value.handle_product_saved.assert_called_once_with(product, True)

    @patch('apps.catalog.signals.ProductEventService')
    @patch('apps.catalog.signals.connection')
    def test_product_update_delegates_to_event_service(self, connection_mock, event_service_cls):
        connection_mock.schema_name = 'acme'
        product = SimpleNamespace(id=11, name='Laptop')

        signals.notify_staff_on_product_create(sender=None, instance=product, created=False)

        event_service_cls.assert_called_once_with(schema_name='acme')
        event_service_cls.return_value.handle_product_saved.assert_called_once_with(product, False)

    @patch('apps.catalog.signals.ProductEventService')
    @patch('apps.catalog.signals.connection')
    def test_product_delete_delegates_to_event_service(self, connection_mock, event_service_cls):
        connection_mock.schema_name = 'acme'
        product = SimpleNamespace(id=99)

        signals.cleanup_product_dependencies(sender=None, instance=product)

        event_service_cls.assert_called_once_with(schema_name='acme')
        event_service_cls.return_value.handle_product_deleted.assert_called_once_with(99)


class CatalogCacheServiceTests(SimpleTestCase):
    @patch('apps.catalog.cache.cache')
    def test_get_search_version_initializes_default(self, cache_mock):
        cache_mock.get.return_value = None
        service = CatalogCacheService('acme')

        version = service.get_search_version()

        self.assertEqual(version, 1)
        cache_mock.set.assert_called_once_with('acme:catalog:products:search:version', 1, timeout=None)

    @patch('apps.catalog.cache.cache')
    def test_invalidate_product_change_deletes_keys_and_bumps_version(self, cache_mock):
        service = CatalogCacheService('acme')
        service.bump_search_version = MagicMock()

        service.invalidate_product_change(7)

        cache_mock.delete.assert_any_call('acme:catalog:products:list')
        cache_mock.delete.assert_any_call('acme:catalog:products:7')
        service.bump_search_version.assert_called_once()


class ProductEventServiceTests(SimpleTestCase):
    @patch('apps.catalog.services.push_bulk_user_notification')
    @patch('apps.catalog.services.Notification')
    @patch('apps.catalog.services.ProductEventService._staff_user_ids', return_value=[10, 11])
    @patch('apps.catalog.services.ProductSearchService')
    @patch('apps.catalog.services.CatalogCacheService')
    def test_handle_product_saved_for_create(
        self,
        cache_service_cls,
        search_service_cls,
        _staff_ids_mock,
        notification_cls,
        push_bulk_mock,
    ):
        service = ProductEventService(schema_name='acme')
        product = SimpleNamespace(id=5, name='Phone')

        service.handle_product_saved(product, created=True)

        cache_service_cls.return_value.invalidate_product_change.assert_called_once_with(5)
        search_service_cls.return_value.index_product.assert_called_once_with(product)
        notification_cls.objects.bulk_create.assert_called_once()
        push_bulk_mock.assert_called_once_with([10, 11], 'New product created: Phone', schema_name='acme')

    @patch('apps.catalog.services.push_bulk_user_notification')
    @patch('apps.catalog.services.Notification')
    @patch('apps.catalog.services.ProductSearchService')
    @patch('apps.catalog.services.CatalogCacheService')
    def test_handle_product_saved_for_update_skips_notification(
        self,
        cache_service_cls,
        search_service_cls,
        notification_cls,
        push_bulk_mock,
    ):
        service = ProductEventService(schema_name='acme')
        product = SimpleNamespace(id=5, name='Phone')

        service.handle_product_saved(product, created=False)

        cache_service_cls.return_value.invalidate_product_change.assert_called_once_with(5)
        search_service_cls.return_value.index_product.assert_called_once_with(product)
        notification_cls.objects.bulk_create.assert_not_called()
        push_bulk_mock.assert_not_called()

    @patch('apps.catalog.services.ProductSearchService')
    @patch('apps.catalog.services.CatalogCacheService')
    def test_handle_product_deleted(self, cache_service_cls, search_service_cls):
        service = ProductEventService(schema_name='acme')
        service.handle_product_deleted(77)

        cache_service_cls.return_value.invalidate_product_change.assert_called_once_with(77)
        search_service_cls.return_value.delete_product.assert_called_once_with(77)


class ProductSearchServiceTests(SimpleTestCase):
    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_init_builds_tenant_scoped_index_name(self, es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = None
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
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = None
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
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = None
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.client.indices.exists.return_value = False

        service.ensure_index()

        service.client.indices.create.assert_called_once()

    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_index_product_indexes_float_price_without_refresh(self, _es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = None
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
        )

    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_index_product_includes_refresh_when_configured(self, _es_cls, settings_mock, connection_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = 'wait_for'
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.ensure_index = MagicMock()
        product = SimpleNamespace(id=6, name='Tablet', description='Android tablet', price=Decimal('120.00'))

        service.index_product(product)

        service.client.index.assert_called_once_with(
            index='saas_acme_products',
            id=6,
            document={'name': 'Tablet', 'description': 'Android tablet', 'price': 120.0},
            refresh='wait_for',
        )

    @patch('apps.catalog.search.logger')
    @patch('apps.catalog.search.connection')
    @patch('apps.catalog.search.settings')
    @patch('apps.catalog.search.Elasticsearch')
    def test_delete_product_logs_errors(self, _es_cls, settings_mock, connection_mock, logger_mock):
        settings_mock.ELASTICSEARCH_URL = 'http://es:9200'
        settings_mock.ELASTICSEARCH_INDEX_PREFIX = 'saas'
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = None
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
        settings_mock.ELASTICSEARCH_WRITE_REFRESH = None
        connection_mock.schema_name = 'acme'

        service = ProductSearchService()
        service.client = MagicMock()
        service.ensure_index = MagicMock()
        service.client.search.return_value = {'hits': {'hits': [{'_id': '10'}, {'_id': '20'}]}}

        result = service.search('phone')

        service.ensure_index.assert_called_once()
        self.assertEqual(result, [10, 20])
