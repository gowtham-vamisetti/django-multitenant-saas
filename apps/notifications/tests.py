from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .services import build_user_notification_group, normalize_schema_name, push_user_notification
from .tenancy import host_from_scope, parse_host


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
