# EM Agent

Agente de atendimento via chat no site da **Empório da Música** (loja de instrumentos musicais de Campo Grande - MS). Desafio técnico de AI Engineering.

O agente responde dúvidas sobre produtos, estoque, promoções, pedidos e políticas da loja, consultando os dados reais no Postgres. Também deve permitir a troca entre o agente e um atendente humano (handoff).

## Stack

- **API:** FastAPI (Python 3.13, gerenciado com `uv`)
- **Agente:** LangGraph + `langchain-anthropic`, com estado das conversas no Postgres (`langgraph-checkpoint-postgres`)
- **Banco:** Postgres 17 com pgvector
- **Redis:** controle de handoff entre agente e atendente humano
- **Proxy:** Caddy (serve o `frontend/` e encaminha `/api/*` para a API)

## Estrutura

```
agent/      prompt.py, tools.py, runner.py (agente LangGraph)
db/         schema.sql, seed.py, connection.py, init/ (scripts de inicialização do Postgres)
handoff/    troca agente <-> atendente humano (Redis)
frontend/   site de chat, servido pelo Caddy
data/       CSVs da loja e manual de políticas (PDF)
main.py     app FastAPI
```

## Como rodar

```bash
cp .env.example .env        # ajuste a senha do Postgres e preencha ANTHROPIC_API_KEY
docker compose up -d --build
docker compose run --rm app python -m db.seed    # importa CSVs e políticas no Postgres
```

Teste em `http://localhost/api/health`.

Depois de alterar o código, rode `docker compose build app`: o código é copiado para a imagem, não montado como volume.

## Dados

`db/seed.py` esvazia e recarrega todas as tabelas, então pode ser executado quantas vezes for preciso:

| Tabela | Origem |
|---|---|
| `categories`, `products`, `promotions`, `customers`, `orders`, `order_items` | CSVs em `data/` |
| `policy_chunks` | `data/políticas_da_loja.pdf`, dividido por seção (25 trechos) |

O schema fica em `db/schema.sql` e é aplicado pelo próprio seed.

## Tools do agente

Definidas em `agent/tools.py` (lista `TOOLS`):

| Tool | Uso |
|---|---|
| `search_products` | Busca no catálogo por texto, categoria, faixa de preço e estoque |
| `get_product` | Detalhes de um produto |
| `list_active_promotions` | Promoções ativas com preço final |
| `get_order_status` | Status e rastreio de um pedido; exige o e-mail ou telefone do cliente |
| `search_policies` | Busca no manual de políticas (frete, trocas, garantia, pagamento, horários) |

## Status

- [x] Estrutura de pastas, FastAPI mínimo, Dockerfile e docker-compose
- [x] Importação dos CSVs e do manual de políticas para o Postgres
- [x] Tools do agente, testadas contra o banco
- [x] `agent/prompt.py` (system prompt)
- [x] `agent/runner.py` (grafo LangGraph + checkpointer Postgres)
- [ ] Endpoint de chat na API
- [ ] Handoff para atendente humano (Redis)
- [ ] Frontend do chat
