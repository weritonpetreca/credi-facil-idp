#!/bin/bash
# 🚀 Utilitário de Provisionamento de Usuário Dev para o CrediFácil IDP

# Puxa as variáveis locais do arquivo .env se ele existir
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

if [ -z "$USER_POOL_ID" ] || [ -z "$ANALYST_EMAIL" ] || [ -z "$ANALYST_PASSWORD" ]; then
    echo "❌ Erro: Configure USER_POOL_ID, ANALYST_EMAIL e ANALYST_PASSWORD no seu ambiente ou arquivo .env local."
    exit 1
fi

echo "🏢 Provisionando usuário analista de testes no Cognito de forma segura..."

# 1. Cria o usuário no pool desativando o self-signup
aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$ANALYST_EMAIL" \
    --user-attributes Name=email,Value="$ANALYST_EMAIL" Name=email_verified,Value=true \
    --message-action SUPPRESS

# 2. Crava a senha informada localmente de forma permanente e limpa
aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$ANALYST_EMAIL" \
    --password "$ANALYST_PASSWORD" \
    --permanent

echo "✅ Usuário $ANALYST_EMAIL provisionado com sucesso e pronto para uso no Front-end!"