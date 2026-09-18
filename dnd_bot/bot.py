"""
Bot principal com endpoint de health check para Render.
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask

# Configurar logging
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# Imports locais
from database import Database
from narrator import Narrator

# Inicializar componentes
db = Database(path=os.getenv("DATABASE_PATH", "dnd.db"), db_url=os.getenv("SUPABASE_DB_URL"))
narrator = Narrator(os.getenv("GEMINI_API_KEY"))

# Flask para health check
app = Flask(__name__)

@app.route('/health')
def health():
    """Health check endpoint para Render."""
    return {"status": "healthy", "bot": "running"}, 200

# Handlers do bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start."""
    await update.message.reply_text(
        "Bem-vindo ao D&D Narrator Bot!\n\n"
        "Para começ​ar, me diga:\n"
        "1. Nome do seu personagem\n"
        "2. Classe (Guerreiro, Mago, Clé©©rigo, Ladino, Bardo)\n"
        "3. Raç©©a (Humano, Elfo, Anã©£o, etc.)\n"
        "4. Detalhes adicionais (opcional)\n\n"
        "Vamos começ​ar! Qual o nome do seu personagem?"
    )
    return 0

async def entrar_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe nome do personagem."""
    context.user_data['nome'] = update.message.text
    await update.message.reply_text(
        f"Ó³timo, {update.message.text}!\n\n"
        "Agora escolha sua classe:\n"
        "1. Guerreiro\n"
        "2. Mago\n"
        "3. Clé©©rigo\n"
        "4. Ladino\n"
        "5. Bardo\n\n"
        "Digite o nú​mero da classe:"
    )
    return 1

async def entrar_classe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe classe do personagem."""
    classe_numero = update.message.text
    classes = {"1": "Guerreiro", "2": "Mago", "3": "Clé©©rigo", "4": "Ladino", "5": "Bardo"}
    classe = classes.get(classe_numero, "Guerreiro")
    context.user_data['classe'] = classe
    await update.message.reply_text(
        f"Excelente {classe}!\n\n"
        "Agora me diga sua raç©©a:\n"
        "(Humano, Elfo, Anã©£o, Orc, Halfling, etc.)"
    )
    return 2

async def entrar_raca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe raç©©a do personagem."""
    context.user_data['raca'] = update.message.text
    await update.message.reply_text(
        "Perfeito! Agora me conte um pouco mais sobre seu personagem.\n"
        "Pode ser:\n"
        "- Histó³©©ria de fundo\n"
        "- Personalidade\n"
        "- Objetivos\n"
        "- Ou qualquer outro detalhe que queira\n\n"
        "(Digite 'pular' se nã©£o quiser adicionar detalhes)"
    )
    return 3

async def entrar_detalhes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe detalhes do personagem."""
    detalhes = update.message.text
    if detalhes.lower() == 'pular':
        detalhes = ""
    context.user_data['detalhes'] = detalhes
    
    # Criar personagem no banco
    try:
        db.create_character(
            user_id=update.effective_user.id,
            name=context.user_data.get('nome', 'Desconhecido'),
            class_name=context.user_data.get('classe', 'Guerreiro'),
            race=context.user_data.get('raca', 'Humano'),
            details=detalhes
        )
        await update.message.reply_text(
            f"Personagem criado com sucesso!\n\n"
            f"Nome: {context.user_data.get('nome')}\n"
            f"Classe: {context.user_data.get('classe')}\n"
            f"Raç©©a: {context.user_data.get('raca')}\n\n"
            "Use /mychar para ver seu personagem\n"
            "Use /startcampaign para iniciar uma campanha"
        )
    except Exception as e:
        log.error(f"Erro ao criar personagem: {e}")
        await update.message.reply_text("Erro ao criar personagem. Tente novamente.)")
    
    return 4

async def mychar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra dados do personagem."""
    try:
        char = db.get_character(update.effective_user.id)
        if char:
            await update.message.reply_text(
                f"Seu personagem:\n\n"
                f"Nome: {char['name']}\n"
                f"Classe: {char['class']}\n"
                f"Raç©©a: {char.get('race', 'Nã©£o informada')}\n"
                f"Detalhes: {char.get('details', 'Nenhum')}"
            )
        else:
            await update.message.reply_text("VocÅª nã©£o tem um personagem. Use /start para criar.")
    except Exception as e:
        log.error(f"Erro ao buscar personagem: {e}")
        await update.message.reply_text("Erro ao buscar personagem.")

async def startcampaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia nova campanha."""
    await update.message.reply_text(
        "Para iniciar uma campanha, me diga:\n"
        "1. Nome da campanha\n"
        "2. Descriç©£o breve (opcional)\n\n"
        "Digite o nome da campanha:"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help."""
    await update.message.reply_text(
        "Comandos disponí©©veis:\n\n"
        "/start - Criar novo personagem\n"
        "/mychar - Ver seu personagem\n"
        "/startcampaign - Iniciar campanha\n"
        "/help - Esta mensagem"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler de erros."""
    log.error(f"Erro: {context.error}")
    if update:
        await update.message.reply_text("Desculpe, ocorreu um erro. Tente novamente.")

def run_bot():
    """Inicia o bot."""
    log.info("Iniciando bot...")
    
    # Criar aplicaç©£o
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    
    # Adicionar handlers
    from telegram.ext import MessageHandler, filters, ConversationHandler
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, entrar_nome)],
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, entrar_classe)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, entrar_raca)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, entrar_detalhes)],
        },
        fallbacks=[],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('mychar', mychar))
    application.add_handler(CommandHandler('startcampaign', startcampaign))
    application.add_handler(CommandHandler('help', help_command))
    application.add_error_handler(error_handler)
    
    log.info("Bot iniciado com sucesso!")
    
    # Rodar bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    import sys
    
    # Se for health check, rodar Flask
    if len(sys.argv) > 1 and sys.argv[1] == 'health':
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
    else:
        # Rodar bot normalmente
        run_bot()
