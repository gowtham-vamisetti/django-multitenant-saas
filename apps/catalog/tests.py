from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .models import Product
from .views import ProductViewSet


class ProductCachingTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        Product.objects.create(name='Widget', description='A widget', price='10.00', is_active=True)

    def test_list_endpoint_returns_data(self):
        request = self.factory.get('/api/catalog/products/')
        response = ProductViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)


class ProductSearchTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        Product.objects.create(name='Phone', description='Smart phone', price='100.00', is_active=True)

    @patch('apps.catalog.views.ProductSearchService')
    def test_search_endpoint_uses_search_service(self, search_service_cls):
        search_service_cls.return_value.search.return_value = [1]
        request = self.factory.get('/api/catalog/products/search/?q=phone')
        response = ProductViewSet.as_view({'get': 'search'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)


class ProductSignalTests(TestCase):
    @patch('apps.catalog.signals.push_user_notification')
    def test_product_create_generates_notification(self, push_mock):
        User = get_user_model()
        user = User.objects.create(username='staff', is_staff=True)
        Product.objects.create(name='Laptop', description='Gaming', price='1200.00', is_active=True)
        user.refresh_from_db()
        self.assertTrue(user.notifications.exists())
        push_mock.assert_called()
