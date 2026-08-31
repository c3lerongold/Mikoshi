# Mikoshi

Mikoshi é uma IA textual local e orientada a consentimento para criar personas digitais a partir de dados fornecidos pela própria pessoa. Ela preserva a origem de cada informação, não inventa memórias e permite apagar uma fonte junto com todos os dados derivados.

## Requisitos

- Windows 10/11 com Docker Desktop
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.com/) (opcional para respostas geradas; há resposta segura de fallback)

## Início rápido

No Windows, a forma mais simples é dar duplo clique em `iniciar-mikoshi.bat`.
Ele prepara dependências, sobe o banco e abre backend e frontend.

```powershell
Copy-Item .env.example .env
docker compose up -d
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Em outro terminal:

```powershell
cd frontend
npm install
npm run dev
```

Abra `http://localhost:5173`. A documentação da API fica em `http://localhost:8000/docs`.

Para rodar a suíte inicial (com o ambiente Python ativo):

```powershell
pytest tests
```

## Ollama

Para habilitar geração local, instale o Ollama e execute:

```powershell
ollama pull llama3.2
ollama serve
```

No `.env`, mantenha `OLLAMA_BASE_URL=http://localhost:11434` e escolha `OLLAMA_MODEL=llama3.2`. Se o Ollama não estiver disponível, o chat responde apenas com incerteza segura, sem inventar dados.

### Escolher o modelo local

Edite [config/ollama.json](config/ollama.json) e altere `selected_model`. O
arquivo `iniciar-mikoshi.bat` inicia o Ollama e baixa esse modelo na primeira
execução quando `auto_pull_model` estiver como `true`.

```json
{
  "selected_model": "qwen2.5:7b",
  "auto_pull_model": true
}
```

Depois de salvar, reinicie a Mikoshi. O modelo deve estar instalado no Ollama;
o inicializador faz o download automaticamente quando essa opção estiver ativa.

## Primeiro uso

1. Crie uma persona no Dashboard.
2. Na página **Importação**, envie TXT, Markdown, JSON, CSV, PDF, DOCX ou cole texto.
3. Aguarde o processamento; a fonte, os chunks e as memórias ficam ligados por IDs de origem.
4. Use **Chat** para perguntar. Ative Debug para ver memórias, fontes e traços usados.
5. Registre feedback ou uma correção manual para ensinar a persona.

## Privacidade e exclusão

- O armazenamento é local por padrão: PostgreSQL no Docker e Ollama local.
- Não há conectores diretos de Instagram, Google ou YouTube.
- Fontes só são aceitas com `consent_status=granted`.
- `DELETE /sources/{id}` remove chunks, memórias, fatos, preferências, opiniões e traços que vieram exclusivamente daquela fonte.
- `DELETE /personas/{id}` apaga a persona e todas as entidades associadas.

## Variáveis de ambiente

Veja `.env.example`. `DATABASE_URL` aponta para Postgres/pgvector. Troque somente se estiver usando uma instância própria. Não coloque dados pessoais nos logs; os logs usam IDs.

## Estrutura

```text
backend/       API FastAPI e domínio
frontend/      React + TypeScript + Vite
database/      migrations Alembic
ingestion/     parsers e pipeline de importação
processing/    limpeza, chunking e análise conservadora
persona/       perfil e Personality Engine
memory/        recuperação, contradições e consolidação
llm/           clientes Ollama e embeddings configuráveis
api/           contrato OpenAPI (gerado em /openapi.json)
tests/         testes de unidades e API
docs/          decisões de privacidade e arquitetura
scripts/       scripts de inicialização para Windows
```

## Endpoints principais

- `POST/GET /personas`, `GET/DELETE /personas/{id}`
- `POST /personas/{id}/sources` para texto manual e `POST /personas/{id}/sources/upload` para arquivo
- `GET /personas/{id}/sources`, `DELETE /sources/{id}`
- `GET/POST /personas/{id}/memories`, `PATCH/DELETE /memories/{id}`
- `POST /personas/{id}/chat`, `POST /personas/{id}/feedback`, `POST /personas/{id}/interview`
- `GET /personas/{id}/profile`, `POST /personas/{id}/rebuild-profile`
