#!/bin/bash

# Aborta o script imediatamente se qualquer comando falhar (Fail-Fast)
set -e

STACK_NAME="credifacil-idp-dev"
USERNAME="analista@credifacil.com"

echo "======================================================================"
echo "🚀 INICIANDO BOOTSTRAP DINÂMICO DO AMBIENTE: $STACK_NAME"
echo "======================================================================"

# 1. Carrega as variáveis de ambiente locais do arquivo .env
if [ -f .env ]; then
    echo "📝 Carregando credenciais seguras do arquivo .env..."
    # Exporta as variáveis ignorando comentários
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "❌ Erro Crítico: Arquivo .env não localizado na raiz do projeto."
    exit 1
fi

# Valida se a senha foi fornecida no .env
if [ -z "$ANALYST_PASSWORD" ]; then
    echo "❌ Erro Crítico: A variável ANALYST_PASSWORD não está definida no .env."
    exit 1
fi

# 2. INTERROGAÇÃO DINÂMICA (A mágica da autodescoberta)
echo "🔍 Interrogando AWS CloudFormation para capturar o UserPoolId ativo..."
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
    --output text)

# Barreira de segurança contra strings vazias ou nulas
if [ -z "$USER_POOL_ID" ] || [ "$USER_POOL_ID" == "None" ]; then
    echo "❌ Erro Crítico: Não foi possível extrair o 'UserPoolId' dos outputs da stack $STACK_NAME."
    echo "Certifique-se de que o Output 'UserPoolId' está declarado no seu template.yaml."
    exit 1
fi

echo "🎯 UserPoolId ativo localizado com sucesso: $USER_POOL_ID"

# 3. GARANTIR IDEMPOTÊNCIA: Remove o usuário se ele já existir para evitar conflitos de sincronização
echo "♻️ Verificando existência prévia do usuário $USERNAME..."
USER_EXISTS=$(aws cognito-idp admin-get-user --user-pool-id "$USER_POOL_ID" --username "$USERNAME" 2>&1 || true)

if [[ "$USER_EXISTS" == *"UserNotFoundException"* ]]; then
    echo "➕ Usuário limpo. Pronto para criação."
else
    echo "⚠️ Usuário antigo localizado. Removendo para sincronização limpa..."
    aws cognito-idp admin-delete-user --user-pool-id "$USER_POOL_ID" --username "$USERNAME"
    echo "✅ Usuário antigo expurgado."
fi

# 4. CRIAÇÃO DO USUÁRIO DE COMPLIANCE
echo "👤 Criando o usuário analista no pool de identidades..."
aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$USERNAME" \
    --user-attributes Name=email,Value="$USERNAME" Name=email_verified,Value=true \
    --message-action SUPPRESS > /dev/null

echo "✅ Usuário analista registrado com sucesso."

# 5. BYPASS DO DESAFIO FORCE_CHANGE_PASSWORD
echo "🔐 Injetando senha do .env e forçando estado permanente (CONFIRMED)..."
aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$USERNAME" \
    --password "$ANALYST_PASSWORD" \
    --permanent

echo "======================================================================"
echo "🎉 AMBIENTE HOMOLOGADO E LIBERADO PARA LOGIN!"
echo "👤 Usuário: $USERNAME"
echo "🔑 Senha: [INJETADA VIA MOCK .ENV]"
echo "======================================================================"