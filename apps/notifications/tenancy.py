from typing import Any

from django_tenants.utils import get_public_schema_name, schema_context

from apps.customers.models import Domain


def parse_host(host_header: str) -> str:
    return host_header.split(':', 1)[0].strip().lower()


def host_from_scope(scope: dict[str, Any]) -> str:
    for name, value in scope.get('headers', []):
        if name == b'host':
            return value.decode('latin1')
    return ''


def schema_name_from_host(host_header: str) -> str:
    public_schema = get_public_schema_name()
    host = parse_host(host_header)
    if not host:
        return public_schema

    with schema_context(public_schema):
        domain = Domain.objects.select_related('tenant').filter(domain=host).first()
    if domain is None:
        return public_schema
    return domain.tenant.schema_name
