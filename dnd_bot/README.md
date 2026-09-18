# 🎲 D&D Narrator Bot

Narrador de RPG D&D para Telegram, com criação guiada de personagens, continuidade persistente e fallback offline.

## 🎮 Fluxo para jogar

1. Use `/start` para começar a criação do personagem.
2. Responda nome, classe, raça e detalhes do passado ou personalidade.
3. Use `/iniciar_historia` para gerar a ficha e abrir a primeira cena.
4. Durante a aventura, use `/acao` seguido da descrição do que seu personagem faz.

O bot tenta os provedores nesta ordem: Gemini, provedor OpenAI-compatible configurado em `AI_*`, Bastião configurado em `BASTIAO_*` e, por fim, um narrador offline determinístico. A sessão não deve parar quando uma API atingir quota, retornar JSON inválido ou ficar indisponível.

Use `/cancelar` para interromper a criação e `/entrar` para recomeçá-la. `/nova_aventura` inicia uma nova criação pelo fluxo de `/start`.

### Outros comandos

- `/ficha` — ver a ficha do personagem
- `/jogadores` — listar os jogadores da sessão
- `/ajuda` — mostrar o fluxo novamente

## 🛡️ Estratégia de continuidade

A IA é tratada como acelerador de narrativa, não como fonte única de estado. O contexto da sessão e o histórico de ações ficam no banco; quando os provedores falham, o fallback local ainda produz ficha, avaliação, narração, sugestões e cena textual.

Cada provedor entra em cooldown após uma falha para evitar tentativas repetitivas e loops. O Bastião deve expor uma API compatível com OpenAI, como Ollama ou LM Studio.

### Bastião em máquina local

```env
BASTIAO_API_KEY=ollama
BASTIAO_BASE_URL=http://127.0.0.1:11434/v1
BASTIAO_MODEL=qwen2.5:7b
```

Se o bot estiver no Railway e o Bastião estiver em casa, `127.0.0.1` não aponta para o seu PC. Use uma VPN ou túnel seguro, como Tailscale ou Cloudflare Tunnel, e nunca exponha a porta sem autenticação.

## ⚙️ Configuração

```bash
cd dnd_bot
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

Configure `TELEGRAM_TOKEN`. `GEMINI_API_KEY`, `AI_*` e `BASTIAO_*` são opcionais: sem eles, o bot utiliza o fallback offline.

## ✅ Testes

Na raiz do projeto:

```bash
python -m unittest discover -s tests
```
