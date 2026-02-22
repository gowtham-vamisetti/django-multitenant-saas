# LLD Code Flow (Q1-Q5)

This document explains how each assignment requirement is implemented in this repository at code-flow level.

## How To Read This

1. Start from the requirement section (`Q1` to `Q5`).
2. Follow the runtime flow steps.
3. Open file references to validate implementation.
4. Use the test evidence subsection when presenting to reviewers.

## Q1. Multi-Tenant Architecture

Requirement:
Implement tenant-isolated schema architecture using Django routing or `django-tenant-schemas` style library.

Runtime flow (HTTP):
1. Incoming request enters Django middleware stack.
2. `TenantMainMiddleware` resolves host/domain to tenant schema.
3. Tenant schema is activated on the DB connection.
4. Request is routed to tenant URLConf or public URLConf based on active schema.
5. ORM queries run inside the active schema only.

Runtime flow (WebSocket):
1. ASGI receives websocket connection.
2. `TenantSchemaScopeMiddleware` reads `Host` header and resolves schema using `Domain`.
3. Consumer receives `scope['schema_name']` and applies tenant-safe behavior.

Main classes/functions:
- Tenant config: `config/settings.py:41`, `config/settings.py:52`, `config/settings.py:74`, `config/settings.py:83`, `config/settings.py:84`, `config/settings.py:85`
- Tenant models: `apps/customers/models.py:5`, `apps/customers/models.py:10`, `apps/customers/models.py:16`
- Tenant/public routing: `config/urls.py:4`, `config/public_urls.py:10`
- ASGI tenant scope middleware: `config/asgi.py:14`, `config/asgi.py:17`, `apps/notifications/middleware.py:6`, `apps/notifications/tenancy.py:19`

Why this completes Q1:
- Uses `django-tenants` engine and router.
- Uses schema-per-tenant (`Client` + `Domain` mapping).
- Uses separate public URLConf and tenant URLConf.
- Extends tenant resolution to WebSocket scope.

Test evidence:
- Baseline tenant model check: `apps/customers/tests.py:6`
- Tenant host parsing helper tests: `apps/notifications/tests.py:40`


## Q2. Django Admin Panel

Requirement:
Customize admin so superusers can manage tenants and tenant users.

Runtime flow:
1. Superuser logs into admin.
2. In public schema admin, superuser manages tenant lifecycle (`Client`, `Domain`).
3. In tenant schema context, admin manages tenant entities (`User`, `Product`, `Notification`).
4. Admin operations use active schema context, so writes remain tenant-local.

Main classes/functions:
- Public admin models: `apps/customers/admin.py:6`, `apps/customers/admin.py:12`
- Tenant user admin: `apps/users/admin.py:7`
- Tenant catalog admin: `apps/catalog/admin.py:6`
- Tenant notifications admin: `apps/notifications/admin.py:6`
- Shared vs tenant app partitioning: `config/settings.py:14`, `config/settings.py:27`

Why this completes Q2:
- Tenant registry is manageable by superuser in admin.
- Tenant-local user and business entities are admin-managed in schema context.

Test evidence:
- Indirect proof via model behavior and signal-driven side effects in tests:
- `apps/customers/tests.py:6`
- `apps/catalog/tests.py:46`

## Q3. Public & Private Schema + Redis Cache for CRUD

Requirement:
Public schema for shared data, private schemas for tenant data, Redis cache where possible for CRUD.

Runtime flow:
1. Public metadata lives in `Client`/`Domain`; tenant business data lives in tenant apps.
2. Product list/retrieve endpoints use cache-aside strategy.
3. Search endpoint also caches query result.
4. Create/update/delete invalidates tenant-scoped cache keys.
5. Signal handlers provide additional cache invalidation on model events.

Main classes/functions:
- Shared/tenant apps split: `config/settings.py:14`, `config/settings.py:27`
- Redis cache config: `config/settings.py:119`
- Product list cache: `apps/catalog/views.py:31`
- Product retrieve cache: `apps/catalog/views.py:41`
- Product search cache: `apps/catalog/views.py:69`
- Cache invalidation in viewset: `apps/catalog/views.py:64`
- Cache invalidation in signals: `apps/catalog/signals.py:22`, `apps/catalog/signals.py:29`, `apps/catalog/signals.py:47`

Why this completes Q3:
- Public/private schema split is explicit in app configuration and tenant model setup.
- Redis caching is implemented for high-read CRUD paths and invalidated on writes.

Test evidence:
- API list/read behavior test: `apps/catalog/tests.py:11`
- Search path test with service mocking: `apps/catalog/tests.py:30`

## Q4. Elasticsearch Implementation

Requirement:
Use official Elasticsearch Python client and keep search tenant-isolated.

Runtime flow:
1. Product write event occurs.
2. Signal handler calls `ProductSearchService.index_product` or `delete_product`.
3. Service resolves index name using current schema.
4. Search API calls `ProductSearchService.search`.
5. Returned IDs are hydrated from tenant DB and serialized.

Main classes/functions:
- Elasticsearch client and index naming: `apps/catalog/search.py:12`, `apps/catalog/search.py:14`, `apps/catalog/search.py:15`
- Index management and write ops: `apps/catalog/search.py:17`, `apps/catalog/search.py:31`, `apps/catalog/search.py:44`
- Search operation: `apps/catalog/search.py:50`
- Signal-based sync path: `apps/catalog/signals.py:27`, `apps/catalog/signals.py:45`
- Search endpoint integration: `apps/catalog/views.py:69`, `apps/catalog/views.py:81`

Why this completes Q4:
- Official `elasticsearch` client is used.
- Index is schema-scoped, so each tenant has isolated search index.
- Signal-driven sync keeps admin and API writes consistent.

Test evidence:
- Search endpoint behavior test: `apps/catalog/tests.py:37`
- Signal path test that validates event-driven side effect pipeline: `apps/catalog/tests.py:48`

## Q5. WebSockets for Notifications

Requirement:
Use Django Channels WebSockets for real-time notifications and React client display.

Runtime flow:
1. Frontend connects to `/ws/notifications/`.
2. ASGI route wraps consumer with auth and tenant scope middleware.
3. Consumer authenticates user and resolves schema-aware group.
4. Domain events call notification push service.
5. Service publishes JSON payload to schema-scoped user group.
6. Consumer forwards payload to client in real time.

Main classes/functions:
- ASGI routing and middleware chain: `config/asgi.py:14`, `config/asgi.py:17`
- Websocket URL route: `apps/notifications/routing.py:5`
- Scope schema resolution: `apps/notifications/middleware.py:6`, `apps/notifications/tenancy.py:19`
- Consumer connect/group/send: `apps/notifications/consumers.py:10`, `apps/notifications/consumers.py:11`, `apps/notifications/consumers.py:22`, `apps/notifications/consumers.py:30`
- Group naming + push service: `apps/notifications/services.py:15`, `apps/notifications/services.py:19`
- Event source: `apps/catalog/signals.py:41`, `apps/catalog/signals.py:42`
- React websocket UI: `frontend/src/App.jsx:13`

Why this completes Q5:
- Channels + Redis channel layer are wired.
- Authenticated websocket consumer is implemented.
- Tenant-safe notification grouping prevents cross-tenant leakage.
- React app consumes and displays real-time notifications.

Test evidence:
- Group naming tests: `apps/notifications/tests.py:9`
- Push behavior tests: `apps/notifications/tests.py:19`
- Host/schema parsing tests: `apps/notifications/tests.py:40`

## Additional Considerations Mapping

Security:
- API auth enforced in viewset: `apps/catalog/views.py:23`
- WebSocket auth check: `apps/notifications/consumers.py:13`

Error handling and logging:
- Search failure handling: `apps/catalog/views.py:82`
- ES index/delete exception logging: `apps/catalog/signals.py:34`, `apps/catalog/signals.py:51`

Unit tests:
- Customer tests: `apps/customers/tests.py`
- Catalog tests: `apps/catalog/tests.py`
- Notifications tests: `apps/notifications/tests.py`

Documentation:
- HLD PDF: `docs/HLD_MultiTenant_Django_SaaS.pdf`
- Demo/Q&A guide: `docs/REVIEWER_DEMO.md`

## Quick Verifier Commands

```bash
pytest
```