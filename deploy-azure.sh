#!/bin/bash
set -e

echo "🚀 部署 HKMU Campus Platform 到 Azure Container Apps..."

# 前置条件：
#   1. 已登录 az cli
#   2. 已设置环境变量：
#        export SECRET_KEY="your-secret-key"
#        export DB_PASSWORD="your-db-password"
#        export SUPABASE_SERVICE_KEY="your-supabase-service-key"
#        export GOOGLE_CLIENT_ID="your-google-client-id"

az containerapp create \
  --name hkmu-campus \
  --resource-group rg-hkmu-campus \
  --environment hkmu-campus-env \
  --image hkmucampusreg.azurecr.io/hkmu-campus:latest \
  --target-port 8000 \
  --ingress external \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 0 \
  --max-replicas 1 \
  --registry-server hkmucampusreg.azurecr.io \
  --secrets \
    "secret-key=$SECRET_KEY" \
    "database-url=postgresql://postgres:$DB_PASSWORD@db.$SUPABASE_PROJECT_REF.supabase.co:5432/postgres" \
    "supabase-key=$SUPABASE_SERVICE_KEY" \
  --env-vars \
    "SECRET_KEY=secretref:secret-key" \
    "DATABASE_URL=secretref:database-url" \
    "SUPABASE_SERVICE_KEY=secretref:supabase-key" \
    "GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" \
    "SUPABASE_URL=https://$SUPABASE_PROJECT_REF.supabase.co" \
    "ADMIN_USERNAMES=$ADMIN_USERNAMES" \
    "PORT=8000" \
    "DB_POOL_MIN=1" \
    "DB_POOL_MAX=5"

echo ""
echo "✅ 部署完成！获取应用 URL..."
FQDN=$(az containerapp show --name hkmu-campus --resource-group rg-hkmu-campus --query properties.configuration.ingress.fqdn --output tsv)
echo "🌐 应用地址: https://$FQDN"
echo ""
echo "验证中..."
curl -s "https://$FQDN/api/health" && echo " ← 健康检查通过！" || echo "❌ 健康检查失败"
