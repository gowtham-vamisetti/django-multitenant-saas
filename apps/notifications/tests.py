import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from .consumers import NotificationConsumer
from .middleware import TenantSchemaScopeMiddleware
from .services import build_user_notification_group, normalize_schema_name, push_user_notification
from .tenancy import host_from_scope, parse_host, schema_name_from_host


class NotificationGroupTests(SimpleTestCase):
    def test_group_name_is_schema_scoped(self):
        group_name = build_user_notification_group('acme', 42)
        self.assertEqual(group_name, 'acme.user_notifications.42')

    def test_schema_name_is_sanitized(self):
        sanitized = normalize_schema_name('acme:west')
        self.assertEqual(sanitized, 'acme_west')


class NotificationPushTests(SimpleTestCase):
    @patch('apps.notifications.services.get_channel_layer')
    @patch('apps.notifications.services.async_to_sync')
    def test_push_user_notification_uses_schema_group(self, async_to_sync_mock, get_channel_layer_mock):
        channel_layer = MagicMock()
        get_channel_layer_mock.return_value = channel_layer
        sender = async_to_sync_mock.return_value

        push_user_notification(user_id=7, message='hello', schema_name='acme')

        async_to_sync_mock.assert_called_once_with(channel_layer.group_send)
        sender.assert_called_once()
        args, _kwargs = sender.call_args
        self.assertEqual(args[0], 'acme.user_notifications.7')
        self.assertEqual(args[1]['type'], 'notify')

    @patch('apps.notifications.services.get_channel_layer', return_value=None)
    def test_push_user_notification_handles_missing_layer(self, _layer_mock):
        push_user_notification(user_id=7, message='hello', schema_name='acme')


class NotificationTenancyParsingTests(SimpleTestCase):
    def test_parse_host_strips_port(self):
        self.assertEqual(parse_host('acme.localhost:8000'), 'acme.localhost')

    def test_host_from_scope_reads_host_header(self):
        scope = {'headers': [(b'host', b'acme.localhost:8000')]}
        self.assertEqual(host_from_scope(scope), 'acme.localhost:8000')

    @patch('apps.notifications.tenancy.get_public_schema_name', return_value='public')
    def test_schema_name_from_host_returns_public_when_empty_host(self, _public_schema_mock):
        self.assertEqual(schema_name_from_host(''), 'public')

    @patch('apps.notifications.tenancy.Domain')
    @patch('apps.notifications.tenancy.schema_context')
    @patch('apps.notifications.tenancy.get_public_schema_name', return_value='public')
    def test_schema_name_from_host_returns_public_when_domain_missing(
        self,
        _public_schema_mock,
        schema_context_mock,
        domain_cls_mock,
    ):
        @contextmanager
        def fake_schema_context(_schema):
            yield

        schema_context_mock.side_effect = fake_schema_context
        domain_cls_mock.objects.select_related.return_value.filter.return_value.first.return_value = None

        self.assertEqual(schema_name_from_host('acme.localhost:8000'), 'public')

    @patch('apps.notifications.tenancy.Domain')
    @patch('apps.notifications.tenancy.schema_context')
    @patch('apps.notifications.tenancy.get_public_schema_name', return_value='public')
    def test_schema_name_from_host_returns_tenant_schema(
        self,
        _public_schema_mock,
        schema_context_mock,
        domain_cls_mock,
    ):
        @contextmanager
        def fake_schema_context(_schema):
            yield

        schema_context_mock.side_effect = fake_schema_context
        domain = SimpleNamespace(tenant=SimpleNamespace(schema_name='acme'))
        domain_cls_mock.objects.select_related.return_value.filter.return_value.first.return_value = domain

        self.assertEqual(schema_name_from_host('acme.localhost:8000'), 'acme')


class NotificationConsumerTests(SimpleTestCase):
    def test_connect_rejects_anonymous_user(self):
        consumer = NotificationConsumer()
        consumer.scope = {'user': SimpleNamespace(is_anonymous=True)}
        consumer.close = AsyncMock()
        consumer.accept = AsyncMock()
        consumer.channel_layer = MagicMock()
        consumer.channel_name = 'chan-1'

        asyncio.run(consumer.connect())

        consumer.close.assert_awaited_once_with(code=4001)
        consumer.accept.assert_not_awaited()

    @patch('apps.notifications.consumers.build_user_notification_group', return_value='acme.user_notifications.7')
    def test_connect_uses_scope_schema_when_present(self, group_builder_mock):
        consumer = NotificationConsumer()
        consumer.scope = {'user': SimpleNamespace(id=7, is_anonymous=False), 'schema_name': 'acme'}
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_add = AsyncMock()
        consumer.channel_name = 'chan-1'
        consumer.accept = AsyncMock()
        consumer.close = AsyncMock()

        asyncio.run(consumer.connect())

        group_builder_mock.assert_called_once_with('acme', 7)
        consumer.channel_layer.group_add.assert_awaited_once_with('acme.user_notifications.7', 'chan-1')
        consumer.accept.assert_awaited_once()

    @patch('apps.notifications.consumers.database_sync_to_async')
    @patch('apps.notifications.consumers.host_from_scope', return_value='acme.localhost:8000')
    @patch('apps.notifications.consumers.build_user_notification_group', return_value='acme.user_notifications.7')
    def test_connect_resolves_schema_when_missing(
        self,
        group_builder_mock,
        _host_from_scope_mock,
        db_sync_to_async_mock,
    ):
        db_sync_to_async_mock.return_value = AsyncMock(return_value='acme')
        consumer = NotificationConsumer()
        consumer.scope = {'user': SimpleNamespace(id=7, is_anonymous=False), 'headers': [(b'host', b'acme.localhost:8000')]}
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_add = AsyncMock()
        consumer.channel_name = 'chan-1'
        consumer.accept = AsyncMock()
        consumer.close = AsyncMock()

        asyncio.run(consumer.connect())

        group_builder_mock.assert_called_once_with('acme', 7)
        consumer.channel_layer.group_add.assert_awaited_once()
        consumer.accept.assert_awaited_once()

    def test_disconnect_discards_group_when_set(self):
        consumer = NotificationConsumer()
        consumer.group_name = 'acme.user_notifications.7'
        consumer.channel_name = 'chan-1'
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_discard = AsyncMock()

        asyncio.run(consumer.disconnect(1000))

        consumer.channel_layer.group_discard.assert_awaited_once_with('acme.user_notifications.7', 'chan-1')

    def test_notify_sends_json_payload(self):
        consumer = NotificationConsumer()
        consumer.send = AsyncMock()

        asyncio.run(consumer.notify({'message': 'hello', 'created_at': '2026-01-01T10:00:00'}))

        consumer.send.assert_awaited_once()
        sent_payload = consumer.send.await_args.kwargs['text_data']
        self.assertIn('"message": "hello"', sent_payload)


class NotificationMiddlewareTests(SimpleTestCase):
    def test_middleware_sets_schema_for_websocket(self):
        captured = {}

        async def dummy_app(scope, receive, send):
            captured['scope'] = dict(scope)
            return 'ok'

        middleware = TenantSchemaScopeMiddleware(dummy_app)
        scope = {'type': 'websocket', 'headers': [(b'host', b'acme.localhost:8000')]}

        with patch('apps.notifications.middleware.host_from_scope', return_value='acme.localhost:8000'), patch(
            'apps.notifications.middleware.database_sync_to_async',
            return_value=AsyncMock(return_value='acme'),
        ):
            result = asyncio.run(middleware(scope, None, None))

        self.assertEqual(result, 'ok')
        self.assertEqual(captured['scope']['schema_name'], 'acme')

    def test_middleware_leaves_non_websocket_scope_unchanged(self):
        captured = {}

        async def dummy_app(scope, receive, send):
            captured['scope'] = dict(scope)
            return 'ok'

        middleware = TenantSchemaScopeMiddleware(dummy_app)
        scope = {'type': 'http'}

        result = asyncio.run(middleware(scope, None, None))

        self.assertEqual(result, 'ok')
        self.assertNotIn('schema_name', captured['scope'])
