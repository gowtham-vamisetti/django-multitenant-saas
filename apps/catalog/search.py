import logging

from django.conf import settings
from django.db import connection
from elasticsearch import Elasticsearch

from .models import Product

logger = logging.getLogger(__name__)


class ProductSearchService:
    def __init__(self) -> None:
        self.client = Elasticsearch(settings.ELASTICSEARCH_URL)
        self.index_name = f"{settings.ELASTICSEARCH_INDEX_PREFIX}_{connection.schema_name}_products"

    def ensure_index(self) -> None:
        if self.client.indices.exists(index=self.index_name):
            return
        self.client.indices.create(
            index=self.index_name,
            mappings={
                'properties': {
                    'name': {'type': 'text'},
                    'description': {'type': 'text'},
                    'price': {'type': 'float'},
                }
            },
        )

    def index_product(self, product: Product) -> None:
        self.ensure_index()
        self.client.index(
            index=self.index_name,
            id=product.id,
            document={
                'name': product.name,
                'description': product.description,
                'price': float(product.price),
            },
            refresh=True,
        )

    def delete_product(self, product_id: int) -> None:
        try:
            self.client.delete(index=self.index_name, id=product_id, refresh=True)
        except Exception:
            logger.exception('Failed to delete product %s from Elasticsearch index %s', product_id, self.index_name)

    def search(self, query: str) -> list[int]:
        self.ensure_index()
        result = self.client.search(
            index=self.index_name,
            query={
                'multi_match': {
                    'query': query,
                    'fields': ['name^2', 'description'],
                }
            },
            size=25,
        )
        return [int(hit['_id']) for hit in result['hits']['hits']]
