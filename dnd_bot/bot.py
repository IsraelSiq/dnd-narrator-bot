"""
🎲 D&D Narrator Bot — Telegram
Narrador de RPG com IA (Gemini) + fichas SQLite + sistema de dados visível
"""

import logging
import os
import asyncio
import time
from telegram import BotCommand, ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, filters
)
from dotenv import load_dotenv

from database import Database
from narrator import Narrator
from dice import (
    realizar_teste, detectar_atributo,
    formatar_resultado_dado, escapa, ATTR_EMOJI
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

db       = Database(
    path=os.getenv("DATABASE_PATH", "dnd.db"),
    db_url=os.getenv("SUPABASE_DB_URL"),
)
narrator = Narrator(os.getenv("GEMINI_API_KEY"))


# ─── /start & /ajuda ──────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚔️ *Bem\\-vindo ao Narrador D&D\\!*\n\n"
        "🗺️ `/nova_aventura` — Inicia uma nova sessão\n"
        "🧙 `/entrar` — Cria seu personagem passo a passo\n"
        "⚡ `/acao` \\+ descrição — Faz algo na aventura\n"
        "🎲 `/rolar` \\[atributo\\] — Rola dado livremente\n"
        "💡 `/sugerir` — Sugestões de ação para seu personagem\n"
        "🖼️ `/cena` — Gera imagem da cena atual\n"
        "📜 `/ficha` — Sua ficha de personagem\n"
        "👥 `/jogadores` — Quem está na sessão\n"
        "❓ `/ajuda` — Este menu\n\n"
        "Use `/nova_aventura` para começar\\!",
        parse_mode="MarkdownV2"
    )

async def cmd_ajuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


# ─── /nova_aventura ───────────────────────────────────────────────────────────
async def cmd_nova_aventura(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("🎲 Gerando sua aventura... aguarde!")
    intro = await narrator.iniciar_aventura(chat_id)
    db.criar_sessao(chat_id, intro["contexto"])
    await update.message.reply_text(
        f"📖 *{escapa(intro['titulo'])}*\n\n"
        f"{escapa(intro['narrativa'])}\n\n"
        f"_Use /entrar para criar seu personagem passo a passo\\!_",
        parse_mode="MarkdownV2"
    )


# ─── /entrar — criação guiada de personagem ───────────────────────────────────
ENTRAR_NOME, ENTRAR_CLASSE, ENTRAR_RACA, ENTRAR_DETALHES = range(4)

CLASSES = {
    "Guerreiro": "atributos recomendados: FOR ou DES, CON — mestre de armas e armaduras",
    "Bárbaro": "atributos recomendados: FOR, CON — combatente resistente e fúria",
    "Ladino": "atributos recomendados: DES, INT ou CAR — perícias, furtividade e precisão",
    "Mago": "atributos recomendados: INT, DES — conjurador arcano e conhecimento",
    "Clérigo": "atributos recomendados: SAB, CON — magia divina, cura e proteção",
    "Ranger": "atributos recomendados: DES, SAB, CON — exploração e combate à distância",
}

RACAS = {
    "Humano": "FOR, DES, CON, INT, SAB e CAR +1 — versátil",
    "Elfo": "DES +2, INT +1 — ágil, atento e ligado à magia",
    "Anão": "CON +2, SAB +1 — resistente e determinado",
    "Halfling": "DES +2, CAR +1 — ágil e sortudo",
    "Tiefling": "INT +1, CAR +2 — magia e presença marcante",
    "Meio-Orc": "FOR +2, CON +1 — poderoso e resistente",
}

RACA_BONUS = {
    "Humano": {"Força": 1, "Destreza": 1, "Constituição": 1, "Inteligência": 1, "Sabedoria": 1, "Carisma": 1},
    "Elfo": {"Destreza": 2, "Inteligência": 1},
    "Anão": {"Constituição": 2, "Sabedoria": 1},
    "Halfling": {"Destreza": 2, "Carisma": 1},
    "Tiefling": {"Inteligência": 1, "Carisma": 2},
    "Meio-Orc": {"Força": 2, "Constituição": 1},
}

def estado_key(update: Update) -> tuple[int, int]:
    return update.effective_chat.id, update.effective_user.id


def estados_entrada(ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    return ctx.application.bot_data.setdefault("entradas", {})


def opcoes_teclado(opcoes: dict) -> ReplyKeyboardMarkup:
    linhas = []
    linha = []
    for opcao, resumo in opcoes.items():
        linha.append(f"{opcao} — {resumo}")
        if len(linha) == 1:
            linhas.append(linha)
            linha = []
    if linha:
        linhas.append(linha)
    return ReplyKeyboardMarkup(linhas, one_time_keyboard=True, resize_keyboard=True)


async def cmd_entrar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    sessao = db.obter_sessao(chat_id)
    if not sessao:
        await update.message.reply_text(
            "❌ Nenhuma aventura ativa\\! Use `/nova_aventura` primeiro\\.",
            parse_mode="MarkdownV2"
        )
        return ConversationHandler.END

    estados_entrada(ctx).pop(estado_key(update), None)
    estados_entrada(ctx)[estado_key(update)] = {"etapa": "nome"}
    await update.message.reply_text("🧙 Criando seu personagem...")
    await update.message.reply_text(
        "1️⃣ Qual será o nome do personagem?\n"
        "Responda diretamente a esta mensagem com o nome ou use /cancelar para sair.",
        reply_markup=ForceReply(selective=True),
    )
    return ENTRAR_NOME


async def receber_nome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    nome = update.message.text.strip()
    if not nome or len(nome) > 40:
        await update.message.reply_text("⚠️ Envie um nome entre 1 e 40 caracteres.")
        return ENTRAR_NOME

    estado = estados_entrada(ctx)[estado_key(update)]
    estado["personagem"] = {"nome": nome}
    estado["etapa"] = "classe"
    await update.message.reply_text(
        "2️⃣ Escolha sua classe.\n"
        "As classes não alteram atributos diretamente; elas definem recursos e "
        "atributos recomendados.\n\n" +
        "\n".join(f"• {nome}: {resumo}" for nome, resumo in CLASSES.items()),
        reply_markup=opcoes_teclado(CLASSES),
    )
    return ENTRAR_CLASSE


async def receber_classe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    escolha = update.message.text.split(" — ", 1)[0]
    if escolha not in CLASSES:
        await update.message.reply_text(
            "⚠️ Escolha uma das classes exibidas usando os botões."
        )
        return ENTRAR_CLASSE

    estado = estados_entrada(ctx).get(estado_key(update))
    if not estado or "personagem" not in estado:
        await update.message.reply_text("⚠️ A criação expirou. Use /entrar novamente.")
        return
    estado["personagem"]["classe"] = escolha
    estado["etapa"] = "raca"
    await update.message.reply_text(
        "3️⃣ Escolha sua raça.\n"
        "Os bônus abaixo são os bônus de atributo padrão de D&D 5e; não há "
        "penalizadores raciais nesta seleção.\n\n" +
        "\n".join(f"• {nome}: {resumo}" for nome, resumo in RACAS.items()),
        reply_markup=opcoes_teclado(RACAS),
    )
    return ENTRAR_RACA


async def receber_raca(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    escolha = update.message.text.split(" — ", 1)[0]
    if escolha not in RACAS:
        await update.message.reply_text(
            "⚠️ Escolha uma das raças exibidas usando os botões."
        )
        return ENTRAR_RACA

    estado = estados_entrada(ctx).get(estado_key(update))
    if not estado or "personagem" not in estado:
        await update.message.reply_text("⚠️ A criação expirou. Use /entrar novamente.")
        return
    personagem = estado["personagem"]
    nome = personagem["nome"]
    classe = personagem["classe"]
    raca = escolha
    personagem["raca"] = escolha
    estado["etapa"] = "detalhes"
    await update.message.reply_text(
        "4️⃣ Agora descreva detalhes do personagem (opcional): arquétipo, manias, "
        "medos, objetivo, profissão anterior ou qualquer detalhe histórico.\n\n"
        "Responda diretamente a esta mensagem. Escreva `nenhum` se prefere "
        "que o narrador decida.",
        reply_markup=ForceReply(selective=True)
    )
    return ENTRAR_DETALHES


async def receber_detalhes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chave = estado_key(update)
    estado = estados_entrada(ctx).get(chave)
    if not estado or "personagem" not in estado:
        await update.message.reply_text("⚠️ A criação expirou. Use /entrar novamente.")
        return
    personagem = estado["personagem"]
    nome = personagem["nome"]
    classe = personagem["classe"]
    raca = personagem["raca"]
    detalhes = update.message.text.strip()
    if detalhes.lower() in {"nenhum", "nenhuma", "n/a", "nao", "não"}:
        detalhes = ""

    await update.message.reply_text("🧙 Criando sua ficha...", reply_markup=ReplyKeyboardRemove())
    try:
        ficha = await narrator.criar_personagem(nome, classe, raca, detalhes)
        if not isinstance(ficha, dict) or not ficha.get("atributos") or not ficha.get("historia"):
            raise ValueError("A IA retornou uma ficha incompleta.")
        db.salvar_personagem(
            user_id=update.effective_user.id, chat_id=update.effective_chat.id,
            nome=nome, classe=classe, raca=raca,
            atributos=ficha["atributos"], historia=ficha["historia"]
        )
    except Exception:
        log.exception("Falha ao finalizar criação de personagem")
        await update.message.reply_text(
            "⚠️ Não consegui finalizar a ficha agora. Seus dados foram preservados; "
            "envie os detalhes novamente ou use /cancelar."
        )
        return ENTRAR_DETALHES

    estados_entrada(ctx).pop(chave, None)

    await update.message.reply_text(
        f"✅ *{escapa(nome)} entrou na aventura\\!*\n\n"
        f"📛 *Classe:* {escapa(classe)} \\| *Raça:* {escapa(raca)}\n\n"
        f"📊 *Atributos:*\n{formatar_atributos(ficha['atributos'])}\n\n"
        f"📖 *História:* _{escapa(ficha['historia'])}_",
        parse_mode="MarkdownV2"
    )
    return ConversationHandler.END


async def cancelar_entrada(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    estados_entrada(ctx).pop(estado_key(update), None)
    await update.message.reply_text(
        "❌ Criação cancelada.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def processar_entrada(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Processa respostas usando estado explícito, inclusive em grupos."""
    estado = estados_entrada(ctx).get(estado_key(update))
    etapa = estado.get("etapa") if estado else None
    if etapa == "nome":
        return await receber_nome(update, ctx)
    if etapa == "classe":
        return await receber_classe(update, ctx)
    if etapa == "raca":
        return await receber_raca(update, ctx)
    if etapa == "detalhes":
        return await receber_detalhes(update, ctx)
    if update.message:
        log.info("Mensagem sem fluxo ativo: chat=%s user=%s", *estado_key(update))


async def configurar_comandos(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Abrir o menu inicial"),
        BotCommand("ajuda", "Mostrar ajuda"),
        BotCommand("nova_aventura", "Iniciar uma aventura"),
        BotCommand("entrar", "Criar personagem passo a passo"),
        BotCommand("cancelar", "Cancelar criação de personagem"),
        BotCommand("acao", "Fazer uma ação"),
        BotCommand("rolar", "Rolar dados"),
        BotCommand("sugerir", "Sugerir ações"),
        BotCommand("cena", "Ver a cena atual"),
        BotCommand("ficha", "Ver sua ficha"),
        BotCommand("jogadores", "Listar jogadores"),
    ])


# ─── /acao ────────────────────────────────────────────────────────────────────
async def cmd_acao(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user

    sessao = db.obter_sessao(chat_id)
    if not sessao:
        await update.message.reply_text(
            "❌ Nenhuma aventura ativa\\! Use `/nova_aventura`\\.",
            parse_mode="MarkdownV2"
        )
        return

    personagem = db.obter_personagem(user.id, chat_id)
    if not personagem:
        await update.message.reply_text(
            "❌ Use `/entrar Nome Classe Raça` primeiro\\.",
            parse_mode="MarkdownV2"
        )
        return

    acao = " ".join(ctx.args) if ctx.args else None
    if not acao:
        await update.message.reply_text(
            "⚠️ Descreva sua ação\\!\n"
            "Ex: `/acao Tento roubar o cálice de ouro sem ninguém ver`",
            parse_mode="MarkdownV2"
        )
        return

    jogadores = db.listar_jogadores(chat_id)

    # Passo 1: Gemini avalia se precisa de teste e qual CD
    msg_proc = await update.message.reply_text("🧠 O Mestre avalia sua ação...")
    avaliacao = await narrator.avaliar_acao(sessao, acao)

    teste = None
    if avaliacao.get("precisa_teste"):
        # Detecta atributo: primeiro pelo texto da ação, depois pelo que o Gemini disse
        atributo = detectar_atributo(acao) or avaliacao.get("atributo", "Destreza")
        cd       = avaliacao.get("cd", 12)

        # Passo 2: Rola o dado e mostra visualmente
        teste = realizar_teste(
            atributos=personagem["atributos"],
            atributo=atributo,
            dificuldade=cd
        )

        await ctx.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_proc.message_id,
            text=formatar_resultado_dado(teste, personagem["nome"]),
            parse_mode="MarkdownV2"
        )
        # Pequena pausa dramática antes de narrar
        await asyncio.sleep(1.5)
        await update.message.reply_text("📖 O narrador descreve o que acontece...")
    else:
        await ctx.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_proc.message_id,
            text="📖 Ação simples — o narrador descreve..."
        )

    # Passo 3: Gemini narra sabendo o resultado real do dado
    resultado = await narrator.narrar_acao_com_dado(
        sessao=sessao,
        personagem=personagem,
        jogadores=jogadores,
        acao=acao,
        teste=teste
    )

    novo_contexto = resultado.get("novo_contexto", "").strip()
    if not novo_contexto or novo_contexto == sessao["contexto"]:
        novo_contexto = (
            f"{sessao['contexto']} Última ação de {personagem['nome']}: {acao}. "
            f"Resultado: {resultado['narrativa']}"
        )
    db.atualizar_contexto(chat_id, novo_contexto)
    db.registrar_acao(user.id, chat_id, acao, resultado["narrativa"])

    await update.message.reply_text(
        f"🗡️ *{escapa(personagem['nome'])} age\\!*\n\n"
        f"{escapa(resultado['narrativa'])}\n\n"
        f"💡 *O que fazer agora?*\n{formatar_sugestoes(resultado['sugestoes'])}",
        parse_mode="MarkdownV2"
    )


# ─── /rolar ───────────────────────────────────────────────────────────────────
async def cmd_rolar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Rola dado livremente.
    Uso: /rolar           → d20 puro
         /rolar Destreza  → d20 + mod de Destreza
         /rolar Força 15  → d20 + mod de Força vs CD 15
    """
    chat_id = update.effective_chat.id
    user    = update.effective_user

    personagem = db.obter_personagem(user.id, chat_id)
    args       = ctx.args

    # Sem personagem: rola d20 puro
    if not personagem:
        import random
        resultado = random.randint(1, 20)
        emoji = "🌟" if resultado == 20 else ("💀" if resultado == 1 else "🎲")
        await update.message.reply_text(
            f"🎲 *Rolagem livre de d20*\n\n{emoji} Resultado: *{resultado}*",
            parse_mode="MarkdownV2"
        )
        return

    # Detecta atributo e CD dos argumentos
    atributo = None
    cd       = 10  # CD padrão

    if args:
        # Primeiro arg pode ser atributo
        arg0 = args[0].capitalize()
        atributos_validos = list(personagem["atributos"].keys())
        # Busca parcial (ex: "For" → "Força")
        for a in atributos_validos:
            if a.lower().startswith(arg0.lower()):
                atributo = a
                break
        # Segundo arg pode ser CD
        if len(args) >= 2:
            try:
                cd = int(args[1])
            except ValueError:
                pass

    if not atributo:
        # Sem atributo especificado: rola d20 puro
        import random
        resultado = random.randint(1, 20)
        emoji = "🌟" if resultado == 20 else ("💀" if resultado == 1 else "🎲")
        await update.message.reply_text(
            f"🎲 *{escapa(personagem['nome'])} rola d20*\n\n{emoji} Resultado: *{resultado}*",
            parse_mode="MarkdownV2"
        )
        return

    teste = realizar_teste(
        atributos=personagem["atributos"],
        atributo=atributo,
        dificuldade=cd
    )
    await update.message.reply_text(
        formatar_resultado_dado(teste, personagem["nome"]),
        parse_mode="MarkdownV2"
    )


# ─── /sugerir ─────────────────────────────────────────────────────────────────
async def cmd_sugerir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sugere ações personalizadas para o personagem com base no contexto."""
    chat_id = update.effective_chat.id
    user    = update.effective_user

    sessao = db.obter_sessao(chat_id)
    if not sessao:
        await update.message.reply_text("❌ Nenhuma aventura ativa\\!", parse_mode="MarkdownV2")
        return

    personagem = db.obter_personagem(user.id, chat_id)
    if not personagem:
        await update.message.reply_text(
            "❌ Use `/entrar Nome Classe Raça` primeiro\\.", parse_mode="MarkdownV2"
        )
        return

    await update.message.reply_text("💡 O Mestre pensa em opções para você...")
    dados = await narrator.sugerir_acoes(sessao, personagem)

    RISCO_EMOJI = {"baixo": "🟢", "médio": "🟡", "alto": "🔴"}
    linhas = []
    for i, s in enumerate(dados.get("sugestoes", []), 1):
        attr_e = ATTR_EMOJI.get(s.get("atributo", ""), "🎲")
        risco  = s.get("risco", "médio")
        r_e    = RISCO_EMOJI.get(risco, "🟡")
        cd     = s.get("cd", "?")
        acao   = escapa(s.get("acao", ""))
        attr   = escapa(s.get("atributo", ""))
        linhas.append(
            f"{i}\\. {r_e} _{acao}_\n"
            f"   {attr_e} *{attr}* \\| CD {cd} \\| Risco: {escapa(risco)}"
        )

    await update.message.reply_text(
        f"💡 *Sugestões para {escapa(personagem['nome'])}:*\n\n" + "\n\n".join(linhas) +
        "\n\n_Use `/acao` \\+ descrição para agir\\!_",
        parse_mode="MarkdownV2"
    )


# ─── /cena ────────────────────────────────────────────────────────────────────
async def cmd_cena(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessao  = db.obter_sessao(chat_id)

    if not sessao:
        await update.message.reply_text("❌ Nenhuma aventura ativa\\!", parse_mode="MarkdownV2")
        return

    await update.message.reply_text("🖼️ Gerando imagem da cena atual...")
    resultado = await narrator.gerar_cena(sessao)

    if resultado.get("imagem_bytes"):
        await update.message.reply_photo(
            photo=resultado["imagem_bytes"],
            caption=f"🏰 _{escapa(resultado['descricao'])}_",
            parse_mode="MarkdownV2"
        )
    else:
        await update.message.reply_text(
            f"🏰 *Cena atual:*\n\n_{escapa(resultado['descricao'])}_",
            parse_mode="MarkdownV2"
        )


# ─── /ficha ───────────────────────────────────────────────────────────────────
async def cmd_ficha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id    = update.effective_chat.id
    user       = update.effective_user
    personagem = db.obter_personagem(user.id, chat_id)

    if not personagem:
        await update.message.reply_text(
            "❌ Você não tem personagem\\! Use `/entrar Nome Classe Raça`\\.",
            parse_mode="MarkdownV2"
        )
        return

    await update.message.reply_text(
        f"📜 *Ficha de {escapa(personagem['nome'])}*\n\n"
        f"🧙 *Classe:* {escapa(personagem['classe'])}\n"
        f"🌍 *Raça:* {escapa(personagem['raca'])}\n\n"
        f"📊 *Atributos:*\n{formatar_atributos(personagem['atributos'])}\n\n"
        f"📖 *História:* _{escapa(personagem['historia'])}_",
        parse_mode="MarkdownV2"
    )


# ─── /jogadores ───────────────────────────────────────────────────────────────
async def cmd_jogadores(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id  = update.effective_chat.id
    jogadores = db.listar_jogadores(chat_id)

    if not jogadores:
        await update.message.reply_text("👥 Nenhum jogador ainda\\.", parse_mode="MarkdownV2")
        return

    lista = "\n".join(
        f"• *{escapa(j['nome'])}* — {escapa(j['classe'])} {escapa(j['raca'])}"
        for j in jogadores
    )
    await update.message.reply_text(
        f"👥 *Jogadores na aventura \\({len(jogadores)}\\):*\n\n{lista}",
        parse_mode="MarkdownV2"
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────
def formatar_atributos(atributos: dict) -> str:
    from dice import modificador
    emoji = {
        "Força": "💪", "Destreza": "🏃", "Constituição": "❤️",
        "Inteligência": "🧠", "Sabedoria": "👁️", "Carisma": "✨"
    }
    linhas = []
    for attr, val in atributos.items():
        e   = emoji.get(attr, "•")
        mod = modificador(val)
        mod_str = f"\\+{mod}" if mod >= 0 else f"\\-{abs(mod)}"
        linhas.append(f"{e} {attr}: *{val}* \\({mod_str}\\)")
    return "\n".join(linhas)


def formatar_sugestoes(sugestoes: list) -> str:
    return "\n".join(f"• _{escapa(s)}_" for s in sugestoes[:3])


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    """Registra falhas sem expor detalhes internos ao usuário."""
    log.error("Falha ao processar atualização", exc_info=ctx.error)
    if isinstance(ctx.error, TimedOut):
        log.warning("Telegram excedeu o timeout de rede; a atualização será retomada.")
        return
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ O Telegram demorou para responder. Tente novamente em instantes."
            )
        except TimedOut:
            log.warning("Também não foi possível enviar a mensagem de erro.")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN não encontrado no .env!")

    # Python 3.14 não cria automaticamente um loop no thread principal.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    proxy_url = os.getenv("TELEGRAM_PROXY") or None
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30,
        read_timeout=60,
        write_timeout=30,
        pool_timeout=30,
        proxy=proxy_url,
    )
    updates_request = HTTPXRequest(
        connection_pool_size=2,
        connect_timeout=30,
        read_timeout=60,
        write_timeout=30,
        pool_timeout=30,
        proxy=proxy_url,
    )
    def build_app():
        app = (
            ApplicationBuilder()
            .token(token)
            .request(request)
            .get_updates_request(updates_request)
            .post_init(configurar_comandos)
            .build()
        )
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("ajuda", cmd_ajuda))
        app.add_handler(CommandHandler("nova_aventura", cmd_nova_aventura))
        app.add_handler(CommandHandler("entrar", cmd_entrar))
        app.add_handler(CommandHandler("cancelar", cancelar_entrada))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_entrada))
        app.add_handler(CommandHandler("acao", cmd_acao))
        app.add_handler(CommandHandler("rolar", cmd_rolar))
        app.add_handler(CommandHandler("sugerir", cmd_sugerir))
        app.add_handler(CommandHandler("cena", cmd_cena))
        app.add_handler(CommandHandler("ficha", cmd_ficha))
        app.add_handler(CommandHandler("jogadores", cmd_jogadores))
        app.add_error_handler(error_handler)
        return app

    log.info("🎲 Bot D&D iniciado!")
    while True:
        app = build_app()
        try:
            app.run_polling(
                timeout=30,
                bootstrap_retries=-1,
                close_loop=False,
            )
            break
        except (NetworkError, TimedOut) as exc:
            log.error(
                "Não foi possível conectar ao Telegram: %s. "
                "Tentando novamente em 15 segundos.",
                exc,
            )
            time.sleep(15)


if __name__ == "__main__":
    main()
