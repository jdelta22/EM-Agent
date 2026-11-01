# CLAUDE.md

Agente de atendimento via chat para a Empório da Música (loja de instrumentos, Campo Grande - MS). Desafio técnico. Visão geral e como rodar: `README.md`.

## Comandos

- Subir tudo: `docker compose up -d --build`
- Importar dados: `docker compose run --rm app python -m db.seed`
- Rebuild após mudar código: `docker compose build app` (o código é copiado na imagem, não há volume)
- Dependências: `uv add <pacote>` (atualiza `pyproject.toml` e `uv.lock`; o Dockerfile usa `uv sync --frozen`)
- Rodar scripts Python no host: `uv run python ...` (o Postgres não expõe porta no host; para testar contra o banco use `docker compose run --rm app ...`)

## Decisões e convenções

- Idioma: código e identificadores em inglês; prompts, mensagens para o cliente e docs em português.
- Stack LangGraph: `langchain-anthropic` para o modelo (não usar o SDK `anthropic` direto), `psycopg` 3 (não psycopg2), checkpointer `langgraph-checkpoint-postgres`.
- Handoff (Redis): chave `handoff:{conversation_id}` = `human`, sempre com validade (`HANDOFF_TIMEOUT_SECONDS`, padrão 1800). Chave ausente = `agent`, então o timeout devolve a conversa ao agente sem job agendado; cada mensagem do atendente renova a validade. Não existe estado "encerrada": uma conversa é só um `conversation_id` guardado pelo cliente, e "nova conversa" = id novo.
- O agente transfere com a tool `transfer_to_human` (pega o id de `config["configurable"]["thread_id"]`, grava a chave e publica evento no canal `handoff:events`). Em modo humano, `POST /api/chat` grava a mensagem do cliente no histórico (checkpoint) e avisa o atendente; mensagens do atendente entram como `AIMessage` com prefixo `[Atendente humano]` e `name="attendant"`, e o prompt explica isso (sem a explicação o modelo atribui a mensagem a si mesmo e "se corrige").
- Endpoints do atendente (`handoff/api.py`, sob `/api/attendant`) exigem o header `X-Attendant-Token` = `ATTENDANT_TOKEN`; sem a variável, todos recusam (401). O cliente recebe respostas do atendente por polling em `GET /api/chat/{id}?after=N`.
- Políticas são buscadas com full-text search do Postgres (config `portuguese` + `unaccent`), não com embeddings: o Claude não gera embeddings e o manual tem só 25 trechos. O pgvector está instalado para uso futuro.
- `search_policies` casa pelas 5 primeiras letras de cada palavra (`word:*`), porque o stemmer do Postgres não une devolver/devolução nem rastrear/rastreamento.
- Preços: promoções não são cumulativas e o desconto PIX de 5% não vale sobre preço promocional. A query já devolve `promo_price_brl` e `pix_price_brl` (este só quando não há promoção), e o agente não deve recalcular.
- O system prompt (`agent/prompt.py`) é estático de propósito: o modelo usa thinking adaptativo (não dá para desligar) e assina os blocos de thinking contra o system prompt; se ele mudar entre turnos, a API devolve 400 ao reaproveitar o histórico. Dados que variam, como data/hora e loja aberta/fechada, vêm de tool (`get_store_status`). Não interpolar nada no prompt. O modelo também não aceita `temperature` fora do padrão.
- `POST /api/chat` (`main.py`) consulta `handoff:{conversation_id}` no Redis antes do grafo. Se o Redis falhar, responde 503 em vez de seguir com o agente, para não falar por cima de um humano.
- `get_order_status` exige e-mail ou telefone do cliente e dá a mesma resposta para pedido inexistente e pedido de outra pessoa.
- Caddy serve `frontend/` e encaminha `/api/*` para `app:8000`; por isso as rotas da API ficam sob `/api`.
- O repositório é público (desafio técnico). Nunca commitar `.env`, que está no `.gitignore`.

## Regras do negócio que o prompt do agente precisa cobrir

Vêm de `data/políticas_da_loja.pdf` (seção 7):

- Tom informal mas profissional, como um amigo que entende de música.
- Nunca informar preço, estoque ou prazo sem consultar as tools.
- A loja vende só instrumentos: pedir de acessórios (cordas, palhetas, cabos, pedais, amplificadores, cases) deve ser redirecionado com educação.
- Produto sem estoque: sugerir alternativas disponíveis. Descontinuado: oferecer equivalente. Promoção vencida: dizer com transparência e mostrar o preço atual.
- Reclamação: ouvir, registrar e encaminhar ao responsável (retorno em 24 horas úteis), o que é um caso para handoff.
- Fora do horário (seg-sex 09-18h, sáb 09-13h), informar quando a loja volta.

## Pontos em aberto

- O PDF tem inconsistências: WhatsApp (67) 3341-4444 na seção 1.2 e (67) 3321-4500 na seção 7; e-mail com e sem acento. Confirmar qual é o correto antes de o agente repetir esses dados.
- `search_policies` às vezes ranqueia garantia (8.1) acima de trocas por defeito (4.2); aceitável, pois o agente recebe 3 trechos.

## Próximos passos

1. `frontend/`: chat simples (`index.html`) servido pelo Caddy, com polling de `GET /api/chat/{id}` enquanto `handled_by` for `human`. Uma tela de atendente (usando `/api/attendant/*`) é opcional.
2. Antes de publicar: limite de requisições por IP em `/api/chat` (hoje qualquer um gasta a chave da Anthropic).
