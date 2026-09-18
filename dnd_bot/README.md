# 🎲 D&D Narrator Bot

Narrador de RPG D&D para Telegram, com Gemini opcional e fallback offline.

---

## ⚙️ Setup — Passo a Passo

### 1. Criar o bot no Telegram

1. Abra o Telegram e procure por **@BotFather**
2. Envie `/newbot`
3. Escolha um nome (ex: `Narrador DnD`)
4. Escolha um username terminado em `bot` (ex: `NarradorDnD_bot`)
5. Copie o **token** que o BotFather te enviar

### 2. Pegar a API Key do Gemini (opcional)

1. Acesse: https://aistudio.google.com/app/apikey
2. Clique em **"Create API key"**
3. Copie a chave gerada

O bot também funciona sem Gemini: ele usa uma aventura, ficha, avaliação e
narração locais para que a partida não fique indisponível quando a API estiver
sem cota, com modelo incorreto ou fora do ar.

### 3. Configurar o projeto

```bash
# Entre na pasta do bot
cd dnd_bot

# Instale as dependências
pip install -r requirements.txt

# Configure as chaves (não coloque chaves reais no .env.example)
cp .env.example .env
# Edite o .env com seu editor favorito e coloque os tokens
```

Edite o `.env`:
```
TELEGRAM_TOKEN=seu_token_do_telegram
GEMINI_API_KEY=sua_chave_do_gemini
GEMINI_MODEL=gemini-2.0-flash
DATABASE_PATH=dnd.db
# Se a rede bloquear o Telegram, configure um proxy HTTP:
# TELEGRAM_PROXY=http://usuario:senha@host:porta
```

### 4. Rodar o bot

```bash
python bot.py
```

Pronto! O bot está online. Se `GEMINI_API_KEY` estiver vazio, o modo offline é
ativado automaticamente. ✅

Se o bot registrar `httpx.ConnectTimeout` ao acessar `api.telegram.org`, teste
outra rede (por exemplo, hotspot do celular) ou configure `TELEGRAM_PROXY`.
O processo agora tenta reconectar automaticamente a cada 15 segundos.

---

## 🎮 Como jogar

### Iniciando uma partida
1. Adicione o bot a um grupo do Telegram (ou converse diretamente)
2. Use `/nova_aventura` para o Gemini gerar um cenário
3. Cada jogador usa `/entrar` e responde às perguntas de nome, classe e raça

### Durante o jogo
- `/acao` + descrição da ação para interagir com a aventura
- `/cena` para gerar uma imagem do momento atual
- `/ficha` para ver sua ficha de personagem
- `/jogadores` para ver quem está na sessão

### Exemplos de uso
```
/entrar
# O bot pergunta o nome, mostra as classes e depois mostra as raças.
# Use /cancelar a qualquer momento durante a criação.

/acao Examino as paredes da masmorra em busca de passagens secretas
/acao Ataco o goblin com minha espada longa!
/acao Tento persuadir o guarda a nos deixar passar

/cena
```

---

## 📁 Estrutura do projeto

```
dnd_bot/
├── bot.py          # Bot Telegram + handlers dos comandos
├── narrator.py     # Integração com Gemini (narrativa + imagem)
├── database.py     # Supabase/Postgres (produção) ou SQLite (local)
├── .env            # Suas chaves (não commitar!)
├── .env.example    # Modelo do .env
├── requirements.txt
└── dnd.db          # Criado automaticamente ao rodar
```

### Banco de dados em produção

Por padrão, o bot usa SQLite em `DATABASE_PATH` (ideal para desenvolvimento
local). Para produção, defina `SUPABASE_DB_URL` com a URL de conexão Postgres
do Supabase; ela tem prioridade sobre `DATABASE_PATH` e não há fallback
silencioso para SQLite em caso de erro de conexão. Use sempre uma URL com
`sslmode=require` e mantenha a senha apenas no ambiente de execução.

O schema versionado está em
`supabase/migrations/20260917214300_initial_schema.sql`. A aplicação também
cria as tabelas na primeira conexão para facilitar instalações existentes.

---

## 💡 Dicas

- O bot funciona em **grupos** e em **conversa privada**
- Cada grupo/chat tem sua própria sessão independente
- Use `/nova_aventura` para resetar e começar uma história nova
- O contexto da aventura é atualizado a cada ação, mantendo consistência
- A geração de imagem requer que o Imagen 3 esteja disponível na sua conta Gemini

## 🛡️ Confiabilidade e escolha do provedor

Gemini continua sendo uma boa primeira opção hospedada para este projeto,
mas o SDK legado `google-generativeai` pode ser incompatível com Python 3.14.
Como alternativa, o bot aceita qualquer API compatível com o formato OpenAI.
Para começar, recomendo Groq pela baixa latência; OpenRouter oferece mais
modelos; Ollama roda localmente sem cota, mas exige recursos da máquina.
Entretanto, o código não deve depender exclusivamente dele: nomes de modelos,
limites de cota, JSON inválido e indisponibilidade são falhas normais de uma API.

Por isso, o narrador captura erros e usa conteúdo offline. Para uso gratuito
com mais previsibilidade, a alternativa mais confiável é rodar um modelo local
via Ollama (por exemplo, uma variante de Llama ou Qwen), mas isso exige memória
e CPU/GPU na máquina. Groq e modelos gratuitos do OpenRouter podem ser opções
rápidas para testes, porém suas cotas e modelos disponíveis mudam com
frequência. Eu recomendaria: Gemini como provedor principal, fallback offline
sempre habilitado e Ollama quando houver necessidade de independência de cota.

Exemplo com Groq:

```env
AI_API_KEY=sua_chave_groq
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
```

## ✅ Testes

Na raiz do projeto:

```bash
python -m unittest discover -s tests
```

---

## 🚀 Rodando em produção (opcional)

Para manter o bot sempre online, você pode usar:

**Screen (simples):**
```bash
screen -S dndbot
python bot.py
# Ctrl+A+D para desanexar
```

**Systemd (mais robusto):**
```ini
# /etc/systemd/system/dndbot.service
[Unit]
Description=D&D Narrator Bot

[Service]
WorkingDirectory=/caminho/para/dnd_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```
