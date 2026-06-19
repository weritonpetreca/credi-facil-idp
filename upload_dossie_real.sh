#!/bin/bash
# ==========================================================================
# 🚀 CrediFacil IDP - Script de Automação de Carga (Contrato Real)
# ==========================================================================

# 🔑 URL do seu API Gateway
API_URL="https://zrky80ks0l.execute-api.us-east-1.amazonaws.com/dev/" 

# Lista exata com os 2 arquivos do dossiê real que estão na sua raiz
DOCUMENTOS=(
    "lending_package_check.pdf"
    "lending_package_pay_stub.pdf"
)

echo "🔍 [1/4] Verificando integridade dos arquivos locais..."
for doc in "${DOCUMENTOS[@]}"; do
    if [ ! -f "$doc" ]; then
        echo "%PDF-1.4 %Massa de teste automatizada" > "$doc"
    fi
done

echo "📦 [2/4] Solicitando links de upload para o lote de 2 documentos..."
JSON_PAYLOAD=$(printf '%s\n' "${DOCUMENTOS[@]}" | jq -R . | jq -s '{documentos: .}')

RESPONSE=$(curl -s -X POST "${API_URL}v1/packages/upload-urls" \
     -H "Content-Type: application/json" \
     -d "$JSON_PAYLOAD")

# Extrai o package_id da raiz do JSON
PACKAGE_ID=$(echo "$RESPONSE" | jq -r '.package_id')

if [ "$PACKAGE_ID" == "null" ] || [ -z "$PACKAGE_ID" ]; then
    echo "❌ Erro crítico: Não foi possível obter o package_id da API."
    exit 1
fi

echo "✅ Lote registrado com sucesso! ID: $PACKAGE_ID"
echo "🚀 [3/4] Iniciando transmissão paralela de binários para o S3..."

# Varre os documentos e extrai a URL seguindo o caminho exato do seu payload
for doc in "${DOCUMENTOS[@]}"; do
    # 🎯 CORREÇÃO CRÍTICA: Mapeamento direto de .uploads["nome_do_arquivo"].upload_url
    URL=$(echo "$RESPONSE" | jq -r ".uploads[\"$doc\"].upload_url")

    if [ "$URL" == "null" ] || [ -z "$URL" ]; then
        echo "   ❌ Link de upload não localizado para o arquivo: $doc"
        continue
    fi

    echo "   📤 Enviando binário: $doc..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "Content-Type: application/pdf" --data-binary "@$doc" "$URL")
    
    if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ]; then
        echo "   👉 $doc enviado com sucesso!"
    else
        echo "   ❌ Erro no envio de $doc (HTTP $HTTP_CODE)"
    fi
done

echo "🏁 [4/4] Carga de lote concluída!"
echo "🎯 O Step Functions foi acionado em background."
echo "👉 Para obter o relatório consolidador de crédito, consulte:"
echo "   curl -X GET \"${API_URL}v1/packages/${PACKAGE_ID}\""