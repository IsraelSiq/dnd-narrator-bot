"""Telegram bot for the D&D narrator."""
import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from telegram import BotCommand, ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from database import Database
from dice import ATTR_EMOJI, detectar_atributo, escapa, formatar_resultado_dado, realizar_teste
from narrator import Narrator

load_dotenv()
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
db = Database(path=os.getenv("DATABASE_PATH", "dnd.db"), db_url=os.getenv("SUPABASE_DB_URL"))
narrator = Narrator(os.getenv("GEMINI_API_KEY"))

ENTRAR_NOME, ENTRAR_CLASSE, ENTRAR_RACA, ENTRAR_DETALHES, AGUARDANDO_INICIO = range(5)
CLASSES = {
    "Guerreiro": "FOR ou DES, CON — mestre de armas e armaduras",
    "Bárbaro": "FOR, CON — combatente resistente e fúria",
    "Ladino": "DES, INT ou CAR — perícias, furtividade e precisão",
    "Mago": "INT, DES — conjurador arcano e conhecimento",
    "Clérigo": "SAB, CON — magia divina, cura e proteção",
    "Ranger": "DES, SAB, CON — exploração e combate à distância",
}
RACAS = {
    "Humano": "FOR, DES, CON, INT, SAB e CAR +1 — versátil",
    "Elfo": "DES +2, INT +1 — ágil e ligado à magia",
    "Anão": "CON +2, SAB +1 — resistente e determinado",
    "Halfling": "DES +2, CAR +1 — ágil e sortudo",
    "Tiefling": "INT +1, CAR +2 — magia e presença marcante",
    "Meio-Orc": "FOR +2, CON +1 — poderoso e resistente",
}


def estado_key(update):
    return update.effective_chat.id, update.effective_user.id


def estados(ctx):
    return ctx.application.bot_data.setdefault("entradas", {})


def teclado(opcoes):
    return ReplyKeyboardMarkup(
        [[f"{nome} — {resumo}"] for nome, resumo in opcoes.items()],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Start now opens character creation; the story starts only at /iniciar_historia."""
    await update.message.reply_text(
        "⚔️ *Bem-vindo ao Narrador D&D!*\n\n"
        "Vamos criar seu personagem antes de começar a história.\n"
        "Ao terminar, use `/iniciar_historia` para finalizar a ficha e iniciar a aventura.\n"
        "Use `/cancelar` para interromper a criação.", parse_mode="Markdown"
    )
    await iniciar_criacao(update, ctx)


async def cmd_ajuda(update, ctx):
    await update.message.reply_text(
        "🎲 Fluxo da partida:\n"
        "1. `/start` — inicia a criação do personagem\n"
        "2. `/iniciar_historia` — finaliza a ficha e começa a história\n"
        "3. `/acao` — interage com a aventura\n\n"
        "Também disponíveis: `/ficha`, `/jogadores`, `/rolar`, `/cena`, `/sugerir` e `/cancelar`."
    )


async def iniciar_criacao(update, ctx):
    estados(ctx)[estado_key(update)] = {"etapa": "nome"}
    await update.message.reply_text(
        "🧙 Qual será o nome do personagem?\n"
        "Responda com o nome ou use /cancelar.", reply_markup=ForceReply(selective=True)
    )
    return ENTRAR_NOME


async def cmd_entrar(update, ctx):
    estados(ctx).pop(estado_key(update), None)
    return await iniciar_criacao(update, ctx)


async def receber_nome(update, ctx):
    nome = update.message.text.strip()
    if not nome or len(nome) > 40:
        await update.message.reply_text("⚠️ Envie um nome entre 1 e 40 caracteres.")
        return ENTRAR_NOME
    estados(ctx)[estado_key(update)] = {"etapa": "classe", "personagem": {"nome": nome}}
    await update.message.reply_text(
        "2️⃣ Escolha sua classe:\n\n" + "\n".join(f"• {n}: {d}" for n, d in CLASSES.items()),
        reply_markup=teclado(CLASSES),
    )
    return ENTRAR_CLASSE


async def receber_classe(update, ctx):
    escolha = update.message.text.split(" — ", 1)[0]
    if escolha not in CLASSES:
        await update.message.reply_text("⚠️ Escolha uma das classes exibidas.")
        return ENTRAR_CLASSE
    estado = estados(ctx).get(estado_key(update))
    if not estado:
        return await cmd_entrar(update, ctx)
    estado["personagem"]["classe"] = escolha
    estado["etapa"] = "raca"
    await update.message.reply_text(
        "3️⃣ Escolha sua raça:\n\n" + "\n".join(f"• {n}: {d}" for n, d in RACAS.items()),
        reply_markup=teclado(RACAS),
    )
    return ENTRAR_RACA


async def receber_raca(update, ctx):
    escolha = update.message.text.split(" — ", 1)[0]
    if escolha not in RACAS:
        await update.message.reply_text("⚠️ Escolha uma das raças exibidas.")
        return ENTRAR_RACA
    estado = estados(ctx).get(estado_key(update))
    if not estado:
        await update.message.reply_text("⚠️ A criação expirou. Use /start novamente.")
        return
    estado["personagem"]["raca"] = escolha
    estado["etapa"] = "detalhes"
    await update.message.reply_text(
        "4️⃣ Descreva detalhes opcionais: arquétipo, manias, medos, objetivo ou histórico.\n"
        "Escreva `nenhum` se prefere que o narrador decida.", reply_markup=ForceReply(selective=True)
    )
    return ENTRAR_DETALHES


async def receber_detalhes(update, ctx):
    estado = estados(ctx).get(estado_key(update))
    if not estado or "personagem" not in estado:
        await update.message.reply_text("⚠️ A criação expirou. Use /start novamente.")
        return
    detalhes = update.message.text.strip()
    estado["personagem"]["detalhes"] = "" if detalhes.lower() in {"nenhum", "nenhuma", "n/a", "nao", "não"} else detalhes
    estado["etapa"] = "aguardando_inicio"
    await update.message.reply_text(
        "✅ Dados do personagem recebidos!\n\n"
        "Quando estiver pronto, use `/iniciar_historia`. Esse comando vai gerar sua ficha, "
        "salvá-la e começar a aventura.\n\nUse /cancelar para descartar a criação.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AGUARDANDO_INICIO


async def cmd_iniciar_historia(update, ctx):
    chave = estado_key(update)
    estado = estados(ctx).get(chave)
    if not estado or estado.get("etapa") != "aguardando_inicio":
        await update.message.reply_text("⚠️ Termine a criação do personagem primeiro usando /start.")
        return
    p = estado["personagem"]
    await update.message.reply_text("🧙 Finalizando sua ficha e preparando a história...")
    try:
        ficha = await narrator.criar_personagem(p["nome"], p["classe"], p["raca"], p["detalhes"])
        if not isinstance(ficha, dict) or not ficha.get("atributos") or not ficha.get("historia"):
            raise ValueError("ficha incompleta")
        intro = await narrator.iniciar_aventura(update.effective_chat.id)
        db.criar_sessao(update.effective_chat.id, intro["contexto"])
        db.salvar_personagem(update.effective_user.id, update.effective_chat.id, p["nome"], p["classe"], p["raca"], ficha["atributos"], ficha["historia"])
    except Exception:
        log.exception("Falha ao iniciar história")
        await update.message.reply_text("⚠️ Não consegui iniciar a história agora. Seus dados continuam preservados; tente /iniciar_historia novamente.")
        return
    estados(ctx).pop(chave, None)
    await update.message.reply_text(
        f"✅ *{escapa(p['nome'])} entrou na aventura!*\n\n"
        f"📊 *Atributos:*\n{formatar_atributos(ficha['atributos'])}\n\n"
        f"📖 *História:* _{escapa(ficha['historia'])}_\n\n"
        f"📚 *{escapa(intro['titulo'])}*\n\n{escapa(intro['narrativa'])}", parse_mode="MarkdownV2"
    )


async def cancelar_entrada(update, ctx):
    estados(ctx).pop(estado_key(update), None)
    await update.message.reply_text("❌ Criação cancelada.", reply_markup=ReplyKeyboardRemove())


async def processar_entrada(update, ctx):
    etapa = estados(ctx).get(estado_key(update), {}).get("etapa")
    if etapa == "nome": return await receber_nome(update, ctx)
    if etapa == "classe": return await receber_classe(update, ctx)
    if etapa == "raca": return await receber_raca(update, ctx)
    if etapa == "detalhes": return await receber_detalhes(update, ctx)
    if etapa == "aguardando_inicio":
        await update.message.reply_text("Use `/iniciar_historia` para finalizar a ficha e começar.", parse_mode="Markdown")


async def cmd_nova_aventura(update, ctx):
    await update.message.reply_text("Para iniciar uma nova partida, use /start e crie um novo personagem.")


async def cmd_ficha(update, ctx):
    p = db.obter_personagem(update.effective_user.id, update.effective_chat.id)
    if not p:
        await update.message.reply_text("❌ Você ainda não tem personagem. Use /start.")
        return
    await update.message.reply_text(f"📜 Ficha de {p['nome']} — {p['classe']} {p['raca']}\n\n{formatar_atributos(p['atributos'])}\n\n{p['historia']}")


async def cmd_jogadores(update, ctx):
    jogadores = db.listar_jogadores(update.effective_chat.id)
    await update.message.reply_text("👥 Nenhum jogador ainda." if not jogadores else "👥 Jogadores:\n" + "\n".join(f"• {j['nome']} — {j['classe']} {j['raca']}" for j in jogadores))


async def cmd_acao(update, ctx):
    sessao = db.obter_sessao(update.effective_chat.id)
    p = db.obter_personagem(update.effective_user.id, update.effective_chat.id)
    if not sessao or not p:
        await update.message.reply_text("❌ Inicie a história com /start e /iniciar_historia.")
        return
    acao = " ".join(ctx.args)
    if not acao:
        await update.message.reply_text("Use /acao seguido da descrição da ação.")
        return
    resultado = await narrator.narrar_acao_com_dado(sessao, p, db.listar_jogadores(update.effective_chat.id), acao, None)
    db.atualizar_contexto(update.effective_chat.id, resultado.get("novo_contexto", sessao["contexto"]))
    db.registrar_acao(update.effective_user.id, update.effective_chat.id, acao, resultado["narrativa"])
    await update.message.reply_text(f"📖 {resultado['narrativa']}")


def formatar_atributos(atributos):
    from dice import modificador
    return "\n".join(f"{a}: {v} ({modificador(v):+d})" for a, v in atributos.items())


async def configurar_comandos(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Criar personagem"), BotCommand("iniciar_historia", "Finalizar ficha e iniciar história"),
        BotCommand("ajuda", "Mostrar ajuda"), BotCommand("entrar", "Recomeçar personagem"),
        BotCommand("cancelar", "Cancelar criação"), BotCommand("acao", "Fazer uma ação"),
        BotCommand("ficha", "Ver ficha"), BotCommand("jogadores", "Listar jogadores"),
    ])


def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN não encontrado no .env!")
    proxy = os.getenv("TELEGRAM_PROXY") or None
    request = HTTPXRequest(connection_pool_size=8, connect_timeout=30, read_timeout=60, write_timeout=30, pool_timeout=30, proxy=proxy)
    updates_request = HTTPXRequest(connection_pool_size=2, connect_timeout=30, read_timeout=60, write_timeout=30, pool_timeout=30, proxy=proxy)
    def build_app():
        app = ApplicationBuilder().token(token).request(request).get_updates_request(updates_request).post_init(configurar_comandos).build()
        for command, handler in [("start", cmd_start), ("ajuda", cmd_ajuda), ("entrar", cmd_entrar), ("iniciar_historia", cmd_iniciar_historia), ("cancelar", cancelar_entrada), ("nova_aventura", cmd_nova_aventura), ("acao", cmd_acao), ("ficha", cmd_ficha), ("jogadores", cmd_jogadores)]:
            app.add_handler(CommandHandler(command, handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_entrada))
        return app
    while True:
        try:
            build_app().run_polling(timeout=30, bootstrap_retries=-1, close_loop=False)
            break
        except (NetworkError, TimedOut) as exc:
            log.error("Falha de rede: %s; tentando novamente em 15 segundos", exc)
            time.sleep(15)


if __name__ == "__main__":
    main()
