from django.test import TestCase

from .models import Client


class ClientModelTests(TestCase):
    def test_client_string_representation(self):
        client = Client(name='Acme', schema_name='acme')
        self.assertIn('Acme', str(client))
        self.assertIn('acme', str(client))
