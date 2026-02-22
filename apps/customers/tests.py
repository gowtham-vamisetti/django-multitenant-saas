from django.test import SimpleTestCase

from .models import Client


class ClientModelTests(SimpleTestCase):
    def test_client_string_representation(self):
        client = Client(name='Acme', schema_name='acme')
        self.assertIn('Acme', str(client))
        self.assertIn('acme', str(client))
