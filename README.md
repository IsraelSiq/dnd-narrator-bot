# D&D Narrator Bot

Bot de RPG D&D para Telegram, com criação guiada de personagens, regras de
atributos de D&D 5e, rolagens de dados, narrativa com IA e fallback offline.

## Executar

```powershell
cd dnd_bot
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python bot.py
```

Configure os tokens no `.env`. Consulte [`dnd_bot/README.md`](dnd_bot/README.md)
para as opções de Gemini, Groq, OpenRouter, Ollama, proxy e implantação.

## Testes

```powershell
python -m unittest discover -s tests
```