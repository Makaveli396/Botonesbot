import logging
import os
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Set
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, 
    InputMediaVideo, InputMediaDocument
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden, BadRequest

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
BOT_TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', f'https://telegram-multi-publisher-bot.onrender.com')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado en variables de entorno")

# Almacenamiento temporal (en producción usar Redis o PostgreSQL)
user_posts: Dict = {}
user_states: Dict = {}
user_channels: Dict = {}

class MediaPost:
    def __init__(self):
        self.text: str = ""
        self.media_group: List = []
        self.single_media: Optional[Dict] = None
        self.buttons: List = []
        self.media_type: str = "text"
        self.target_channels: Set[str] = set()
        
    def add_media(self, file_id: str, media_type: str, caption: str = ""):
        media_item = {
            'file_id': file_id,
            'type': media_type,
            'caption': caption
        }
        
        if len(self.media_group) == 0 and not self.single_media:
            self.single_media = media_item
            self.media_type = media_type
        else:
            if self.single_media:
                self.media_group.append(self.single_media)
                self.single_media = None
            self.media_group.append(media_item)
            self.media_type = "media_group"

class ChannelManager:
    def __init__(self, bot):
        self.bot = bot
    
    async def get_user_channels(self, user_id: int) -> List[Dict]:
        """Obtiene canales del usuario"""
        channels = []
        
        if user_id in user_channels:
            for channel_id, channel_info in user_channels[user_id].items():
                try:
                    chat = await self.bot.get_chat(channel_id)
                    bot_member = await self.bot.get_chat_member(channel_id, self.bot.id)
                    
                    if bot_member.can_post_messages or chat.type == 'supergroup':
                        channels.append({
                            'id': channel_id,
                            'title': chat.title,
                            'type': chat.type,
                            'username': chat.username,
                            'member_count': await self._get_member_count(channel_id),
                            'can_post': True
                        })
                except Exception as e:
                    logger.warning(f"Error verificando canal {channel_id}: {e}")
                    if user_id in user_channels and channel_id in user_channels[user_id]:
                        del user_channels[user_id][channel_id]
        
        return channels
    
    async def _get_member_count(self, chat_id: str) -> int:
        try:
            return await self.bot.get_chat_member_count(chat_id)
        except:
            return 0
    
    async def add_channel(self, user_id: int, channel_identifier: str) -> Dict:
        """Añade un canal"""
        try:
            if channel_identifier.startswith('@'):
                chat = await self.bot.get_chat(channel_identifier)
            elif channel_identifier.startswith('-100') or channel_identifier.startswith('-'):
                chat = await self.bot.get_chat(int(channel_identifier))
            else:
                chat = await self.bot.get_chat(f"@{channel_identifier}")
            
            bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
            
            if bot_member.status not in ['administrator', 'creator']:
                return {'success': False, 'error': 'El bot no es administrador'}
            
            try:
                user_member = await self.bot.get_chat_member(chat.id, user_id)
                if user_member.status not in ['administrator', 'creator']:
                    return {'success': False, 'error': 'No eres administrador'}
            except:
                return {'success': False, 'error': 'No tienes acceso al canal'}
            
            if user_id not in user_channels:
                user_channels[user_id] = {}
            
            user_channels[user_id][str(chat.id)] = {
                'title': chat.title,
                'username': chat.username,
                'type': chat.type,
                'added_at': datetime.now().isoformat()
            }
            
            return {
                'success': True,
                'channel': {
                    'id': str(chat.id),
                    'title': chat.title,
                    'username': chat.username,
                    'type': chat.type,
                    'member_count': await self._get_member_count(chat.id)
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': f'Error: {str(e)}'}

class TelegramPublisher:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.channel_manager = ChannelManager(self.app.bot)
        self.setup_handlers()
    
    def setup_handlers(self):
        """Configura manejadores"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("nueva", self.new_post))
        self.app.add_handler(CommandHandler("canales", self.manage_channels))
        
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        self.app.add_handler(MessageHandler(filters.DOCUMENT, self.handle_document))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de inicio"""
        user = update.effective_user
        user_id = user.id
        
        if user_id not in user_posts:
            user_posts[user_id] = {}
            user_states[user_id] = {'current_post': None, 'step': 'idle'}
            user_channels[user_id] = {}
        
        welcome_text = f"""
🚀 **Bot Publicador Multi-Canal**

¡Hola {user.first_name}! Tu asistente para publicaciones masivas.

🎯 **FUNCIONES PRINCIPALES:**
• 📝 Crear publicaciones multimedia
• 📺 Gestionar múltiples canales
• 🎯 Publicar simultáneamente
• 🔘 Botones interactivos

**¡Conecta tus canales y comienza!**
        """
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("❓ Ayuda")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def manage_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestión de canales"""
        user_id = update.effective_user.id
        channels = await self.channel_manager.get_user_channels(user_id)
        
        if not channels:
            keyboard = [
                [InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📺 **Gestión de Canales**\n\n"
                "🔍 No tienes canales configurados.\n\n"
                "**Para añadir canales:**\n"
                "1. Añade el bot como administrador\n"
                "2. Dale permisos para publicar\n"
                "3. Usa el botón para añadir",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        channels_text = "📺 **Tus Canales**\n\n"
        keyboard = []
        
        for channel in channels[:10]:
            channels_text += f"✅ **{channel['title']}**\n"
            channels_text += f"   👥 {channel['member_count']} miembros\n"
            if channel['username']:
                channels_text += f"   🔗 @{channel['username']}\n"
            channels_text += "\n"
        
        keyboard.append([InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            channels_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def new_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Nueva publicación"""
        user_id = update.effective_user.id
        
        channels = await self.channel_manager.get_user_channels(user_id)
        if not channels:
            keyboard = [[InlineKeyboardButton("📺 Configurar Canales", callback_data="add_channel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ **No tienes canales configurados**\n\n"
                "Primero añade canales donde publicar.",
                reply_markup=reply_markup
            )
            return
        
        post_id = f"post_{datetime.now().timestamp()}"
        user_posts[user_id][post_id] = MediaPost()
        user_states[user_id]['current_post'] = post_id
        user_states[user_id]['step'] = 'creating'
        
        keyboard = [
            [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📝 Añadir Texto", callback_data="add_text")],
            [InlineKeyboardButton("📤 Enviar Ahora", callback_data="send_now")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎯 **Nueva Publicación Multi-Canal**\n\n"
            f"📺 Canales disponibles: {len(channels)}\n\n"
            "**Selecciona una opción:**",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "add_channel":
            await self._handle_add_channel(query, user_id)
        elif data == "select_channels":
            await self._handle_select_channels(query, user_id)
        elif data.startswith("toggle_channel_"):
            await self._handle_toggle_channel(query, user_id, data)
        elif data == "send_now":
            await self._handle_send_now(query, user_id)
        elif data == "add_text":
            await self._handle_add_text(query, user_id)
    
    async def _handle_add_channel(self, query, user_id: int):
        user_states[user_id]['step'] = 'adding_channel'
        
        await query.edit_message_text(
            "➕ **Añadir Canal**\n\n"
            "**Pasos:**\n"
            "1. Añade el bot como administrador\n"
            "2. Dale permisos de publicación\n"
            "3. Envía el identificador:\n\n"
            "**Formatos:**\n"
            "• `@nombre_canal`\n"
            "• `https://t.me/nombre_canal`\n"
            "• `-100xxxxxxxxx` (ID numérico)",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_select_channels(self, query, user_id: int):
        current_post = self._get_current_post(user_id)
        if not current_post:
            await query.edit_message_text("❌ No hay publicación activa.")
            return
        
        channels = await self.channel_manager.get_user_channels(user_id)
        
        keyboard = []
        for channel in channels:
            is_selected = channel['id'] in current_post.target_channels
            icon = "✅" if is_selected else "⬜"
            
            keyboard.append([InlineKeyboardButton(
                f"{icon} {channel['title']} ({channel['member_count']})",
                callback_data=f"toggle_channel_{channel['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("📤 Publicar", callback_data="send_now")])
        
        await query.edit_message_text(
            f"🎯 **Seleccionar Canales**\n\n"
            f"📊 Seleccionados: {len(current_post.target_channels)}\n\n"
            "Toca los canales donde publicar:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_toggle_channel(self, query, user_id: int, data: str):
        channel_id = data.replace("toggle_channel_", "")
        current_post = self._get_current_post(user_id)
        
        if not current_post:
            return
        
        if channel_id in current_post.target_channels:
            current_post.target_channels.remove(channel_id)
        else:
            current_post.target_channels.add(channel_id)
        
        await self._handle_select_channels(query, user_id)
    
    async def _handle_send_now(self, query, user_id: int):
        current_post = self._get_current_post(user_id)
        if not current_post:
            await query.edit_message_text("❌ No hay publicación activa.")
            return
        
        if not current_post.target_channels:
            await query.edit_message_text("❌ Selecciona canales primero.")
            return
        
        if not (current_post.text or current_post.single_media or current_post.media_group):
            await query.edit_message_text("❌ La publicación está vacía.")
            return
        
        progress_msg = await query.edit_message_text(
            f"📤 **Publicando en {len(current_post.target_channels)} canales...**"
        )
        
        results = await self._publish_to_channels(current_post, user_id)
        
        success_count = sum(1 for r in results if r['success'])
        
        result_text = f"📊 **Resultados**\n\n"
        result_text += f"✅ Exitosos: {success_count}/{len(current_post.target_channels)}\n\n"
        
        for result in results:
            if result['success']:
                result_text += f"✅ {result['channel_name']}\n"
            else:
                result_text += f"❌ {result['channel_name']}: {result['error']}\n"
        
        await progress_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
        self._clear_user_post(user_id)
    
    async def _handle_add_text(self, query, user_id: int):
        user_states[user_id]['step'] = 'adding_text'
        await query.edit_message_text(
            "✍️ **Escribir Texto**\n\n"
            "Envía el texto para la publicación.\n\n"
            "Puedes usar formato Markdown."
        )
    
    async def _publish_to_channels(self, post: MediaPost, user_id: int) -> List[Dict]:
        results = []
        channels = await self.channel_manager.get_user_channels(user_id)
        channel_dict = {ch['id']: ch for ch in channels}
        
        for channel_id in post.target_channels:
            channel_info = channel_dict.get(channel_id, {})
            channel_name = channel_info.get('title', f'Canal {channel_id}')
            
            try:
                success = await self._send_content_to_channel(channel_id, post)
                
                results.append({
                    'success': success,
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'error': 'Error de envío' if not success else None
                })
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error enviando a {channel_id}: {e}")
                results.append({
                    'success': False,
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'error': str(e)
                })
        
        return results
    
    async def _send_content_to_channel(self, channel_id: str, post: MediaPost) -> bool:
        try:
            if post.media_type == "text":
                await self.app.bot.send_message(
                    chat_id=channel_id,
                    text=post.text or "Publicación",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif post.media_type == "photo":
                await self.app.bot.send_photo(
                    chat_id=channel_id,
                    photo=post.single_media['file_id'],
                    caption=post.text,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif post.media_type == "video":
                await self.app.bot.send_video(
                    chat_id=channel_id,
                    video=post.single_media['file_id'],
                    caption=post.text,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif post.media_type == "media_group":
                media_list = []
                for i, media in enumerate(post.media_group):
                    caption = post.text if i == 0 else ""
                    
                    if media['type'] == 'photo':
                        media_list.append(InputMediaPhoto(media['file_id'], caption=caption))
                    elif media['type'] == 'video':
                        media_list.append(InputMediaVideo(media['file_id'], caption=caption))
                
                await self.app.bot.send_media_group(chat_id=channel_id, media=media_list)
            
            return True
            
        except Exception as e:
            logger.error(f"Error enviando a {channel_id}: {e}")
            return False
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        
        if user_states[user_id].get('step') == 'adding_channel':
            await self._process_channel_addition(update, update.message.caption or "")
            return
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(photo.file_id, "photo", caption)
            await update.message.reply_text("📸 **Imagen añadida**")
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        video = update.message.video
        caption = update.message.caption or ""
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(video.file_id, "video", caption)
            await update.message.reply_text("🎥 **Video añadido**")
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        document = update.message.document
        caption = update.message.caption or ""
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(document.file_id, "document", caption)
            await update.message.reply_text("📎 **Archivo añadido**")
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        # Botones del teclado
        if text == "📝 Nueva Publicación":
            await self.new_post(update, context)
            return
        elif text == "📺 Mis Canales":
            await self.manage_channels(update, context)
            return
        elif text == "❓ Ayuda":
            await self.help_command(update, context)
            return
        
        user_step = user_states[user_id].get('step', 'idle')
        
        # Añadir canal
        if user_step == 'adding_channel':
            await self._process_channel_addition(update, text)
            return
        
        current_post = self._get_current_post(user_id)
        
        if current_post and user_step in ['adding_text', 'creating']:
            current_post.text = text
            user_states[user_id]['step'] = 'creating'
            
            await update.message.reply_text(
                f"📝 **Texto añadido**\n\n{text[:100]}{'...' if len(text) > 100 else ''}"
            )
        else:
            await update.message.reply_text("💡 Usa /nueva para crear una publicación")
    
    async def _process_channel_addition(self, update: Update, text: str):
        user_id = update.effective_user.id
        
        channel_text = text.strip()
        if channel_text.startswith('https://t.me/'):
            channel_text = channel_text.replace('https://t.me/', '@')
        
        result = await self.channel_manager.add_channel(user_id, channel_text)
        
        if result['success']:
            channel = result['channel']
            user_states[user_id]['step'] = 'idle'
            
            await update.message.reply_text(
                f"✅ **Canal añadido**\n\n"
                f"📢 **{channel['title']}**\n"
                f"👥 {channel['member_count']} miembros",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"❌ **Error:** {result['error']}\n\n"
                "Verifica que el bot sea administrador."
            )
    
    def _get_current_post(self, user_id: int) -> Optional[MediaPost]:
        if user_id not in user_states or user_id not in user_posts:
            return None
        
        current_post_id = user_states[user_id].get('current_post')
        if current_post_id and current_post_id in user_posts[user_id]:
            return user_posts[user_id][current_post_id]
        
        return None
    
    def _clear_user_post(self, user_id: int):
        if user_id in user_states and user_states[user_id]['current_post']:
            post_id = user_states[user_id]['current_post']
            if user_id in user_posts and post_id in user_posts[user_id]:
                del user_posts[user_id][post_id]
            user_states[user_id] = {'current_post': None, 'step': 'idle'}
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🚀 **Bot Publicador Multi-Canal**

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
• 📸 Imágenes • 🎥 Videos
• 📎 Documentos • 📝 Texto

**CONFIGURAR CANALES:**
• Añade bot como admin
• Dale permisos de publicación
• Usa: @canal o ID numérico
        """
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# Configuración del webhook para Render
async def webhook_handler(request: Request) -> Response:
    """Maneja webhooks de Telegram"""
    try:
        body = await request.text()
        update = Update.de_json(json.loads(body), publisher.app.bot)
        await publisher.app.process_update(update)
        return Response(text="OK")
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return Response(text="ERROR", status=500)

async def health_check(request: Request) -> Response:
    """Health check para Render"""
    return Response(text="Bot is running!")

async def setup_webhook():
    """Configura el webhook"""
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await publisher.app.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook configurado: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Error configurando webhook: {e}")

async def init_app():
    """Inicializa la aplicación"""
    # Inicializar bot
    await publisher.app.initialize()
    await publisher.app.start()
    
    # Configurar webhook
    await setup_webhook()
    
    # Configurar servidor web
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    return app

# Instancia global del bot
publisher = TelegramPublisher()

def main():
    """Función principal para Render"""
    try:
        # Crear servidor web
        app_coro = init_app()
        app = asyncio.new_event_loop().run_until_complete(app_coro)
        
        # Ejecutar servidor
        logger.info(f"🚀 Bot iniciado en puerto {PORT}")
        logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")
        
        web.run_app(app, host='0.0.0.0', port=PORT)
        
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    main()