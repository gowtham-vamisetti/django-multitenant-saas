# django-multitenant-saas

Multi-tenant SaaS reference implementation using Django, PostgreSQL schemas, Redis, Elasticsearch, and Django Channels.

## Reviewer Quick Guide

- HLD PDF: `docs/HLD_MultiTenant_Django_SaaS.pdf`
- Backend entrypoints: `config/settings.py`, `config/asgi.py`, `config/urls.py`, `config/public_urls.py`
- Primary apps: `apps/customers`, `apps/users`, `apps/catalog`, `apps/notifications`

If you want the fastest review path, open the HLD PDF first, then validate the requirement mapping table below.

## Requirement Coverage Matrix

| Assignment Requirement | Implemented Design | Code References | HLD Page |
|---|---|---|---|
| 1. Multi-Tenant Architecture | `django-tenants` domain-based tenant resolution with schema-per-tenant isolation | `config/settings.py`, `apps/customers/models.py`, `config/public_urls.py` | Requirement 1 page |
| 2. Django Admin Panel | Public admin manages tenant lifecycle, tenant admin manages tenant-local users/data | `apps/customers/admin.py`, `apps/users/admin.py`, `apps/catalog/admin.py`, `apps/notifications/admin.py` | Requirement 2 page |
| 3. Public & Private Schema + Redis | Public schema for shared metadata; private schemas for tenant entities; tenant-scoped cache keys + versioned invalidation | `config/settings.py`, `apps/catalog/views.py`, `apps/catalog/cache.py`, `apps/catalog/services.py` | Requirement 3 page |
| 4. Elasticsearch Implementation | Official Elasticsearch client with tenant-isolated index naming and signal-to-service sync | `apps/catalog/search.py`, `apps/catalog/services.py`, `apps/catalog/signals.py` | Requirement 4 page |
| 5. WebSockets for Notifications | Django Channels consumer + Redis channel layer + React client with schema-scoped notification groups | `config/asgi.py`, `apps/notifications/consumers.py`, `apps/notifications/services.py`, `frontend/src/App.jsx` | Requirement 5 page |

## Architecture Highlights

- Hard tenant isolation at DB schema level (`public` + private tenant schemas).
- Tenant boundary is propagated consistently to ORM access (`connection.schema_name`).
- Tenant boundary is propagated consistently to Redis keys (`<schema>:...`).
- Search cache uses schema-scoped versioning to avoid stale query results after writes.
- Tenant boundary is propagated consistently to Elasticsearch indexes (`<prefix>_<schema>_products`).
- Tenant boundary is propagated consistently to WebSocket groups (`<schema>.user_notifications.<id>`).
- Admin separation: public domain admin for tenants/domains, tenant domain admin for tenant business data.
- Signal-to-service event pipeline keeps cache, search index, and notifications coherent for API and admin writes.

## Project Structure

- `config/settings.py`: multi-tenancy, Redis cache, DRF auth, Channels, Elasticsearch, logging.
- `config/asgi.py`: HTTP + WebSocket protocol routing and tenant-aware websocket middleware.
- `apps/customers/`: tenant and domain models (`Client`, `Domain`) in public schema.
- `apps/users/`: tenant user model/admin.
- `apps/catalog/`: product CRUD API, search endpoint, caching hooks, search sync.
- `apps/notifications/`: notification model, websocket consumer, push service, tenancy helpers.
- `frontend/`: minimal React app for live WebSocket notifications.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Start infra:

```bash
docker compose up -d postgres redis elasticsearch
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run migrations and create superuser:

```bash
python manage.py migrate_schemas --shared
python manage.py migrate_schemas
python manage.py createsuperuser
```

5. Run backend:

```bash
python manage.py runserver
```

6. Run frontend:

```bash
cd frontend
npm install
npm run dev
```

## Endpoints

Tenant routes:
- `GET /api/catalog/products/`
- `POST /api/catalog/products/`
- `GET /api/catalog/products/{id}/`
- `PUT/PATCH /api/catalog/products/{id}/`
- `DELETE /api/catalog/products/{id}/`
- `GET /api/catalog/products/search/?q=...`

Public route:
- `GET /health/`

WebSocket:
- `ws://<tenant-domain>/ws/notifications/`

API authentication defaults:
- `SessionAuthentication`
- optional `BasicAuthentication` via `ENABLE_BASIC_AUTH=1`

## Quality, Security, and Reliability

- Authentication enforced for API and WebSocket notification access.
- Tenant-safe channel grouping for notifications.
- Tenant-scoped cache keys and invalidation strategy.
- Graceful error handling and logging for search/indexing paths.
- Baseline security settings and secure-cookie toggles in environment config.

## Tests

Run tests:

```bash
pytest
```

Current test coverage includes:
- Product API response/auth tests.
- Search endpoint behavior with mocked search service.
- Notification creation on product create.
- Notification service group isolation and tenancy parsing tests.
- Tenant model representation test.

## Submission Notes

- This repo includes source code and configuration for all required components.
- The HLD deliverable is included as `docs/HLD_MultiTenant_Django_SaaS.pdf`.

## Evaluation Criteria Mapping

- Adherence to requirements: `config/settings.py`, `apps/customers/models.py`, `apps/catalog/search.py`, `apps/notifications/consumers.py`
- Code quality and organization: `apps/catalog/cache.py`, `apps/catalog/services.py`, `apps/catalog/signals.py`
- Scalability and performance: `apps/catalog/views.py`, `apps/catalog/search.py`, `apps/notifications/services.py`
- Documentation and clarity: `README.md`, `LLD_CODE_FLOW.md`, `docs/HLD_MultiTenant_Django_SaaS.pdf`, `docs/REVIEWER_DEMO.md`

## Production Hardening Checklist

- Enable HTTPS and strict cookie settings.
- Restrict `ALLOWED_HOSTS` and disable `DEBUG`.
- Add monitoring, alerting, and centralized log aggregation.
- Add CI pipeline for tests, linting, and security checks.
