#!/bin/bash
set -e # Para o script imediatamente se qualquer comando falhar

# Configurações do Projeto
ENVIRONMENT="dev"
PROJECT_NAME="credifacil-idp-project-${ENVIRONMENT}"
TEMPLATE_FILE="infrastructure/template.yaml"
STACK_NAME="credifacil-idp-stack-${ENVIRONMENT}"
SAGEMAKER_ARN="COLOQUE_AQUI_O_ARN_REAL_QUE_VOCE_PEGOU_NO_CONSOLE"

echo "🔍 [DevSecOps] Verificando existência do projeto no Bedrock Data Automation..."

# 1. Tenta buscar o ID de um projeto já existente com esse nome
BDA_PROJECT_ID=$(aws bedrock-data-automation list-data-automation-projects \
  --query "projects[?projectName=='$PROJECT_NAME'].projectId" \
  --output text 2>/dev/null || echo "")

# 2. Se não existir (retorno vazio ou None), cria o projeto programaticamente
if [ -z "$BDA_PROJECT_ID" ] || [ "$BDA_PROJECT_ID" == "None" ]; then
  echo "✨ [IA] Projeto BDA não encontrado. Criando um novo blueprint automágico..."
  
  # Comando CLI para criar o projeto focado em Documentos/Identidade
  BDA_PROJECT_ID=$(aws bedrock-data-automation create-data-automation-project \
    --project-name "$PROJECT_NAME" \
    --project-stage "DEVELOPMENT" \
    --standard-blueprint-configuration '{"blueprints":[{"blueprintArn":"arn:aws:bedrock:us-east-1::blueprint/identity-document"}]}' \
    --query "projectId" \
    --output text)
    
  echo "✅ [IA] Projeto BDA criado com sucesso! ID: $BDA_PROJECT_ID"
else
  echo "😎 [DevSecOps] Projeto BDA existente reutilizado. ID: $BDA_PROJECT_ID"
fi

# 3. Executa o build do SAM para empacotar as atualizações do template
echo "📦 [SAM] Compilando a infraestrutura corporativa..."
sam build --template-file $TEMPLATE_FILE --cached

# 4. Executa o Deploy injetando os parâmetros reais dinamicamente
echo "🚀 [CloudFormation] Iniciando implantação dos recursos na nuvem..."
sam deploy \
  --stack-name $STACK_NAME \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    Environment=$ENVIRONMENT \
    BdaProjectId=$BDA_PROJECT_ID \
    SageMakerWorkteamArn=$SAGEMAKER_ARN \
  --no-confirm-changeset

echo "🎉 [FIM] Toda a esteira IDP Serverless está de pé e integrada com IA!"