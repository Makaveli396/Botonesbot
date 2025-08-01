import logging
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Set
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Configuración
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', f'https://telegram-multi-publisher-bot.onrender.com')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado")

# Almacenamiento en memoria
user_data = {}

class MediaPost:
    def __init__(self):
        self.text = ""
        self.media = []
        self.target_channels = set()
        
    def add_media(self, file_id, media_type):
        self.media.append({'file_id': file_id, 'type': media_type})

class TelegramBot:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Configura manejadores del bot"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_cmd))
        self.app.add_handler(CommandHandler("nueva", self.new_post))
        self.app.add_handler(CommandHandler("canales", self.manage_channels))
        
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Manejadores de multimedia
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        try:
            # Probar diferentes formas de manejar documentos
            self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        except AttributeError:
            try:
                self.app.add_handler(MessageHandler(filters.DOCUMENT, self.handle_document))
            except AttributeError:
                logger.warning("No se pudo configurar handler para documentos")
        
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    def get_user_data(self, user_id):
        """Obtiene datos del usuario"""
        if user_id not in user_data:
            user_data[user_id] = {
                'current_post': None,
                'step': 'idle',
                'channels': {}
            }
        return user_data[user_id]
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user = update.effective_user
        self.get_user_data(user.id)  # Inicializar usuario
        
        text = f"""🚀 **Bot Publicador Multi-Canal**

¡Hola {user.first_name}!

**FUNCIONES:**
• 📝 Crear publicaciones
• 📺 Gestionar canales
• 🎯 Publicar simultáneamente

**COMANDOS:**
• /nueva - Nueva publicación
• /canales - Gestionar canales
• /help - Ayuda"""
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("❓ Ayuda")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def new_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Crear nueva publicación"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        # Verificar canales
        if not data['channels']:
            keyboard = [[InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")]]
            await update.message.reply_text(
                "❌ **No tienes canales configurados**\n\nPrimero añade canales donde publicar.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Crear nueva publicación
        data['current_post'] = MediaPost()
        data['step'] = 'creating'
        
        keyboard = [
            [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📝 Añadir Texto", callback_data="add_text")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
        ]
        
        await update.message.reply_text(
            f"🎯 **Nueva Publicación**\n\nCanales disponibles: {len(data['channels'])}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def manage_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestionar canales"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if not data['channels']:
            keyboard = [[InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")]]
            text = """📺 **Gestión de Canales**

No tienes canales configurados.

**Para añadir:**
1. Añade el bot como administrador
2. Dale permisos de publicación
3. Usa el botón para añadir"""
        else:
            keyboard = [[InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")]]
            text = f"📺 **Tus Canales** ({len(data['channels'])})\n\n"
            
            for ch_id, ch_info in list(data['channels'].items())[:5]:
                text += f"• {ch_info.get('title', 'Canal')}\n"
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja callbacks de botones"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = self.get_user_data(user_id)
        callback_data = query.data
        
        if callback_data == "add_channel":
            data['step'] = 'adding_channel'
            await query.edit_message_text(
                """➕ **Añadir Canal**

**Pasos:**
1. Añade el bot como administrador
2. Dale permisos de publicación
3. Envía el identificador del canal

**Formatos:**
• @nombre_canal
• https://t.me/nombre_canal
• -100xxxxxxxxx (ID)""",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif callback_data == "select_channels":
            if not data.get('current_post'):
                await query.edit_message_text("❌ No hay publicación activa")
                return
            
            keyboard = []
            for ch_id, ch_info in data['channels'].items():
                selected = ch_id in data['current_post'].target_channels
                icon = "✅" if selected else "⬜"
                keyboard.append([InlineKeyboardButton(
                    f"{icon} {ch_info.get('title', 'Canal')}",
                    callback_data=f"toggle_{ch_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("📤 Publicar", callback_data="publish")])
            
            await query.edit_message_text(
                f"🎯 **Seleccionar Canales**\n\nSeleccionados: {len(data['current_post'].target_channels)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif callback_data.startswith("toggle_"):
            ch_id = callback_data.replace("toggle_", "")
            if data.get('current_post'):
                if ch_id in data['current_post'].target_channels:
                    data['current_post'].target_channels.remove(ch_id)
                else:
                    data['current_post'].target_channels.add(ch_id)
                
                # Actualizar vista
                await self.callback_handler(update, context)
        
        elif callback_data == "add_text":
            data['step'] = 'adding_text'
            await query.edit_message_text("✍️ **Escribir Texto**\n\nEnvía el texto para la publicación:")
        
        elif callback_data == "publish":
            await self.publish_post(query, user_id)
    
    async def publish_post(self, query, user_id):
        """Publica la publicación en los canales"""
        data = self.get_user_data(user_id)
        post = data.get('current_post')
        
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        if not post.target_channels:
            await query.edit_message_text("❌ Selecciona canales primero")
            return
        
        if not post.text and not post.media:
            await query.edit_message_text("❌ La publicación está vacía")
            return
        
        # Publicar
        results = []
        for ch_id in post.target_channels:
            try:
                if post.media:
                    # Enviar con media
                    media_item = post.media[0]
                    if media_item['type'] == 'photo':
                        await self.app.bot.send_photo(
                            chat_id=ch_id,
                            photo=media_item['file_id'],
                            caption=post.text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'video':
                        await self.app.bot.send_video(
                            chat_id=ch_id,
                            video=media_item['file_id'],
                            caption=post.text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                else:
                    # Solo texto
                    await self.app.bot.send_message(
                        chat_id=ch_id,
                        text=post.text or "Publicación",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                results.append(f"✅ {data['channels'][ch_id].get('title', 'Canal')}")
                
            except Exception as e:
                logger.error(f"Error publicando en {ch_id}: {e}")
                results.append(f"❌ {data['channels'][ch_id].get('title', 'Canal')}: Error")
        
        # Mostrar resultados
        result_text = f"📊 **Resultados**\n\n" + "\n".join(results)
        await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)
        
        # Limpiar
        data['current_post'] = None
        data['step'] = 'idle'
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja fotos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            photo = update.message.photo[-1]
            data['current_post'].add_media(photo.file_id, 'photo')
            await update.message.reply_text("📸 **Imagen añadida**")
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja videos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            video = update.message.video
            data['current_post'].add_media(video.file_id, 'video')
            await update.message.reply_text("🎥 **Video añadido**")
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja documentos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            document = update.message.document
            data['current_post'].add_media(document.file_id, 'document')
            await update.message.reply_text("📎 **Documento añadido**")
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja texto"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        text = update.message.text
        
        # Botones del teclado
        if text == "📝 Nueva Publicación":
            await self.new_post(update, context)
            return
        elif text == "📺 Mis Canales":
            await self.manage_channels(update, context)
            return
        elif text == "❓ Ayuda":
            await self.help_cmd(update, context)
            return
        
        step = data.get('step', 'idle')
        
        if step == 'adding_channel':
            await self.add_channel(update, user_id, text)
        elif step == 'adding_text' and data.get('current_post'):
            data['current_post'].text = text
            data['step'] = 'creating'
            await update.message.reply_text(f"📝 **Texto añadido**\n\n{text[:100]}...")
        else:
            await update.message.reply_text("💡 Usa los botones o comandos disponibles")
    
    async def add_channel(self, update, user_id, channel_text):
        """Añade un canal"""
        data = self.get_user_data(user_id)
        
        # Limpiar texto
        channel_text = channel_text.strip()
        if channel_text.startswith('https://t.me/'):
            channel_text = channel_text.replace('https://t.me/', '@')
        
        try:
            # Obtener info del canal
            if channel_text.startswith('@'):
                chat = await self.app.bot.get_chat(channel_text)
            elif channel_text.startswith('-'):
                chat = await self.app.bot.get_chat(int(channel_text))
            else:
                chat = await self.app.bot.get_chat(f"@{channel_text}")
            
            # Verificar permisos
            bot_member = await self.app.bot.get_chat_member(chat.id, self.app.bot.id)
            if bot_member.status not in ['administrator', 'creator']:
                await update.message.reply_text("❌ El bot no es administrador del canal")
                return
            
            # Guardar canal
            data['channels'][str(chat.id)] = {
                'title': chat.title,
                'username': chat.username,
                'type': chat.type
            }
            
            data['step'] = 'idle'
            
            await update.message.reply_text(
                f"✅ **Canal añadido**\n\n📢 {chat.title}",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error añadiendo canal: {e}")
            await update.message.reply_text(f"❌ **Error:** {str(e)}")
    
    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de ayuda"""
        text = """🚀 **Bot Publicador Multi-Canal**

**COMANDOS:**
• `/nueva` - Nueva publicación
• `/canales` - Gestionar canales
• `/help` - Esta ayuda

**FLUJO:**
1. Configura canales (/canales)
2. Crea publicación (/nueva)
3. Selecciona canales
4. Añade contenido
5. Publica

**MULTIMEDIA:**
• 📸 Imágenes
• 🎥 Videos
• 📎 Documentos
• 📝 Texto con formato

**CONFIGURAR CANALES:**
• Añade bot como admin
• Dale permisos de publicación
• Formatos: @canal, t.me/canal, ID"""
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# Configuración del servidor web
async def webhook_handler(request: Request) -> Response:
    """Maneja webhooks de Telegram"""
    try:
        body = await request.text()
        update = Update.de_json(json.loads(body), bot.app.bot)
        await bot.app.process_update(update)
        return Response(text="OK")
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return Response(text="ERROR", status=500)

async def health_check(request: Request) -> Response:
    """Health check"""
    return Response(text="Bot is running!")

async def setup_webhook():
    """Configura webhook"""
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await bot.app.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook configurado: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Error webhook: {e}")

async def init_app():
    """Inicializa aplicación"""
    await bot.app.initialize()
    await bot.app.start()
    await setup_webhook()
    
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    return app

# Instancia del bot
bot = TelegramBot()

def main():
    """Función principal"""
    import asyncio
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        app = loop.run_until_complete(init_app())
        
        logger.info(f"🚀 Bot iniciado en puerto {PORT}")
        logger.info(f"🌐 Webhook: {WEBHOOK_URL}")
        
        web.run_app(app, host='0.0.0.0', port=PORT)
        
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    main()