#!/bin/bash
set -e

echo "⚙️ 配置 Web App 环境变量..."

# 前置条件：
#   1. 已登录 az cli
#   2. 已设置环境变量：
#        export SECRET_KEY="your-secret-key"
#        export DB_PASSWORD="your-db-password"
#        export SUPABASE_SERVICE_KEY="your-supabase-service-key"
#        export GOOGLE_CLIENT_ID="your-google-client-id"
#        export SUPABASE_PROJECT_REF="your-project-ref"
#        export FRONTEND_URL="https://your-app.azurewebsites.net"

az webapp config appsettings set \
  --name hkmu-campus \
  --resource-group rg-hkmu-campus \
  --settings \
    "WEBSITES_PORT=8000" \
    "SECRET_KEY=$SECRET_KEY" \
    "DATABASE_URL=postgresql://postgres:$DB_PASSWORD@db.$SUPABASE_PROJECT_REF.supabase.co:5432/postgres" \
    "GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" \
    "SUPABASE_URL=https://$SUPABASE_PROJECT_REF.supabase.co" \
    "SUPABASE_SERVICE_KEY=$SUPABASE_SERVICE_KEY" \
    "ADMIN_USERNAMES=$ADMIN_USERNAMES" \
    "DB_POOL_MIN=1" \
    "DB_POOL_MAX=5" \
    "FRONTEND_URL=$FRONTEND_URL" \
    "CORS_ORIGINS=$FRONTEND_URL"

echo ""
echo "🔄 重启 Web App..."
az webapp restart --name hkmu-campus --resource-group rg-hkmu-campus

echo ""
echo "⏳ 等待 30 秒启动..."
sleep 30

echo ""
echo "🧪 健康检查..."
curl -s --max-time 15 "$FRONTEND_URL/api/health" && echo " ✅ 成功！" || echo " ❌ 失败"
