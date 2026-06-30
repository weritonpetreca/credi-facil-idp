# 🏆🏦 CrediFácil IDP — Vencedor Hack2Hire 2026

![AWS](https://img.shields.io/badge/AWS-Serverless-FF9900?logo=amazon-aws&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8.0-646CFF?logo=vite&logoColor=white)
![SAM](https://img.shields.io/badge/IaC-AWS%20SAM-FF9900)
![Bedrock](https://img.shields.io/badge/AI-Amazon%20Bedrock-8C4FFF)
![Cognito](https://img.shields.io/badge/Auth-Amazon%20Cognito-DD344C)
![Status](https://img.shields.io/badge/status-Pós--Hackathon%20em%20Evolução-blue)

> 🎯 **Solução serverless de Processamento Inteligente de Documentos (IDP)** para automação completa da análise de crédito com garantia imobiliária, construída 100% na AWS com IA generativa, segurança B2B e observabilidade em tempo real.

Desenvolvida pelo **Grupo 12** para o **Hack2Hire 2026** (Escola da Nuvem + AWS), atualmente em evolução para um produto comercializável.

---

## Sumário

- [Sobre o Projeto](#-sobre-o-projeto)
- [Arquitetura](#️-arquitetura)
- [Decisões Técnicas](#-decisões-técnicas)
- [Stack Completa](#-stack-completa)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Como Executar](#-como-executar)
- [Segurança e Observabilidade](#-segurança-e-observabilidade)
- [Roadmap Pós-Hackathon](#-roadmap-pós-hackathon)
- [Equipe](#-equipe)

---

## 🎯 Sobre o Projeto

### O Problema

Operações de crédito processam diariamente centenas de solicitações de empréstimo com garantia imobiliária, cada uma composta por múltiplos documentos (identidade, comprovante de renda, extrato bancário, matrícula do imóvel) analisados manualmente — processo lento, sujeito a erro humano e sem escala.

### A Solução

O **CrediFácil IDP** automatiza ponta a ponta a leitura, classificação, extração e consolidação de um dossiê de crédito, entregando em aproximadamente 2 minutos o que levaria 20 a 30 minutos de triagem manual:

- **JSON estruturado** com todos os dados extraídos e validados
- **Planilha Excel consolidada** pronta para auditoria
- **Score de crédito determinístico** (300 a 1000 pontos), 100% calculado em código e auditável
- **Alerta de revisão humana** quando campos críticos têm baixa confiança de extração

O produto é voltado ao mercado **B2B de acesso restrito**: correspondentes bancários, cooperativas de crédito e fintechs que já operam com crédito imobiliário.

---

## 🏗️ Arquitetura

![Arquitetura da Solução CrediFácil](docs/architecture-diagram.png)

A solução é **100% serverless** em `us-east-1`, organizada em três camadas:

### Camada de Ingestão e Autenticação

O fluxo começa com o usuário autenticado via **Amazon Cognito** (acesso restrito, sem auto-cadastro). A API Gateway valida o token JWT antes de qualquer invocação. O frontend solicita URLs pré-assinadas (Presigned POST com `content-length-range`) e faz o upload **diretamente ao S3**, sem passar por nenhuma Lambda no caminho crítico. Isso mantém custo baixo e evita gargalos.

Quando todos os arquivos de um pacote chegam, o `s3_upload_tracker` detecta a conclusão do lote via contador atômico com lock condicional no DynamoDB, evitando disparos duplicados, e inicia a execução do Step Functions.

### Camada de Orquestração (Step Functions)

O pipeline principal é uma máquina de estados que coordena:

1. **BDA Invoker:** dispara um `invoke_data_automation_async` por documento, em paralelo, cada um com sua subpasta isolada de saída no S3.
2. **BDA Status Poller:** aguarda a conclusão de todos os jobs do Bedrock Data Automation.
3. **Confidence Checker:** avalia os campos críticos de cada documento contra um limiar de 80% de confiança. Campos abaixo do limiar disparam um evento `LowConfidenceFieldsDetected` no EventBridge customizado, que roteia para a fila de revisão humana (SQS) com DLQ e alarme no CloudWatch.
4. **Nova Structurer:** usa `amazon.nova-lite-v1:0` com tool calling forçado (`toolChoice`) para estruturar os dados brutos do BDA em JSON tipado por documento.
5. **Excel Generator:** gera planilhas estilizadas por documento via `Map` state paralelo.
6. **Customer Consolidator (opcional):** chama `amazon.nova-pro-v1:0` para validação cruzada de KYC entre documentos (consistência de nome, data de nascimento, tipo de documento), depois calcula o score determinístico em código Python puro.
7. **Result Writer:** persiste o resultado final no DynamoDB (tabela de pacotes e CRM de clientes).
8. **Notification:** publica no SNS de conclusão ou de erro.

### Camada de Observabilidade e Segurança

Transversal a todo o sistema: Lambda Powertools com logs estruturados em JSON, X-Ray ativo em todas as funções, métricas customizadas de tokens consumidos e custo estimado via Embedded Metric Format (EMF), e AWS Budgets com alarme de billing.

---

## 🧠 Decisões Técnicas

### Por que Presigned POST em vez de PUT?

O frontend usa `generate_presigned_post` com a condição `content-length-range`. Isso faz o **próprio S3** rejeitar uploads que excedam 10 MB, sem depender da Lambda para checar o tamanho declarado pelo cliente. Uma presigned PUT padrão não impõe essa barreira fisicamente.

### Por que tool calling em vez de prompt de texto livre?

O `nova_structurer` usa `converse()` com `toolConfig` e `toolChoice` forçado em vez de pedir JSON em texto livre. Com tool calling, o Bedrock garante estruturalmente que a resposta seja um objeto válido conforme o schema definido — sem parsing manual de markdown fences ou risco de texto extra na resposta.

### Por que Nova Lite para estruturação por documento e Nova Pro para consolidação?

A estruturação por documento é uma tarefa de extração com schema definido: o tool calling remove a necessidade de raciocínio livre. Nova Lite resolve bem e custa 13 vezes menos que o Pro. A consolidação cruzada de KYC envolve comparação entre múltiplos documentos e classificação de risco, onde o modelo mais capaz justifica o custo marginal. O score final, porém, é sempre calculado em código determinístico, nunca decidido pela IA.

### Por que acesso B2B restrito?

Cada pacote processado tem custo real de Bedrock. Acesso público e auto-cadastrado significaria que qualquer pessoa geraria custo sem ser um cliente pagante. Além disso, o CrediFácil processa documentos sensíveis (identidade e renda) para uma decisão que afeta acesso a crédito — isso só faz sentido dentro de uma relação contratual com uma empresa que tem base legal (LGPD) para coletar esses dados dos próprios clientes dela.

---

## 📦 Stack Completa

| Camada | Tecnologia | Papel |
|---|---|---|
| Frontend | React 19.2, Vite 8.0 | Interface web com drag-and-drop, terminal de logs em tempo real e dashboard de score |
| CDN | Amazon CloudFront + OAC | Distribuição do frontend via HTTPS com cache e invalidação automatizada no CI/CD |
| Autenticação | Amazon Cognito User Pools | Autenticação B2B restrita (sem auto-cadastro), com verificação de e-mail |
| API | Amazon API Gateway (REST) | Ponto único de entrada com Cognito Authorizer, throttling e CORS |
| Ingestão | AWS Lambda, Amazon S3 | Geração de URLs Presigned POST + upload direto pelo navegador |
| Orquestração | AWS Step Functions | Pipeline de estados com Map state para geração paralela de Excel |
| Extração (IA) | Amazon Bedrock Data Automation | OCR, classificação e extração bruta por documento |
| Estruturação (IA) | Amazon Bedrock, Nova Lite | Estruturação JSON via tool calling forçado |
| Consolidação (IA) | Amazon Bedrock, Nova Pro | Validação cruzada de KYC entre documentos |
| Score de crédito | Python determinístico | Scorecard de 300 a 1000 pontos, 100% auditável, nunca decidido pela IA |
| Relatórios | AWS Lambda, openpyxl | Planilhas Excel estilizadas por documento |
| Armazenamento | Amazon DynamoDB (PAY_PER_REQUEST) | Status de pacotes e CRM de clientes |
| Armazenamento | Amazon S3 | Documentos de entrada, saídas do BDA, JSONs e planilhas |
| Mensageria | Amazon SNS | Notificações de conclusão e erro |
| Revisão humana | Amazon EventBridge, SQS, DLQ | Roteamento de campos de baixa confiança para fila de revisão com alarme |
| Observabilidade | Lambda Powertools, CloudWatch, X-Ray | Logs JSON estruturados, métricas de custo e tracing distribuído |
| FinOps | AWS Budgets + CloudWatch Alarm | Alertas de billing antes de qualquer surpresa de fatura |
| IaC | AWS SAM / CloudFormation | 100% da infraestrutura reprodutível via código |
| CI/CD | GitHub Actions + OIDC | Deploy sem credenciais estáticas; invalidação de cache CloudFront automatizada |
| Runtime | Python 3.12, arm64 (Graviton) | ~20% mais barato que x86 para a mesma carga |

---

## 📁 Estrutura do Repositório

```
.
├── .github/
│   └── workflows/
│       ├── deploy-dev.yml          # Deploy para o ambiente de desenvolvimento (branch: develop)
│       └── destroy-dev.yml         # Teardown completo do ambiente (purga buckets antes de deletar a stack)
│
├── docs/
│   ├── architecture-diagram.png   # Diagrama da arquitetura
│   └── samples/                   # PDFs de amostra para testes locais
│       ├── lending_package_check.pdf
│       └── lending_package_pay_stub.pdf
│
├── frontend/
│   ├── src/
│   │   ├── components/            # Componentes React (ResultPanel, StatusTerminal, ScoreExplainPanel, …)
│   │   ├── hooks/
│   │   │   └── useDocumentPipeline.js  # Hook principal de polling de status e upload
│   │   └── utils/
│   │       └── resultHelpers.js
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── infrastructure/
│   └── template.yaml              # Infraestrutura como código (AWS SAM)
│
├── scripts/
│   └── bootstrap-dev.sh           # Provisionamento local de usuário Cognito pós-deploy (lê .env)
│
├── src/
│   ├── lambdas/
│   │   ├── bda_invoker/           # Dispara jobs paralelos no Bedrock Data Automation
│   │   ├── bda_status_poller/     # Verifica status dos jobs do BDA
│   │   ├── confidence_checker/    # Avalia confiança dos campos críticos, emite evento de revisão
│   │   ├── customer_consolidator/ # Validação cruzada de KYC + scorecard determinístico
│   │   ├── excel_generator/       # Gera planilhas estilizadas com openpyxl
│   │   ├── notification/          # Publica resultado no SNS (conclusão ou erro)
│   │   ├── nova_structurer/       # Estrutura saída bruta do BDA via tool calling (Nova Lite)
│   │   ├── pipeline_trigger/      # Endpoint manual de disparo do pipeline com idempotência
│   │   ├── pre_signed_url/        # Gera Presigned POST com barreiras de tamanho no S3
│   │   ├── query_handler/         # Consulta status e gera URLs de download assinadas
│   │   ├── result_writer/         # Persiste resultado no DynamoDB (pacotes e CRM de clientes)
│   │   └── s3_upload_tracker/     # Detecta conclusão do lote via contador atômico
│   ├── layers/
│   │   └── dependencies/          # Lambda Layer compartilhada (boto3, Powertools, pydantic, openpyxl)
│   └── shared/
│       ├── models.py              # Modelos Pydantic de domínio
│       ├── tools.py               # Especificação das tools do Bedrock (tool calling)
│       └── schemas/
│           └── loan_packages_schema.json
│
├── state_machines/
│   └── idp_pipeline.json          # Definição do Step Functions (ASL)
│
├── tests/
│   └── unit/                      # 30 testes unitários com pytest + moto (100% passando)
│
├── .gitignore
├── pytest.ini
├── requirements.txt               # Dependências de desenvolvimento e testes
└── README.md
```

---

## 🚀 Como Executar

### Pré-requisitos

- AWS CLI configurado com credenciais e permissões adequadas
- AWS SAM CLI instalado
- Python 3.12
- Node.js 20+ (para o frontend)
- Acesso habilitado ao **Amazon Bedrock** na conta (Data Automation + Nova Lite + Nova Pro)
- Um **BDA Project** criado no Bedrock Data Automation com os blueprints configurados

### 1. Deploy da infraestrutura

```bash
# Build da aplicação (empacota Lambdas e Layers)
sam build --template-file infrastructure/template.yaml

# Deploy no ambiente de desenvolvimento
sam deploy \
  --stack-name credifacil-idp-dev \
  --resolve-s3 \
  --no-confirm-changeset \
  --parameter-overrides \
    Environment=dev \
    BdaProjectId=<SEU_BDA_PROJECT_ID> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND
```

> O deploy contínuo está automatizado via GitHub Actions com autenticação OIDC (sem chaves de acesso estáticas). O push para `develop` aciona o deploy completo incluindo build e publicação do frontend.

### 2. Provisionar o usuário de acesso

Após o deploy, crie um arquivo `.env` na raiz do projeto (nunca versionado):

```env
USER_POOL_ID=us-east-1_XXXXXXXXX
ANALYST_EMAIL=seu-email@exemplo.com
ANALYST_PASSWORD=SuaSenha@Forte2026
```

Execute o script de bootstrap:

```bash
chmod +x scripts/bootstrap-dev.sh
./scripts/bootstrap-dev.sh
```

> O `USER_POOL_ID` está disponível no output da stack via `aws cloudformation describe-stacks --stack-name credifacil-idp-dev --query "Stacks[0].Outputs"`.

### 3. Acessar o frontend

A URL do frontend é gerada automaticamente no deploy. Para obtê-la:

```bash
aws cloudformation describe-stacks \
  --stack-name credifacil-idp-dev \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendCloudFrontUrl'].OutputValue" \
  --output text
```

### 4. Destruir o ambiente

```bash
# Via workflow (recomendado): dispara destroy-dev.yml manualmente no GitHub Actions
# Ou localmente:
aws s3 rm s3://credifacil-docs-entrada-<ACCOUNT_ID>-dev --recursive
aws s3 rm s3://credifacil-docs-saida-<ACCOUNT_ID>-dev --recursive
aws s3 rm s3://credifacil-idp-frontend-<ACCOUNT_ID>-dev --recursive
sam delete --stack-name credifacil-idp-dev --no-prompts
```

### 5. Executar os testes

```bash
pip install -r requirements.txt
AWS_DEFAULT_REGION=us-east-1 pytest tests/unit -v
```

---

## 🔐 Segurança e Observabilidade

### Segurança

| Item | Implementação |
|---|---|
| Autenticação B2B | Amazon Cognito com `AllowAdminCreateUserOnly: true` — sem auto-cadastro público |
| Autorização de API | `CognitoAuthorizer` como default authorizer em todos os endpoints sensíveis |
| Upload seguro | Presigned POST com `content-length-range` — o S3 rejeita arquivos acima de 10 MB na borda |
| Credenciais no CI/CD | OIDC (GitHub Actions assume role temporária via `aws-actions/configure-aws-credentials@v4`) — sem chaves estáticas |
| IAM com privilégio mínimo | Roles escopadas por recurso em cada Lambda |
| Criptografia em repouso | AES-256 (SSE-S3) em todos os buckets |
| Throttling de API | `ThrottlingRateLimit: 5 req/s`, `ThrottlingBurstLimit: 10` |
| Segredos locais | Credenciais de desenvolvimento via `.env` (nunca versionado) |

### Observabilidade

- **AWS Lambda Powertools:** logs estruturados em JSON com `service`, `package_id` e nível de severidade em todas as funções
- **AWS X-Ray:** tracing distribuído ativo (mapa de serviços + latência ponta a ponta)
- **CloudWatch Metrics (EMF):** `BedrockInputTokens`, `BedrockOutputTokens` e `EstimatedGenAiCostUSD` por `package_id`, emitidos pelo `nova_structurer`
- **AWS Budgets + CloudWatch Alarm:** alerta de billing configurado para a conta — proteção contra surpresas de fatura em conta pessoal de desenvolvimento
- **DLQ Alarm:** alarme no CloudWatch disparado quando mensagens chegam à DLQ de revisão humana

---

## 🛣️ Roadmap Pós-Hackathon

Este projeto segue um SRS detalhado com fases priorizadas por custo e risco. O estado atual:

### ✅ Concluído (Fase -1 e Fase 0 parcial)

- ✅ **Cognito B2B** com acesso restrito e autorização em todos os endpoints
- ✅ **Presigned POST** com barreiras físicas de tamanho no S3
- ✅ **Métricas de custo** via EMF (tokens e custo estimado por pacote)
- ✅ **AWS Budgets + alarme de billing** para conta pessoal de desenvolvimento
- ✅ **Notificações SNS** de conclusão e erro com `NotifySuccess`/`NotifyError`
- ✅ **Fila de revisão humana** (SQS + DLQ + EventBridge + alarme) para campos de baixa confiança
- ✅ **`bootstrap-dev.sh`** para provisionamento seguro de usuário local pós-deploy
- ✅ **Remoção de exposição de dados sensíveis** (`cfn_error_trace.json`, senha hardcoded no CI)
- ✅ **`BDA_PROFILE_ARN` via CloudFormation** eliminando chamada STS em runtime
- ✅ **30/30 testes unitários** passando

### 🔄 Em andamento (Fase 1 — Paralelismo e Eventos)

- 🔄 **Task Token + EventBridge para o BDA:** eliminar o polling do `bda_status_poller` usando a notificação nativa do Bedrock Data Automation — cada documento retoma individualmente quando seu job termina, sem custo de polling
- ⏳ **Map state por documento no `nova_structurer`:** isolar a falha por documento em vez de abortar o lote inteiro
- ⏳ **Retry/Catch padronizados:** backoff exponencial e captura de erros em todos os `Task` da state machine
- ⏳ **Fechamento do loop de revisão humana:** a pipeline deve pausar (Task Token) quando há campos de baixa confiança, aguardando confirmação humana antes de continuar
- ⏳ **Migração do `customer_consolidator` para Nova Lite + tool calling** (redução de custo de ~13×)
- ⏳ **Bedrock Guardrails (Prompt Attack):** proteção contra prompt injection via conteúdo de PDFs maliciosos

### 🔜 Fase 2 (Compliance e Hardening)

- WAF básico, CloudTrail, Cognito com MFA
- Blueprints para documentos brasileiros (RG/CNH, holerite CLT, extrato bancário BR)
- Documentação formal de LGPD e postura frente ao Marco Legal da IA

---

## 👥 Equipe

| Integrante |
|---|
| [Weriton Petreca](https://github.com/weritonpetreca) |
| [Mikael Kobama](https://github.com/Mikael-Kobama) |
| [Juan Levi](https://github.com/Juan92eng) |
| [Ítalo Palhares](https://github.com/ItaloPalhares) |

---

## 💰 Estimativa de Custos

Para referência, a estimativa original do hackathon para 750 solicitações diárias está disponível na [Calculadora de Preços da AWS](https://calculator.aws/#/estimate?id=c0c37981b850386fe457dbaa52513264ab875d16). O custo por pacote individual gira em torno de US$ 0,64 só de Bedrock Data Automation (~8 documentos × 2 páginas × US$ 0,040/página), mais os tokens de Nova Lite/Pro medidos via EMF.

---

## 📜 Licença

Distribuído sob a **Licença MIT**. Veja [LICENSE](LICENSE) para mais detalhes.

---

<p align="center"><b>Grupo 12 — Hack2Hire 2026 — Case A</b></p>