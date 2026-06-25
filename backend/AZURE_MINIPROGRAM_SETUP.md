# Azure + WeChat Mini Program Setup

The mini program talks to the FastAPI backend. It does not connect to the
database directly.

```text
WeChat Mini Program -> Azure App Service -> Supabase PostgreSQL
```

## Azure App Settings

Open Azure Portal:

```text
hkmu-campus-sea -> Settings -> Environment variables -> App settings
```

Add these values as application settings, not connection strings:

```env
DATABASE_URL=postgresql://...
SECRET_KEY=...
DB_POOL_MIN=1
DB_POOL_MAX=5
WECHAT_MINIPROGRAM_APPID=...
WECHAT_MINIPROGRAM_SECRET=...
CORS_ORIGINS=https://hkmu-campus-sea.azurewebsites.net
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
ADMIN_USERNAMES=testuser1
```

Use the Supabase pooler URL for `DATABASE_URL`.

## WeChat Server Domain

In the WeChat Mini Program admin console, set the request domain to:

```text
https://hkmu-campus-sea.azurewebsites.net
```

Do not include `/api/v1` in the server domain.

## Mini Program API Base

The mini program API base should stay:

```js
const API_BASE = "https://hkmu-campus-sea.azurewebsites.net/api/v1";
```

## Verify

After deployment and restart:

```text
https://hkmu-campus-sea.azurewebsites.net/api/health
https://hkmu-campus-sea.azurewebsites.net/api/v1/courses?page=1&page_size=1
```
