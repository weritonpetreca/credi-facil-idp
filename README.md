# 🏆🏦 CrediFácil IDP — Vencedor Hack2Hire 2026

![AWS](https://img.shields.io/badge/AWS-Serverless-FF9900?logo=amazon-aws&logoColor=white)
![React](https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8.0-646CFF?logo=vite&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![SAM](https://img.shields.io/badge/IaC-AWS%20SAM-FF9900)
![Bedrock](https://img.shields.io/badge/AI-Amazon%20Bedrock-8C4FFF)
![CloudWatch](https://img.shields.io/badge/Observability-CloudWatch%20%2B%20X--Ray-FF9900)
![Status](https://img.shields.io/badge/status-MVP%20Produção-success)

> 🎯 **Solução serverless de Processamento Inteligente de Documentos (IDP)** para automação completa da análise de crédito com garantia imobiliária, construída de ponta a ponta na AWS com IA generativa e observabilidade em tempo real.

**Desenvolvido pelo Grupo 12** para o **Hack2Hire 2026** — evento promovido pela **Escola da Nuvem** em parceria com a **AWS**. 🚀

---

## 📑 Sumário

- [Sobre o Evento](#-sobre-o-evento)
- [Equipe — Grupo 12](#-equipe--grupo-12)
- [O Desafio (Case A)](#-o-desafio-case-a)
- [A Solução](#-a-solução)
- [Arquitetura](#️-arquitetura)
- [Frontend — UX Moderna](#-frontend--experiência-de-usuário-moderna)
- [Fluxo de Processamento](#️-fluxo-de-processamento-automático)
- [Impacto Mensurável](#-impacto-mensurável)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Como Executar / Deploy](#-como-executar--deploy)
- [Segurança & Observabilidade](#-segurança--observabilidade---produção-ready)
- [Implementado no Hack2Hire](#-hack2hire-2026--o-que-foi-implementado-vs-futuro)
- [Limitações Conhecidas](#️-limitações-conhecidas--em-desenvolvimento)
- [Roadmap](#-roadmap--evolução-da-solução)
- [Estimativa de Custos](#-estimativa-de-custos)
- [Licença](#-licença)
- [Agradecimentos](#-agradecimentos)

---

## 🏆 Sobre o Evento

O **Hack2Hire** é um hackathon promovido pela **Escola da Nuvem** em parceria com a **AWS**, com o objetivo de conectar talentos a oportunidades de mercado através da resolução de desafios reais de negócio usando a nuvem AWS. Este repositório contém a solução desenvolvida pelo **Grupo 12** para o **Case A**.

## 👥 Equipe — Grupo 12

| Integrantes |
|---|
| [Weriton Petreca](https://github.com/weritonpetreca) |
| [Mikael Kobama](https://github.com/Mikael-Kobama) |
| [Juan Levi](https://github.com/Juan92eng) |
| [Ítalo Palhares](https://github.com/ItaloPalhares) |

---

## 🎯 O Desafio (Case A)

A operação de crédito processa, diariamente, **centenas de solicitações de empréstimo com garantia imobiliária**, cada uma composta por múltiplos documentos (identidade, comprovante de renda, extrato bancário, matrícula do imóvel) que precisam ser analisados manualmente.

Essa dependência total de intervenção humana em todas as etapas gera:
- 🐌 Gargalo operacional e lentidão na resposta ao cliente;
- 💸 Aumento de custo por solicitação processada;
- 🔁 Retrabalho na conferência campo a campo;
- 📉 Limitação de escala da operação.

## 💡 A Solução

O **CrediFácil IDP** automatiza ponta a ponta a leitura, classificação, extração e consolidação dos documentos de um dossiê de crédito, usando serviços nativos de IA da AWS, entregando:

- Um **JSON estruturado e padronizado** com todos os dados extraídos do dossiê;
- Uma **planilha Excel consolidada**, pronta para auditoria humana;
- Opcionalmente, um **score de crédito** calculado por regra determinística, com classificação de risco e justificativa técnica.

O analista interage com tudo isso por uma única interface web, sem precisar abrir documento por documento.

---

## 🏗️ Arquitetura

![Arquitetura da Solução CrediFácil](docs/architecture-diagram.png)


A solução é **100% serverless**, na região `us-east-1`, dividida em duas frentes: o **fluxo principal** de processamento e uma camada transversal de **segurança e observabilidade**.

| Camada | Serviço AWS | Papel |
|---|---|---|
| Frontend | **Amazon S3** (Website Hosting) | Interface web moderna (React + Vite) para upload e visualização de resultados |
| API | **Amazon API Gateway** (REST) | Ponto único de entrada HTTP |
| Ingestão | **AWS Lambda** | Geração de URLs pré-assinadas para upload direto |
| Armazenamento (entrada) | **Amazon S3** | Recebe os documentos originais via upload direto do navegador |
| Gatilho automático | **AWS Lambda** | Detecta upload completo e dispara o pipeline |
| Orquestração | **AWS Step Functions** | Máquina de estados `credifacil-idp-pipeline` |
| Extração (IDP) | **Amazon Bedrock Data Automation** | OCR, classificação e extração bruta por documento |
| Estruturação (IA) | **Amazon Bedrock — Nova Pro** | Estrutura os dados em JSON tipado (tool calling) |
| Consolidação (IA) | **Amazon Bedrock — Nova Pro** | Validação cruzada de KYC entre documentos |
| Regra de negócio | Código Python determinístico | Cálculo do score de crédito (auditável, não decidido pela IA) |
| Relatórios | **AWS Lambda** (openpyxl) | Geração de planilhas Excel estilizadas |
| Persistência | **Amazon DynamoDB** | Status do processamento + CRM consolidado do proponente |
| Armazenamento (saída) | **Amazon S3** | Resultados do BDA, JSON estruturado e planilhas |
| Consulta | **AWS Lambda** | Consulta de status e geração de URLs assinadas de download |
| Observabilidade | **AWS Lambda Powertools**, **Amazon CloudWatch**, **AWS X-Ray** | Logs estruturados, métricas e tracing distribuído |
| Segurança | **AWS IAM** (Roles + Permission Boundary) + **OIDC** | Privilégio mínimo, sem credenciais estáticas no CI/CD |
| IaC | **AWS SAM** / CloudFormation | Toda a infraestrutura é reprodutível via código |

## 💻 Frontend — Experiência de Usuário Moderna

O **CrediFácil IDP** conta com uma interface web construída em **React 19** com **Vite** como bundler, oferecendo uma experiência fluida e responsiva:

- **🎯 Upload por Drag-and-Drop:** O usuário arrasta os documentos diretamente na interface, sem complexidade. Upload seguro e direto ao S3 via URLs pré-assinadas.
- **📺 Terminal de Logs em Tempo Real:** Acompanhamento ao vivo de cada etapa do processamento (OCR, validação, extração, score) através de um terminal interativo estilizado, mostrando fase ativa, tempo decorrido e status (LIVE, CONCLUÍDO, ERRO).
- **📊 Dashboard de Score de Crédito:** Visualização instantânea do score calculado (300 a 1000 pontos), classificação de risco (baixo/médio/alto) com cores visuais intuitivas, e explicação estruturada de cada fator avaliado.
- **📥 Download Seguro:** Links assinados para download de planilhas Excel consolidadas e JSON estruturados, com auditoria completa integrada.
- **🌓 Dark Mode:** Tema escuro nativo otimizado para ambientes de análise operacional.

**Stack Frontend:** React 19.2 | Vite 8.0 | Componentes funcionais | Hooks customizados | CSS modular

---

## ⚙️ Fluxo de Processamento Automático

1. **Upload Seguro:** O usuário arrasta os documentos para o drag-and-drop → a API gera URLs pré-assinadas → o navegador faz o upload **direto para o S3**, sem exposição de credenciais.
2. **Disparo Automático:** Quando todos os arquivos do lote chegam ao S3, uma Lambda detecta o evento e inicia automaticamente a execução do Step Functions.
3. **Extração Inteligente:** O **Amazon Bedrock Data Automation** realiza OCR, classificação e extração bruta de cada documento em paralelo.
4. **Estruturação de Dados:** O **Amazon Nova Pro** transforma a extração bruta em JSON estruturado e tipado, por documento, com validações.
5. **Cálculo de Score (Opcional):** Se solicitado, uma segunda chamada ao Nova Pro realiza validação cruzada de KYC entre documentos (consistência de nome, data de nascimento, tipos de documento), e uma **regra determinística em código** (100% auditável) calcula o score final (300 a 1000 pontos) com base em análise de risco, renda e liquidez.
6. **Persistência Imediata:** O resultado é salvo no **DynamoDB** (metadados) e no **S3** (JSON estruturado + Excel consolidado).
7. **Consulta em Tempo Real:** A interface consulta o status continuamente; quando concluído, exibe o relatório completo com links de download seguros (URLs assinadas com validade limitada).

**📊 Impacto Mensurável**

Em aproximadamente **2 minutos**, o CrediFácil IDP processa um pacote com **6 documentos distintos**, classifica cada arquivo e entrega os resultados em JSON estruturado e Excel — uma etapa que, manualmente, levaria entre **20 e 30 minutos** de triagem operador a operador.

Com a automação, o operador deixa de fazer a conferência campo a campo e passa a atuar de forma estratégica: revisando os dados já estruturados e sendo alertado apenas quando algum campo essencial não atingir um nível de confiabilidade adequado.

---

## 📁 Estrutura do Repositório

```bash
.
├── .github/workflows/         # Pipeline de CI/CD (GitHub Actions + OIDC)
│   ├── deploy-dev.yml         # Deploy automático para o ambiente de desenvolvimento
│   └── destroy-dev.yml        # Workflow para desprovisionar o ambiente de dev
├── docs/                      # Documentação e diagramas da arquitetura
│   └── architecture-diagram.png
├── frontend/                  # Interface web — React 19 + Vite
│   ├── src/
│   │   # ...
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── infrastructure/
│   └── template.yaml          # Infraestrutura como código (AWS SAM)
├── src/
│   ├── lambdas/               # Código-fonte de cada função Lambda
│   │   ├── bda_invoker/
│   │   ├── bda_status_poller/
│   │   ├── confidence_checker/
│   │   ├── customer_consolidator/
│   │   ├── excel_generator/
│   │   ├── nova_structurer/
│   │   ├── pipeline_trigger/
│   │   ├── pre_signed_url/
│   │   ├── query_handler/
│   │   ├── result_writer/
│   │   ├── s3_upload_tracker/
│   │   └── notification/
│   ├── layers/dependencies/   # Layer compartilhada (boto3, pydantic, powertools, openpyxl)
│   └── shared/                # Modelos Pydantic, schemas JSON e tools do Bedrock
├── state_machines/
│   └── idp_pipeline.json      # Definição da máquina de estados (Step Functions)
├── tests/                     # Testes automatizados (unitários, integração)
│   └── unit/                  # Testes unitários para as funções Lambda
├── requirements.txt           # Dependências Python do backend
└── LICENSE                    # Licença de uso do projeto (MIT)
```

## 🚀 Como Executar / Deploy

**Pré-requisitos:** AWS CLI configurado, [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html), Python 3.12, acesso habilitado ao **Amazon Bedrock** (Data Automation + Nova Pro) na conta AWS de destino.

```bash
# Build da aplicação
sam build --template-file infrastructure/template.yaml

# Deploy (ambiente de desenvolvimento)
sam deploy \
  --stack-name credifacil-idp-dev \
  --resolve-s3 \
  --no-confirm-changeset \
  --parameter-overrides Environment=dev BdaProjectId=<SEU_BDA_PROJECT_ID> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND
```

> O deploy contínuo está automatizado via **GitHub Actions** (`.github/workflows/deploy-dev.yml`), autenticando na AWS por **OIDC** — sem chaves de acesso estáticas armazenadas no repositório.

---

## 🔐 Segurança & Observabilidade — Produção-Ready

Implementado de forma transversal a todas as Lambdas, ao Step Functions e à API Gateway:

### 🔍 Observabilidade em Tempo Real

- **AWS Lambda Powertools** — Logger estruturado em todas as Lambdas (JSON), com serviços identificados e contexto de execução completo;
- **Amazon CloudWatch** — Logs centralizados com buscas por package_id, tempo de execução e status de processamento; métricas customizadas para custo por requisição;
- **AWS X-Ray** — Tracing distribuído ativo em todas as funções (Tracing: Active nos Globals do SAM template), com mapa de serviços visual e latência ponta-a-ponta.
- **Dashboard Operacional** — Terminal em tempo real no frontend com atualizações contínuas do status de cada etapa.

### 🛡️ Segurança

- **AWS IAM** — Roles com privilégio mínimo, escopadas por recurso, sob *Permission Boundary* obrigatório;
- **OIDC (GitHub Actions)** — Deploy sem credenciais de longa duração (assumindo roles temporárias);
- **S3 Bucket Encryption** — Criptografia AES-256 ativada em todos os buckets;
- **Signed URLs** — Arquivos entram e saem do S3 apenas via URLs pré-assinadas de curta duração (nunca acesso público).

---

## 🏆 Hack2Hire 2026 — O que foi Implementado vs Futuro

### ✅ Implementado Durante o Evento

Tudo funcionando e em produção:

- ✅ **Pipeline IDP Completo:** Extração com Bedrock Data Automation, estruturação com Nova Pro, cálculo de score determinístico;
- ✅ **Frontend React + Vite:** Interface moderna com drag-and-drop, terminal de logs em tempo real, dashboard de score com dark mode;
- ✅ **Observabilidade:** CloudWatch logs estruturados (AWS Lambda Powertools) + X-Ray tracing distribuído em todas as funções;
- ✅ **Upload Seguro:** URLs pré-assinadas, S3 com criptografia AES-256, sem credenciais expostas;
- ✅ **CI/CD via OIDC:** GitHub Actions com autenticação segura na AWS (sem secrets estáticos);
- ✅ **IaC Reprodutível:** 100% da infraestrutura via AWS SAM / CloudFormation;
- ✅ **Tratamento de Confiança:** Validação granular de acurácia do BDA, com alertas para campos críticos;
- ✅ **Relatórios Excel:** Geração automática de planilhas estilizadas com openpyxl;
- ✅ **Testes Unitários:** Base de testes unitários com `pytest` para as principais funções Lambda, garantindo a lógica de negócio;
- ✅ **DynamoDB CRM:** Persistência de dados consolidados do cliente para auditoria e consultas futuras.

## ⚠️ Limitações Conhecidas & Em Desenvolvimento

### Em Desenvolvimento Pós-Hackathon

- 🔄 **Amazon SNS & SQS** — Estrutura desenhada no SAM template, implementação de notificações assíncronas e fila de revisão humana em validação;
- 🔑 **Amazon Cognito** — Autenticação de usuários integrada à API (claims já mapeados nos eventos de exemplo, integração backend em progresso).

### Limitações do MVP

- O endpoint manual `/v1/packages/{packageId}/process` existe na infraestrutura mas não é utilizado pelo fluxo atual (disparo é 100% automático via evento de S3).

## 🛣️ Roadmap — Evolução da Solução

### 🔜 Próximas Iterações (Curto Prazo)

- 🔔 **SNS/SQS Completo** — Ativar notificações de conclusão e fila de revisão humana (estrutura já existe);
- 🔐 **Cognito com MFA** — Integração de autenticação de usuários com multi-factor authentication;
- 🔄 **WebSocket / AppSync** — Atualização real-time de status em vez de polling;
- 🧪 **Testes Automatizados** — Suite de testes com `pytest` + `moto` para Lambdas e Step Functions.

### 🚀 Médio Prazo — Escalabilidade & Performance

- 🌐 **Amazon CloudFront** — CDN na frente do frontend e downloads (cache, HTTPS, WAF integrado);
- ⚡ **Paralelismo Real** — Migração de BDA para *Map state* nativo do Step Functions (sem risco de timeout);
- 📊 **Batching Automático** — Processamento agrupado de múltiplos pacotes (reduz custos de API);
- 💾 **PITR + Backups** — Point-in-Time Recovery e backup automático no DynamoDB.

### 🔒 Longo Prazo — Compliance & Segurança Avançada

- 🛡️ **AWS Shield / WAF** — Proteção contra DDoS e ataques web;
- 🔍 **GuardDuty** — Detecção de ameaças e comportamentos anômalos;
- 🔐 **KMS Customizado** — Chaves de criptografia gerenciadas pelo cliente para S3 e DynamoDB;
- 📋 **Compliance Audit Trail** — Log imutável de todas as operações sensíveis (CloudTrail + S3 Object Lock).

## 💰 Estimativa de Custos

Considerando um cenário de aproximadamente **750 solicitações diárias**, foi realizada uma estimativa de custos com base nos serviços utilizados (Lambda, API Gateway, DynamoDB, S3, Bedrock, IAM, Step Functions e EventBridge).

🔗 [Confira a estimativa completa na Calculadora de Preços da AWS](https://calculator.aws/#/estimate?id=c0c37981b850386fe457dbaa52513264ab875d16)

---

## 📜 Licença

Este projeto é distribuído sob a **Licença MIT**. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 🙏 Agradecimentos

À **Escola da Nuvem** e à **AWS** pela organização do Hack2Hire e pela oportunidade de aplicar serviços de nuvem e IA generativa em um desafio real de negócio.

---

<p align="center"><b>Grupo 12 — Hack2Hire 2026 — Case A</b></p>
