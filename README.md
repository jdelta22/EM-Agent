# EM Agent

Agente de atendimento via chat no site da **Empório da Música** (loja de instrumentos musicais de Campo Grande - MS). Desafio técnico de AI Engineering.

O agente responde dúvidas sobre produtos, estoque, promoções, pedidos e políticas da loja, consultando os dados reais no Postgres. Quando o assunto exige uma pessoa (reclamação, pedido de atendente), ele transfere a conversa para um **atendente humano**, que responde por um painel web. Se o atendente sumir, o agente retoma sozinho.

## Sumário

- [Stack](#stack)
- [Como rodar](#como-rodar)
- [Como usar](#como-usar): [site e chat](#1-site-e-chat-do-cliente) · [painel do atendente](#2-painel-do-atendente) · [testar a transferência](#3-testando-a-transferência-para-um-humano)
- [Configuração](#configuração-env)
- [Como funciona](#como-funciona)
- [API](#api)
- [Testes manuais](#testes-manuais)
- [Problemas comuns](#problemas-comuns)
- [Estrutura](#estrutura) · [Dados](#dados) · [Tools do agente](#tools-do-agente)

## Stack

- **API:** FastAPI (Python 3.13, gerenciado com `uv`)
- **Agente:** LangGraph + `langchain-anthropic`, com o histórico das conversas no Postgres (`langgraph-checkpoint-postgres`)
- **Banco:** Postgres 17 com pgvector
- **Redis:** estado do handoff (agente ou humano) e avisos em tempo real para o atendente
- **Proxy:** Caddy (serve o `frontend/` e encaminha `/api/*` para a API)
- **Frontend:** HTML, CSS e JS puros, sem etapa de build

## Como rodar

### Pré-requisitos

- **Docker** com Docker Compose (no Windows e no Mac, o Docker Desktop precisa estar aberto).
- Uma **chave da API da Anthropic** (`ANTHROPIC_API_KEY`).
- As portas **80** e **443** livres no seu computador (o Caddy usa as duas).

Python e `uv` só são necessários se você for rodar scripts fora do Docker (veja [Testes manuais](#testes-manuais)).

### Passo a passo

**1. Crie o `.env`** a partir do exemplo:

```bash
cp .env.example .env
```

**2. Edite o `.env`** e preencha, no mínimo:

| Variável | O que colocar |
|---|---|
| `POSTGRES_PASSWORD` | Qualquer senha (troque o `change-me`) |
| `ANTHROPIC_API_KEY` | Sua chave da Anthropic |
| `ATTENDANT_TOKEN` | Senha de acesso ao painel do atendente (veja abaixo como gerar) |

Para gerar um token de atendente forte:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Se você não tiver Python no computador, qualquer senha longa serve.

> O `.env` guarda segredos e **não é versionado** (está no `.gitignore`). Nunca o commite: o repositório é público.

**3. Suba os serviços:**

```bash
docker compose up -d --build
```

Isso sobe quatro containers: `app` (API), `postgres`, `redis` e `caddy`. Na primeira vez o build leva alguns minutos. Confira se todos estão de pé:

```bash
docker compose ps
```

**4. Carregue os dados da loja** (somente na primeira vez, ou para restaurar os dados originais):

```bash
docker compose run --rm app python -m db.seed
```

Isso cria as tabelas e importa os CSVs e o manual de políticas. Pode ser repetido à vontade: o comando esvazia e recarrega tudo.

**5. Verifique:**

```bash
curl http://localhost/api/health
# {"status":"ok"}
```

Pronto. Agora é só abrir o navegador (próxima seção).

### Parar e reiniciar

```bash
docker compose stop              # para os containers, mantendo os dados
docker compose start             # volta
docker compose down              # remove os containers, mantendo os dados
docker compose down -v           # CUIDADO: remove também os dados (banco, conversas, Redis)
```

### Depois de alterar o código

| O que mudou | O que fazer |
|---|---|
| Código Python (`agent/`, `handoff/`, `main.py`, `db/`) | `docker compose up -d --build app` (o código é copiado para a imagem, não montado como volume) |
| `frontend/` (HTML, CSS, JS) | Nada: a pasta é montada no Caddy. Basta recarregar a página (Ctrl+F5) |
| `Caddyfile` | `docker compose restart caddy` |
| `.env` | `docker compose up -d app` (recria o container com os novos valores) |

## Como usar

Com tudo no ar, são três endereços (troque `localhost` pelo seu domínio se tiver mudado o `SITE_ADDRESS`):

| Endereço | Para quem | O que é |
|---|---|---|
| http://localhost/ | Cliente | Landing page da loja, com botão para o chat |
| http://localhost/chat | Cliente | Chat com o assistente virtual |
| http://localhost/atendente | Equipe da loja | Painel do atendente (exige token) |

### 1. Site e chat do cliente

1. Abra **http://localhost/** e clique em **Conversar com a gente** (ou vá direto a http://localhost/chat).
2. Clique numa das sugestões ou escreva sua pergunta. Enter envia; Shift+Enter quebra a linha.
3. O assistente consulta o banco da loja a cada resposta. Exemplos para testar:
   - "Tem violão de nylon da Yamaha? Quanto custa?"
   - "Quais promoções estão ativas?"
   - "Qual o prazo para devolução?"
   - "Quero saber do meu pedido" (ele vai pedir o número do pedido e o e-mail ou telefone cadastrado)
   - "Vocês vendem corda de violão?" (a loja só vende instrumentos, então ele redireciona com educação)
4. A conversa fica salva no navegador: ao recarregar a página, ela volta. **Nova conversa** (no topo) começa do zero.

O selo no topo do chat mostra quem está respondendo: **Assistente virtual** ou **Atendente da loja**.

### 2. Painel do atendente

1. Abra **http://localhost/atendente**.
2. Digite o valor de `ATTENDANT_TOKEN` que você colocou no `.env` e clique em **Entrar**. O token fica guardado só na aba do navegador (some ao fechá-la).
3. O indicador **Ao vivo** (no topo) confirma que o painel está recebendo avisos em tempo real. Se aparecer **Reconectando…**, ele tenta de novo sozinho.

O painel tem duas áreas:

- **Fila (esquerda):** as conversas que estão com um humano, a mais recente primeiro. Cada item mostra o resumo que o assistente escreveu ao transferir (o que aconteceu e o que o cliente quer), um contador de mensagens novas e quanto tempo falta para a conversa voltar ao assistente. O número de mensagens novas também aparece no título da aba. Se você permitir as notificações do navegador, ele avisa de novas transferências com a aba em segundo plano.
- **Conversa (direita):** o histórico completo, com o assistente identificado como "Assistente (IA)". Escreva no campo de baixo e envie com Enter.

Ações:

| Ação | Efeito |
|---|---|
| **Enviar** uma resposta | O cliente recebe em poucos segundos e o tempo de atendimento é renovado |
| **Devolver ao assistente** | A conversa volta para o agente, e o cliente é avisado no chat |
| **Sair** | Apaga o token da aba |

> Se ninguém do atendimento responder por um tempo (30 minutos por padrão, ajustável com `HANDOFF_TIMEOUT_SECONDS`), a conversa volta sozinha para o assistente. Cada resposta do atendente reinicia essa contagem.

### 3. Testando a transferência para um humano

Para ver o fluxo completo, use duas janelas (ou uma janela normal e uma anônima):

1. **Janela A:** abra o painel em http://localhost/atendente e entre com o token. A fila deve estar vazia.
2. **Janela B:** abra http://localhost/chat e escreva algo como: *"Quero falar com um atendente, meu pedido 5 chegou com defeito"*.
3. O assistente transfere. No chat, o selo muda para **Atendente da loja**. Na janela A, a conversa aparece na fila, com o resumo.
4. **Janela A:** clique na conversa e responda. A resposta aparece na janela B.
5. **Janela B:** responda ao atendente. A mensagem aparece na janela A em tempo real.
6. **Janela A:** clique em **Devolver ao assistente**. A janela B mostra "O atendimento voltou para o assistente virtual" e o assistente volta a responder, já sabendo o que foi combinado.

## Configuração (`.env`)

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Sim | `agent` / `change-me` / `agent` | Credenciais do Postgres. O compose monta a `DATABASE_URL` a partir delas |
| `ANTHROPIC_API_KEY` | Sim | — | Chave da API da Anthropic |
| `ATTENDANT_TOKEN` | Sim, para o painel | — | Senha do painel. **Vazio = o painel recusa todos os acessos** |
| `SITE_ADDRESS` | Não | `:80` | `:80` para uso local, ou um domínio (ex.: `agent.exemplo.com`) para o Caddy ativar HTTPS automático |
| `ANTHROPIC_MODEL` | Não | `claude-sonnet-5-5` | Modelo usado pelo agente |
| `HANDOFF_TIMEOUT_SECONDS` | Não | `1800` | Segundos sem resposta do atendente até o assistente retomar a conversa |

`REDIS_URL` e `DATABASE_URL` são definidas pelo `docker-compose.yml`; você não precisa mexer nelas.

## Como funciona

```
Navegador ──► Caddy ──► /api/*  ──► FastAPI ──► Agente (LangGraph) ──► Claude
   │            │                      │              │
   │            └─ /, /chat,           │              ├─ tools ──► Postgres (produtos, pedidos, políticas)
   │               /atendente          │              └─ histórico ─► Postgres (checkpoint)
   │               (arquivos)          └─ handoff ───► Redis (quem responde + avisos ao atendente)
```

- **Uma conversa é um `conversation_id`**, guardado pelo navegador. Não há "encerramento": uma nova conversa é um id novo.
- **Quem responde** fica no Redis, na chave `handoff:{conversation_id}`. Sem chave, responde o agente. Com `human`, a API não chama o modelo: guarda a mensagem do cliente no histórico e avisa o atendente. A chave sempre tem validade, e é isso que devolve a conversa ao agente no timeout.
- **O agente nunca informa preço, estoque, prazo ou status de pedido sem consultar uma tool.** Promoções não são cumulativas e o desconto PIX de 5% não vale sobre preço promocional.
- **O prompt do sistema é estático** (`agent/prompt.py`). Data, hora e se a loja está aberta vêm da tool `get_store_status`. Isso é necessário porque o modelo assina o raciocínio contra o prompt, e mudá-lo entre turnos quebra o histórico.
- **Pedidos são privados:** a consulta exige o e-mail ou telefone do cliente e dá a mesma resposta para pedido inexistente e pedido de outra pessoa.

## API

Todas as rotas ficam sob `/api` (o Caddy só encaminha esse prefixo para a API).

**Cliente** (sem autenticação):

| Rota | Descrição |
|---|---|
| `GET /api/health` | `{"status": "ok"}` |
| `POST /api/chat` | Corpo `{"message": "...", "conversation_id": "..."}` (o id é opcional: sem ele, começa uma conversa). Resposta `{conversation_id, handled_by, reply}`. Com um humano atendendo, `reply` é `null` |
| `GET /api/chat/{id}?after=N` | Mensagens da conversa a partir do índice `N`, e quem está respondendo. O chat usa para receber as respostas do atendente |

**Atendente** (exigem o header `X-Attendant-Token: <ATTENDANT_TOKEN>`):

| Rota | Descrição |
|---|---|
| `GET /api/attendant/conversations` | Fila: conversas com humano, com o motivo da transferência |
| `GET /api/attendant/conversations/{id}` | Histórico e quem está respondendo |
| `POST /api/attendant/conversations/{id}/message` | Corpo `{"text": "..."}`. Responde ao cliente e assume a conversa se ela estava com o agente |
| `POST /api/attendant/conversations/{id}/release` | Devolve a conversa ao agente |
| `GET /api/attendant/events` | Fluxo de eventos em tempo real (SSE): `transfer`, `customer_message`, `released` |

## Testes manuais

Os scripts em `scripts/` exercitam o sistema de verdade e **fazem chamadas reais ao modelo** (custam alguns centavos). A stack precisa estar no ar.

| Script | O que faz | Como rodar |
|---|---|---|
| `scripts/try_agent.py` | Sete conversas de exemplo (produto, promoção, acessório, política, pedido, reclamação, tentativa de injeção de prompt) e as tools usadas em cada uma | `docker compose run --rm app python scripts/try_agent.py` (aceita nomes de cenários) |
| `scripts/try_handoff.py` | Fluxo da transferência pela API: evento, mensagem do atendente, devolução e timeout | `python scripts/try_handoff.py` (lê o `ATTENDANT_TOKEN` do `.env`) |
| `scripts/try_ui.py` | Abre o Chrome e percorre landing, chat e painel do atendente, com capturas de tela | `uv run --with playwright python scripts/try_ui.py [pasta-das-capturas]` (precisa do Google Chrome instalado) |

Os scripts de handoff e de interface deixam conversas em atendimento humano na fila; elas somem sozinhas quando o tempo de atendimento expira.

## Problemas comuns

| Sintoma | Causa provável e solução |
|---|---|
| `failed to connect to the docker API` | O Docker Desktop não está aberto. Abra-o e tente de novo |
| Erro de porta 80 ou 443 em uso | Outro programa usa a porta. Feche-o, ou mude as portas do serviço `caddy` no `docker-compose.yml` |
| O chat responde "Não consegui responder agora" (erro 502) | Veja `docker compose logs app`. Quase sempre é `ANTHROPIC_API_KEY` ausente ou inválida; depois de corrigir o `.env`, rode `docker compose up -d app` |
| O assistente diz que não encontra nenhum produto | Os dados não foram carregados: rode o passo 4 (`db.seed`) |
| Erro 503 no chat | O Redis ou o banco não está saudável. Veja `docker compose ps` |
| Painel: "Token inválido" | O token digitado difere do `ATTENDANT_TOKEN` do `.env`, ou a variável está vazia. Após mudar o `.env`, rode `docker compose up -d app` |
| Painel fica em "Reconectando…" | Verifique `docker compose ps` e `docker compose logs app` |
| Alterei o frontend e nada mudou | Recarregue sem cache (Ctrl+F5) |
| Alterei o Python e nada mudou | Faltou `docker compose up -d --build app` |
| Quero apagar todas as conversas | `docker compose down -v` apaga tudo (inclusive o banco); depois repita os passos 3 e 4 |

## Estrutura

```
agent/      prompt.py (system prompt), tools.py (tools), store.py (horário da loja), runner.py (grafo LangGraph)
db/         schema.sql, seed.py, connection.py, init/ (scripts de inicialização do Postgres)
handoff/    state.py (quem responde, com timeout), events.py (avisos em tempo real), api.py (rotas do atendente)
frontend/   index.html (landing), chat.html, atendente.html, style.css, common.js, chat.js, atendente.js
scripts/    testes manuais (try_agent.py, try_handoff.py, try_ui.py)
data/       CSVs da loja e manual de políticas (PDF)
main.py     app FastAPI
```

## Dados

`db/seed.py` esvazia e recarrega todas as tabelas, então pode ser executado quantas vezes for preciso:

| Tabela | Origem |
|---|---|
| `categories`, `products`, `promotions`, `customers`, `orders`, `order_items` | CSVs em `data/` |
| `policy_chunks` | `data/políticas_da_loja.pdf`, dividido por seção (25 trechos) |

O schema fica em `db/schema.sql` e é aplicado pelo próprio seed. As tabelas do histórico das conversas são criadas sozinhas pelo agente na primeira execução (o seed não as apaga).

## Tools do agente

Definidas em `agent/tools.py` (lista `TOOLS`):

| Tool | Uso |
|---|---|
| `search_products` | Busca no catálogo por texto, categoria, faixa de preço e estoque |
| `get_product` | Detalhes de um produto |
| `list_active_promotions` | Promoções ativas com preço final |
| `get_order_status` | Status e rastreio de um pedido; exige o e-mail ou telefone do cliente |
| `search_policies` | Busca no manual de políticas (frete, trocas, garantia, pagamento, horários) |
| `get_store_status` | Data e hora em Campo Grande e se a loja está aberta, com o horário de volta |
| `transfer_to_human` | Transfere a conversa para um atendente e avisa a equipe, com um resumo do caso |
