# django-multitenant-saas

Multi-tenant SaaS reference implementation using Django, PostgreSQL schemas, Redis cache, Elasticsearch search, and Django Channels WebSockets.

## Implemented Requirements

1. Multi-tenant architecture
- Uses `django-tenants` with PostgreSQL schema isolation.
- `public` schema stores shared tenant metadata.
- Each tenant gets a private schema containing tenant-specific apps and data.

2. Django admin panel
- Tenant models (`Client`, `Domain`) are managed in admin.
- Tenant users, products, and notifications are admin-managed per schema.

3. Public and private schemas
- Shared apps in `SHARED_APPS` (`apps.customers`, auth/admin base).
- Tenant apps in `TENANT_APPS` (`apps.users`, `apps.catalog`, `apps.notifications`).
- Redis caching used in product CRUD read paths (`list`, `retrieve`) with tenant-scoped cache keys.

4. Elasticsearch integration
- Uses official Python client (`elasticsearch`).
- Product data indexed into tenant-specific index names:
  - `{ELASTICSEARCH_INDEX_PREFIX}_{schema_name}_products`
- Search endpoint returns tenant-scoped results.

5. WebSockets for notifications
- Django Channels + Redis channel layer.
- Authenticated users connect to `/ws/notifications/`.
- Product creation emits notification events to tenant staff users.
- React app (`frontend/`) subscribes and renders live notifications.

## Project Structure

- `config/settings.py`: django-tenants, Redis, Channels, Elasticsearch, logging.
- `apps/customers/`: tenant and domain models (public schema).
- `apps/users/`: tenant user model.
- `apps/catalog/`: product CRUD API, Redis cache, Elasticsearch indexing/search.
- `apps/notifications/`: notification model, websocket consumer, push service.
- `frontend/`: minimal React WebSocket client.

## Local Setup

### 1. Environment

Copy `.env.example` to `.env` and adjust values.

### 2. Start infrastructure

```bash
docker compose up -d postgres redis elasticsearch
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Database and tenants

```bash
python manage.py migrate_schemas --shared
python manage.py createsuperuser
```

Create a tenant in Django admin (`/admin`) under `Clients` and add its `Domain`.

Then run tenant migrations:

```bash
python manage.py migrate_schemas
```

### 5. Run backend

```bash
python manage.py runserver
```

### 6. Run React client

```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

Tenant domain routes:
- `GET /api/catalog/products/`
- `POST /api/catalog/products/`
- `GET /api/catalog/products/{id}/`
- `PUT/PATCH /api/catalog/products/{id}/`
- `DELETE /api/catalog/products/{id}/`
- `GET /api/catalog/products/search/?q=...`

Public domain routes:
- `GET /health/`

WebSocket:
- `ws://<tenant-domain>/ws/notifications/`

## Security and Reliability Notes

- Tenant isolation is enforced at DB schema level via `django-tenants`.
- Notifications WebSocket requires authenticated users.
- Logging is configured with centralized console handler.
- Search/index operations are wrapped with exception handling to avoid request crashes.
- Cache keys are tenant-scoped (`{schema_name}:...`) to prevent leakage.

## Tests

Included tests:
- Product API response test.
- Search endpoint integration with mocked search service.
- Notification creation on product create.
- Tenant model string representation.

Run tests:

```bash
pytest
```

## Design Decisions

- `django-tenants` selected over manual routing for robust schema lifecycle management.
- Redis chosen for low-latency cache and channel layer backend.
- Elasticsearch index per tenant keeps search boundaries explicit.
- WebSocket push grouped per user (`user_notifications_<id>`) for targeted events.

## Notes

- Python runtime was not available in this environment, so runtime checks (`pytest`, migrations) were not executed here.
- Before production use, add HTTPS, strict host/cookie settings, connection pooling, and CI pipeline checks.
