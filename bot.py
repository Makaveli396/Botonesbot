import logging
import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from io import BytesIO

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, 
    InputMediaVideo, InputMediaDocument, Chat, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError, Forbidden, BadRequest

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token del bot desde variable de entorno
BOT_TOKEN = os.getenv('BOT_TOKEN', 'TU_TOKEN_AQUI')

# Almacenamiento temporal (en producción usar Redis o PostgreSQL)
user_posts: Dict = {}
user_states: Dict = {}
user_channels: Dict = {}  # Canales por usuario
scheduled_posts: Dict = {}  # Posts programados

class MediaPost:
    def __init__(self):
        self.text: str = ""
        self.media_group: List = []
        self.single_media: Optional[Dict] = None
        self.buttons: List = []
        self.media_type: str = "text"
        self.target_channels: Set[str] = set()  # IDs de canales objetivo
        self.scheduled_time: Optional[datetime] = None
        self.custom_texts: Dict[str, str] = {}  # Textos personalizados por canal
        
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
    def __init__(self, bot_app):
        self.bot = bot_app.bot
    
    async def get_user_channels(self, user_id: int) -> List[Dict]:
        """Obtiene todos los canales donde el usuario es administrador"""
        channels = []
        
        if user_id in user_channels:
            for channel_id, channel_info in user_channels[user_id].items():
                try:
                    # Verificar si el canal aún existe y el bot tiene permisos
                    chat = await self.bot.get_chat(channel_id)
                    bot_member = await self.bot.get_chat_member(channel_id, self.bot.id)
                    
                    if bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                        if bot_member.can_post_messages or chat.type == Chat.GROUP:
                            channels.append({
                                'id': channel_id,
                                'title': chat.title,
                                'type': chat.type,
                                'username': chat.username,
                                'member_count': await self._get_member_count(channel_id),
                                'can_post': True
                            })
                        else:
                            channels.append({
                                'id': channel_id,
                                'title': chat.title,
                                'type': chat.type,
                                'username': chat.username,
                                'member_count': await self._get_member_count(channel_id),
                                'can_post': False
                            })
                except Exception as e:
                    logger.warning(f"Error verificando canal {channel_id}: {e}")
                    # Remover canal inválido
                    if user_id in user_channels and channel_id in user_channels[user_id]:
                        del user_channels[user_id][channel_id]
        
        return channels
    
    async def _get_member_count(self, chat_id: str) -> int:
        """Obtiene el número de miembros de un chat"""
        try:
            return await self.bot.get_chat_member_count(chat_id)
        except:
            return 0
    
    async def add_channel(self, user_id: int, channel_identifier: str) -> Dict:
        """Añade un canal a la lista del usuario"""
        try:
            # Intentar obtener información del canal
            if channel_identifier.startswith('@'):
                chat = await self.bot.get_chat(channel_identifier)
            elif channel_identifier.startswith('-100') or channel_identifier.startswith('-'):
                chat = await self.bot.get_chat(int(channel_identifier))
            else:
                chat = await self.bot.get_chat(f"@{channel_identifier}")
            
            # Verificar permisos del bot
            bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
            
            if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return {'success': False, 'error': 'El bot no es administrador en este canal'}
            
            if chat.type == Chat.CHANNEL and not bot_member.can_post_messages:
                return {'success': False, 'error': 'El bot no tiene permisos para publicar en este canal'}
            
            # Verificar permisos del usuario
            try:
                user_member = await self.bot.get_chat_member(chat.id, user_id)
                if user_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                    return {'success': False, 'error': 'No eres administrador de este canal'}
            except:
                return {'success': False, 'error': 'No tienes acceso a este canal'}
            
            # Guardar canal
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
            
        except Forbidden:
            return {'success': False, 'error': 'El bot fue removido del canal o no tiene acceso'}
        except BadRequest as e:
            return {'success': False, 'error': f'Canal no encontrado: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'Error: {str(e)}'}

class TelegramPublisher:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.channel_manager = ChannelManager(self.app)
        self.setup_handlers()
    
    def setup_handlers(self):
        """Configura todos los manejadores del bot"""
        # Comandos principales
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("nueva", self.new_post))
        self.app.add_handler(CommandHandler("canales", self.manage_channels))
        self.app.add_handler(CommandHandler("programar", self.schedule_post))
        
        # Manejadores de callbacks
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Manejadores de multimedia
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.VIDEO_NOTE, self.handle_video_note))
        self.app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        self.app.add_handler(MessageHandler(filters.DOCUMENT, self.handle_document))
        self.app.add_handler(MessageHandler(filters.STICKER, self.handle_sticker))
        
        # Manejador de texto (debe ir al final)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de inicio con menú completo"""
        user = update.effective_user
        user_id = user.id
        
        # Inicializar usuario
        if user_id not in user_posts:
            user_posts[user_id] = {}
            user_states[user_id] = {'current_post': None, 'step': 'idle'}
            user_channels[user_id] = {}
        
        welcome_text = f"""
🚀 **Bot Publicador Multi-Canal**

¡Hola {user.first_name}! Tu asistente para publicaciones masivas.

🎯 **FUNCIONES PRINCIPALES:**
• 📝 Crear publicaciones multimedia
• 📺 Gestionar múltiples canales/grupos
• 🎯 Publicar simultáneamente
• 📅 Programar envíos automáticos
• 🎨 Personalizar contenido por canal

🔥 **MULTIMEDIA SOPORTADO:**
• 📸 Imágenes y álbumes • 🎥 Videos y GIFs
• 🔊 Audio y notas de voz • 📎 Documentos
• 😊 Stickers • 🔘 Botones interactivos

**¡Conecta tus canales y comienza!**
        """
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("📅 Programar Envío"), KeyboardButton("📊 Estadísticas")],
            [KeyboardButton("⚙️ Configuración"), KeyboardButton("❓ Ayuda")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def manage_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestión completa de canales"""
        user_id = update.effective_user.id
        channels = await self.channel_manager.get_user_channels(user_id)
        
        if not channels:
            keyboard = [
                [InlineKeyboardButton("➕ Añadir Primer Canal", callback_data="add_channel")],
                [InlineKeyboardButton("📖 Guía de Configuración", callback_data="channel_guide")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📺 **Gestión de Canales**\n\n"
                "🔍 No tienes canales configurados aún.\n\n"
                "**Para añadir canales:**\n"
                "1. Añade el bot como administrador\n"
                "2. Dale permisos para publicar\n"
                "3. Usa el botón para añadir el canal\n\n"
                "**Formatos aceptados:**\n"
                "• `@nombre_canal`\n"
                "• `https://t.me/nombre_canal`\n"
                "• `-100xxxxxxxxx` (ID numérico)",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Mostrar canales existentes
        channels_text = "📺 **Tus Canales Configurados**\n\n"
        keyboard = []
        
        for i, channel in enumerate(channels[:10], 1):  # Límite de 10 para el teclado
            status_icon = "✅" if channel['can_post'] else "❌"
            type_icon = "📢" if channel['type'] == 'channel' else "👥"
            
            channels_text += f"{status_icon} {type_icon} **{channel['title']}**\n"
            channels_text += f"   👥 {channel['member_count']} miembros\n"
            if channel['username']:
                channels_text += f"   🔗 @{channel['username']}\n"
            channels_text += f"   📱 `{channel['id']}`\n\n"
            
            # Botón para gestionar canal individual
            keyboard.append([InlineKeyboardButton(
                f"{status_icon} {channel['title'][:25]}...", 
                callback_data=f"manage_channel_{channel['id']}"
            )])
        
        # Botones de gestión
        keyboard.extend([
            [InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel"),
             InlineKeyboardButton("🔄 Verificar Todos", callback_data="verify_channels")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data="channel_stats"),
             InlineKeyboardButton("⚙️ Configurar", callback_data="channel_settings")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            channels_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def new_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Crear nueva publicación multi-canal"""
        user_id = update.effective_user.id
        
        # Verificar canales disponibles
        channels = await self.channel_manager.get_user_channels(user_id)
        available_channels = [ch for ch in channels if ch['can_post']]
        
        if not available_channels:
            keyboard = [[InlineKeyboardButton("📺 Configurar Canales", callback_data="add_channel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ **No tienes canales configurados**\n\n"
                "Primero debes añadir y configurar tus canales.\n"
                "El bot necesita ser administrador con permisos de publicación.",
                reply_markup=reply_markup
            )
            return
        
        # Crear nueva publicación
        post_id = f"post_{datetime.now().timestamp()}"
        user_posts[user_id][post_id] = MediaPost()
        user_states[user_id]['current_post'] = post_id
        user_states[user_id]['step'] = 'creating'
        
        keyboard = [
            [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📝 Añadir Texto", callback_data="add_text"),
             InlineKeyboardButton("🖼️ Añadir Media", callback_data="add_media")],
            [InlineKeyboardButton("🔘 Añadir Botones", callback_data="add_buttons")],
            [InlineKeyboardButton("🎨 Personalizar por Canal", callback_data="customize_channels")],
            [InlineKeyboardButton("📅 Programar Envío", callback_data="schedule_post"),
             InlineKeyboardButton("📤 Enviar Ahora", callback_data="send_now")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview_multi")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        channels_info = f"📺 **Canales disponibles:** {len(available_channels)}\n"
        for ch in available_channels[:3]:
            channels_info += f"• {ch['title']} ({ch['member_count']} miembros)\n"
        if len(available_channels) > 3:
            channels_info += f"• ... y {len(available_channels) - 3} más\n"
        
        await update.message.reply_text(
            f"🎯 **Nueva Publicación Multi-Canal**\n\n"
            f"{channels_info}\n"
            "**Selecciona una opción para comenzar:**",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja callbacks de botones"""
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
        elif data == "confirm_channels":
            await self._handle_confirm_channels(query, user_id)
        elif data == "preview_multi":
            await self._handle_preview_multi(query, user_id)
        elif data == "send_now":
            await self._handle_send_now(query, user_id)
        elif data == "customize_channels":
            await self._handle_customize_channels(query, user_id)
        elif data.startswith("customize_"):
            await self._handle_channel_customization(query, user_id, data)
        elif data == "add_text":
            await self._handle_add_text(query, user_id)
        elif data == "add_buttons":
            await self._handle_add_buttons(query, user_id)
        # ... otros callbacks existentes
    
    async def _handle_add_channel(self, query, user_id: int):
        """Maneja la adición de nuevos canales"""
        user_states[user_id]['step'] = 'adding_channel'
        
        await query.edit_message_text(
            "➕ **Añadir Nuevo Canal**\n\n"
            "**Pasos para añadir un canal:**\n\n"
            "1️⃣ **Añade el bot a tu canal como administrador**\n"
            "   • Ve a tu canal\n"
            "   • Configuración → Administradores\n"
            "   • Añadir administrador → Buscar este bot\n\n"
            "2️⃣ **Dale permisos de publicación**\n"
            "   • ✅ Publicar mensajes\n"
            "   • ✅ Editar mensajes\n"
            "   • ✅ Eliminar mensajes\n\n"
            "3️⃣ **Envía el identificador del canal:**\n\n"
            "**Formatos válidos:**\n"
            "• `@nombre_canal`\n"
            "• `https://t.me/nombre_canal`\n"
            "• `-100xxxxxxxxx` (ID numérico)\n\n"
            "💡 **Tip:** Para obtener el ID, reenvía un mensaje del canal a @userinfobot",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_select_channels(self, query, user_id: int):
        """Maneja la selección de canales para publicación"""
        current_post = self._get_current_post(user_id)
        if not current_post:
            await query.edit_message_text("❌ No hay publicación activa.")
            return
        
        channels = await self.channel_manager.get_user_channels(user_id)
        available_channels = [ch for ch in channels if ch['can_post']]
        
        if not available_channels:
            await query.edit_message_text("❌ No tienes canales disponibles para publicar.")
            return
        
        keyboard = []
        for channel in available_channels:
            is_selected = channel['id'] in current_post.target_channels
            icon = "✅" if is_selected else "⬜"
            type_icon = "📢" if channel['type'] == 'channel' else "👥"
            
            keyboard.append([InlineKeyboardButton(
                f"{icon} {type_icon} {channel['title']} ({channel['member_count']})",
                callback_data=f"toggle_channel_{channel['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("✅ Confirmar Selección", callback_data="confirm_channels")])
        
        selected_count = len(current_post.target_channels)
        await query.edit_message_text(
            f"🎯 **Seleccionar Canales de Destino**\n\n"
            f"📊 **Seleccionados:** {selected_count}/{len(available_channels)}\n\n"
            "Toca los canales donde quieres publicar:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_toggle_channel(self, query, user_id: int, data: str):
        """Alterna la selección de un canal"""
        channel_id = data.replace("toggle_channel_", "")
        current_post = self._get_current_post(user_id)
        
        if not current_post:
            return
        
        if channel_id in current_post.target_channels:
            current_post.target_channels.remove(channel_id)
        else:
            current_post.target_channels.add(channel_id)
        
        # Actualizar la vista
        await self._handle_select_channels(query, user_id)
    
    async def _handle_send_now(self, query, user_id: int):
        """Publica inmediatamente en todos los canales seleccionados"""
        current_post = self._get_current_post(user_id)
        if not current_post:
            await query.edit_message_text("❌ No hay publicación activa.")
            return
        
        if not current_post.target_channels:
            await query.edit_message_text("❌ No has seleccionado ningún canal.")
            return
        
        if not (current_post.text or current_post.single_media or current_post.media_group):
            await query.edit_message_text("❌ La publicación está vacía.")
            return
        
        # Mostrar progreso
        progress_msg = await query.edit_message_text(
            f"📤 **Publicando en {len(current_post.target_channels)} canales...**\n\n"
            "🔄 Iniciando envío..."
        )
        
        results = await self._publish_to_channels(current_post, user_id)
        
        # Mostrar resultados
        success_count = sum(1 for r in results if r['success'])
        total_reach = sum(r.get('member_count', 0) for r in results if r['success'])
        
        result_text = f"📊 **Resultados del Envío**\n\n"
        result_text += f"✅ **Exitosos:** {success_count}/{len(current_post.target_channels)}\n"
        result_text += f"👥 **Alcance total:** {total_reach:,} personas\n\n"
        
        # Detalles por canal
        for result in results:
            if result['success']:
                result_text += f"✅ {result['channel_name']} ({result['member_count']})\n"
            else:
                result_text += f"❌ {result['channel_name']}: {result['error']}\n"
        
        await progress_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
        
        # Limpiar publicación
        self._clear_user_post(user_id)
    
    async def _publish_to_channels(self, post: MediaPost, user_id: int) -> List[Dict]:
        """Publica en todos los canales seleccionados"""
        results = []
        channels = await self.channel_manager.get_user_channels(user_id)
        channel_dict = {ch['id']: ch for ch in channels}
        
        for channel_id in post.target_channels:
            channel_info = channel_dict.get(channel_id, {})
            channel_name = channel_info.get('title', f'Canal {channel_id}')
            
            try:
                # Obtener texto personalizado o usar el general
                text = post.custom_texts.get(channel_id, post.text)
                
                # Crear botones inline
                reply_markup = None
                if post.buttons:
                    keyboard = []
                    for btn in post.buttons:
                        if btn['data'].startswith('http'):
                            keyboard.append([InlineKeyboardButton(btn['text'], url=btn['data'])])
                        else:
                            keyboard.append([InlineKeyboardButton(btn['text'], callback_data=btn['data'])])
                    reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Enviar según tipo de contenido
                success = await self._send_content_to_channel(
                    channel_id, post, text, reply_markup
                )
                
                if success:
                    results.append({
                        'success': True,
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'member_count': channel_info.get('member_count', 0)
                    })
                else:
                    results.append({
                        'success': False,
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'error': 'Error de envío'
                    })
                    
                # Pequeña pausa entre envíos
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error enviando a canal {channel_id}: {e}")
                results.append({
                    'success': False,
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'error': str(e)
                })
        
        return results
    
    async def _send_content_to_channel(self, channel_id: str, post: MediaPost, text: str, reply_markup) -> bool:
        """Envía contenido específico a un canal"""
        try:
            if post.media_type == "text":
                await self.app.bot.send_message(
                    chat_id=channel_id,
                    text=text or "Publicación sin texto",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            elif post.media_type == "photo":
                await self.app.bot.send_photo(
                    chat_id=channel_id,
                    photo=post.single_media['file_id'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            elif post.media_type == "video":
                await self.app.bot.send_video(
                    chat_id=channel_id,
                    video=post.single_media['file_id'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            elif post.media_type == "voice":
                await self.app.bot.send_voice(
                    chat_id=channel_id,
                    voice=post.single_media['file_id'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            elif post.media_type == "audio":
                await self.app.bot.send_audio(
                    chat_id=channel_id,
                    audio=post.single_media['file_id'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            elif post.media_type == "document":
                await self.app.bot.send_document(
                    chat_id=channel_id,
                    document=post.single_media['file_id'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            elif post.media_type == "media_group":
                # Preparar media group
                media_list = []
                for i, media in enumerate(post.media_group):
                    caption = text if i == 0 else ""
                    
                    if media['type'] == 'photo':
                        media_list.append(InputMediaPhoto(media['file_id'], caption=caption))
                    elif media['type'] == 'video':
                        media_list.append(InputMediaVideo(media['file_id'], caption=caption))
                    elif media['type'] == 'document':
                        media_list.append(InputMediaDocument(media['file_id'], caption=caption))
                
                await self.app.bot.send_media_group(chat_id=channel_id, media=media_list)
                
                # Enviar botones por separado si los hay
                if reply_markup:
                    await self.app.bot.send_message(
                        chat_id=channel_id,
                        text="👆 Interactúa con los botones:",
                        reply_markup=reply_markup
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"Error enviando contenido a {channel_id}: {e}")
            return False
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja fotos enviadas"""
        user_id = update.effective_user.id
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        
        if user_states[user_id].get('step') == 'adding_channel':
            # No es una foto, es texto para canal
            await self._process_channel_addition(update, update.message.caption or "")
            return
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(photo.file_id, "photo", caption)
            
            await update.message.reply_text(
                f"📸 **Imagen añadida** ({len(current_post.media_group) + (1 if current_post.single_media else 0)})\n"
                f"Caption: {caption[:50]}..." if caption else "📸 **Imagen añadida**",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja videos enviados"""
        user_id = update.effective_user.id
        video = update.message.video
        caption = update.message.caption or ""
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(video.file_id, "video", caption)
            
            duration = f"{video.duration}s" if video.duration else ""
            await update.message.reply_text(
                f"🎥 **Video añadido** {duration}\n"
                f"Caption: {caption[:50]}..." if caption else f"🎥 **Video añadido** {duration}",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja notas de voz"""
        user_id = update.effective_user.id
        voice = update.message.voice
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(voice.file_id, "voice", "")
            
            duration = f"{voice.duration}s" if voice.duration else ""
            await update.message.reply_text(
                f"🔊 **Nota de voz añadida** {duration}",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_video_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja video mensajes circulares"""
        user_id = update.effective_user.id
        video_note = update.message.video_note
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(video_note.file_id, "video_note", "")
            
            await update.message.reply_text(
                "📹 **Video mensaje añadido**",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja archivos de audio"""
        user_id = update.effective_user.id
        audio = update.message.audio
        caption = update.message.caption or ""
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(audio.file_id, "audio", caption)
            
            title = audio.title or "Audio"
            duration = f"{audio.duration}s" if audio.duration else ""
            await update.message.reply_text(
                f"🎵 **Audio añadido:** {title} {duration}",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja documentos y archivos"""
        user_id = update.effective_user.id
        document = update.message.document
        caption = update.message.caption or ""
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(document.file_id, "document", caption)
            
            file_name = document.file_name or "Documento"
            file_size = self._format_file_size(document.file_size) if document.file_size else ""
            await update.message.reply_text(
                f"📎 **Archivo añadido:** {file_name} {file_size}",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_sticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja stickers"""
        user_id = update.effective_user.id
        sticker = update.message.sticker
        
        current_post = self._get_current_post(user_id)
        if current_post:
            current_post.add_media(sticker.file_id, "sticker", "")
            
            await update.message.reply_text(
                f"😊 **Sticker añadido:** {sticker.emoji or ''}",
                reply_markup=self._get_multi_post_keyboard()
            )
        else:
            await self._prompt_new_post(update)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja mensajes de texto"""
        user_id = update.effective_user.id
        text = update.message.text
        
        # Manejar botones del teclado principal
        if text == "📝 Nueva Publicación":
            await self.new_post(update, context)
            return
        elif text == "📺 Mis Canales":
            await self.manage_channels(update, context)
            return
        elif text == "📅 Programar Envío":
            await self.schedule_post(update, context)
            return
        elif text == "❓ Ayuda":
            await self.help_command(update, context)
            return
        
        user_step = user_states[user_id].get('step', 'idle')
        
        # Proceso de añadir canal
        if user_step == 'adding_channel':
            await self._process_channel_addition(update, text)
            return
        
        # Proceso de personalizar texto por canal
        if user_step.startswith('customizing_'):
            channel_id = user_step.replace('customizing_', '')
            await self._process_channel_customization(update, channel_id, text)
            return
        
        current_post = self._get_current_post(user_id)
        
        if current_post and user_step in ['adding_text', 'creating']:
            if user_step == 'adding_buttons':
                # Parsear botones
                buttons_added = self._parse_buttons(text, current_post)
                await update.message.reply_text(
                    f"✅ **{buttons_added} botón(es) añadido(s)**",
                    reply_markup=self._get_multi_post_keyboard()
                )
            else:
                # Añadir texto a la publicación
                current_post.text = text
                user_states[user_id]['step'] = 'creating'
                
                await update.message.reply_text(
                    f"📝 **Texto añadido:**\n\n{text[:100]}{'...' if len(text) > 100 else ''}",
                    reply_markup=self._get_multi_post_keyboard()
                )
        else:
            await self._prompt_new_post(update)
    
    async def _process_channel_addition(self, update: Update, text: str):
        """Procesa la adición de un nuevo canal"""
        user_id = update.effective_user.id
        
        # Limpiar el texto del canal
        channel_text = text.strip()
        if channel_text.startswith('https://t.me/'):
            channel_text = channel_text.replace('https://t.me/', '@')
        
        # Añadir canal
        result = await self.channel_manager.add_channel(user_id, channel_text)
        
        if result['success']:
            channel = result['channel']
            user_states[user_id]['step'] = 'idle'
            
            keyboard = [
                [InlineKeyboardButton("📺 Ver Todos los Canales", callback_data="view_all_channels")],
                [InlineKeyboardButton("➕ Añadir Otro Canal", callback_data="add_channel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ **Canal añadido exitosamente**\n\n"
                f"📢 **{channel['title']}**\n"
                f"👥 {channel['member_count']} miembros\n"
                f"🆔 `{channel['id']}`\n"
                f"🔗 @{channel['username']}" if channel['username'] else "",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"❌ **Error al añadir canal:**\n\n"
                f"{result['error']}\n\n"
                "**Verifica que:**\n"
                "• El bot sea administrador del canal\n"
                "• Tenga permisos para publicar\n"
                "• El identificador sea correcto\n\n"
                "Intenta de nuevo o envía /canales para ver la guía."
            )
    
    async def _process_channel_customization(self, update: Update, channel_id: str, text: str):
        """Procesa la personalización de texto para un canal específico"""
        user_id = update.effective_user.id
        current_post = self._get_current_post(user_id)
        
        if current_post:
            current_post.custom_texts[channel_id] = text
            user_states[user_id]['step'] = 'creating'
            
            # Obtener nombre del canal
            channels = await self.channel_manager.get_user_channels(user_id)
            channel_name = next((ch['title'] for ch in channels if ch['id'] == channel_id), f"Canal {channel_id}")
            
            await update.message.reply_text(
                f"✅ **Texto personalizado guardado**\n\n"
                f"📢 **Canal:** {channel_name}\n"
                f"📝 **Texto:** {text[:100]}{'...' if len(text) > 100 else ''}",
                reply_markup=self._get_multi_post_keyboard()
            )
    
    async def _handle_add_text(self, query, user_id: int):
        """Maneja la adición de texto general"""
        user_states[user_id]['step'] = 'adding_text'
        await query.edit_message_text(
            "✍️ **Escribir Texto General**\n\n"
            "Envía el texto que se usará en todos los canales.\n\n"
            "**Formatos disponibles:**\n"
            "• **negrita** o *cursiva*\n"
            "• `código` o ```bloque```\n"
            "• [enlace](https://ejemplo.com)\n"
            "• __subrayado__ o ~~tachado~~\n\n"
            "💡 **Tip:** Después puedes personalizar el texto para canales específicos."
        )
    
    async def _handle_add_buttons(self, query, user_id: int):
        """Maneja la adición de botones"""
        user_states[user_id]['step'] = 'adding_buttons'
        await query.edit_message_text(
            "🔘 **Añadir Botones Interactivos**\n\n"
            "Formato: `Texto del botón | URL o callback`\n\n"
            "**Ejemplos:**\n"
            "• `Mi Web | https://ejemplo.com`\n"
            "• `Canal Principal | https://t.me/mi_canal`\n"
            "• `Contacto | callback_contacto`\n"
            "• `Suscribirse | https://t.me/+enlace_privado`\n\n"
            "**Un botón por línea.** Los botones aparecerán en todos los canales."
        )
    
    async def _handle_customize_channels(self, query, user_id: int):
        """Maneja la personalización por canal"""
        current_post = self._get_current_post(user_id)
        if not current_post or not current_post.target_channels:
            await query.edit_message_text(
                "❌ Primero selecciona los canales de destino."
            )
            return
        
        channels = await self.channel_manager.get_user_channels(user_id)
        channel_dict = {ch['id']: ch for ch in channels}
        
        keyboard = []
        for channel_id in current_post.target_channels:
            channel = channel_dict.get(channel_id, {})
            channel_name = channel.get('title', f'Canal {channel_id}')
            
            has_custom = channel_id in current_post.custom_texts
            icon = "🎨" if has_custom else "📝"
            
            keyboard.append([InlineKeyboardButton(
                f"{icon} {channel_name}",
                callback_data=f"customize_{channel_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("◀️ Volver", callback_data="back_to_main")])
        
        await query.edit_message_text(
            "🎨 **Personalizar Contenido por Canal**\n\n"
            "Selecciona un canal para personalizar su contenido:\n\n"
            "📝 = Usando texto general\n"
            "🎨 = Texto personalizado\n\n"
            "💡 **Útil para:** Adaptar el mensaje a cada audiencia",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_channel_customization(self, query, user_id: int, data: str):
        """Maneja la personalización de un canal específico"""
        channel_id = data.replace("customize_", "")
        user_states[user_id]['step'] = f'customizing_{channel_id}'
        
        # Obtener información del canal
        channels = await self.channel_manager.get_user_channels(user_id)
        channel_name = next((ch['title'] for ch in channels if ch['id'] == channel_id), f"Canal {channel_id}")
        
        current_post = self._get_current_post(user_id)
        current_text = current_post.custom_texts.get(channel_id, current_post.text) if current_post else ""
        
        await query.edit_message_text(
            f"🎨 **Personalizar: {channel_name}**\n\n"
            f"**Texto actual:**\n{current_text[:200]}{'...' if len(current_text) > 200 else ''}\n\n"
            "**Envía el nuevo texto personalizado** para este canal específico.\n\n"
            "Este texto solo se usará en este canal, mientras que otros canales usarán el texto general.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_preview_multi(self, query, user_id: int):
        """Muestra vista previa multi-canal"""
        current_post = self._get_current_post(user_id)
        if not current_post:
            await query.edit_message_text("❌ No hay publicación activa.")
            return
        
        if not current_post.target_channels:
            await query.edit_message_text("❌ No has seleccionado canales de destino.")
            return
        
        channels = await self.channel_manager.get_user_channels(user_id)
        channel_dict = {ch['id']: ch for ch in channels}
        
        # Crear resumen detallado
        preview_text = "👀 **VISTA PREVIA MULTI-CANAL**\n\n"
        
        # Contenido general
        media_count = len(current_post.media_group) + (1 if current_post.single_media else 0)
        if media_count > 0:
            preview_text += f"📎 **Multimedia:** {media_count} archivo(s)\n"
        
        if current_post.buttons:
            preview_text += f"🔘 **Botones:** {len(current_post.buttons)}\n"
        
        # Canales de destino
        total_reach = 0
        preview_text += f"\n🎯 **Canales de destino ({len(current_post.target_channels)}):**\n"
        
        for channel_id in current_post.target_channels:
            channel = channel_dict.get(channel_id, {})
            channel_name = channel.get('title', f'Canal {channel_id}')
            member_count = channel.get('member_count', 0)
            total_reach += member_count
            
            has_custom = channel_id in current_post.custom_texts
            custom_icon = " 🎨" if has_custom else ""
            
            preview_text += f"• {channel_name} ({member_count:,}){custom_icon}\n"
        
        preview_text += f"\n👥 **Alcance total:** {total_reach:,} personas\n"
        
        # Mostrar textos
        if current_post.text:
            preview_text += f"\n📝 **Texto general:**\n{current_post.text[:150]}{'...' if len(current_post.text) > 150 else ''}\n"
        
        if current_post.custom_texts:
            preview_text += f"\n🎨 **Textos personalizados:** {len(current_post.custom_texts)}\n"
        
        keyboard = [
            [InlineKeyboardButton("📤 Publicar Ahora", callback_data="send_now")],
            [InlineKeyboardButton("📅 Programar", callback_data="schedule_post")],
            [InlineKeyboardButton("✏️ Editar", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_confirm_channels(self, query, user_id: int):
        """Confirma la selección de canales"""
        current_post = self._get_current_post(user_id)
        if not current_post:
            return
        
        if not current_post.target_channels:
            await query.edit_message_text("❌ Debes seleccionar al menos un canal.")
            return
        
        channels = await self.channel_manager.get_user_channels(user_id)
        channel_dict = {ch['id']: ch for ch in channels}
        total_reach = sum(channel_dict.get(ch_id, {}).get('member_count', 0) for ch_id in current_post.target_channels)
        
        await query.edit_message_text(
            f"✅ **Canales seleccionados:** {len(current_post.target_channels)}\n"
            f"👥 **Alcance total:** {total_reach:,} personas\n\n"
            "¿Qué quieres hacer ahora?",
            reply_markup=self._get_multi_post_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    def _get_multi_post_keyboard(self):
        """Teclado para publicaciones multi-canal"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📝 Editar Texto", callback_data="add_text"),
             InlineKeyboardButton("🔘 Añadir Botones", callback_data="add_buttons")],
            [InlineKeyboardButton("🎨 Personalizar por Canal", callback_data="customize_channels")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview_multi"),
             InlineKeyboardButton("📤 Publicar", callback_data="send_now")],
            [InlineKeyboardButton("🗑️ Limpiar", callback_data="clear_post")]
        ])
    
    def _get_current_post(self, user_id: int) -> Optional[MediaPost]:
        """Obtiene la publicación actual del usuario"""
        if user_id not in user_states or user_id not in user_posts:
            return None
        
        current_post_id = user_states[user_id].get('current_post')
        if current_post_id and current_post_id in user_posts[user_id]:
            return user_posts[user_id][current_post_id]
        
        return None
    
    def _clear_user_post(self, user_id: int):
        """Elimina todos los datos de la publicación actual"""
        if user_id in user_states and user_states[user_id]['current_post']:
            post_id = user_states[user_id]['current_post']
            if user_id in user_posts and post_id in user_posts[user_id]:
                del user_posts[user_id][post_id]
            user_states[user_id] = {'current_post': None, 'step': 'idle'}
    
    def _parse_buttons(self, text: str, post: MediaPost) -> int:
        """Parsea botones desde texto"""
        lines = text.strip().split('\n')
        buttons_added = 0
        
        for line in lines:
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    button_text = parts[0].strip()
                    button_data = parts[1].strip()
                    
                    post.buttons.append({
                        'text': button_text,
                        'data': button_data
                    })
                    buttons_added += 1
        
        return buttons_added
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Formatea el tamaño de archivo"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f}KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f}MB"
        else:
            return f"{size_bytes/(1024**3):.1f}GB"
    
    async def _prompt_new_post(self, update: Update):
        """Sugiere crear una nueva publicación"""
        keyboard = [[InlineKeyboardButton("📝 Crear Nueva Publicación", callback_data="new_post_quick")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💡 **No tienes una publicación activa**\n\n"
            "Crea una nueva publicación para añadir contenido:",
            reply_markup=reply_markup
        )
    
    async def schedule_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Función para programar publicaciones (implementación futura)"""
        await update.message.reply_text(
            "📅 **Programación de Publicaciones**\n\n"
            "🚧 **Funcionalidad en desarrollo...**\n\n"
            "**Próximamente podrás:**\n"
            "• Programar envíos automáticos\n"
            "• Diferentes horarios por canal\n"
            "• Repetición automática\n"
            "• Optimización de horarios\n"
            "• Cola de publicaciones\n\n"
            "Mientras tanto, usa **'Publicar Ahora'** para envío inmediato."
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de ayuda completo para multi-canal"""
        help_text = """
🚀 **Bot Publicador Multi-Canal - Guía Completa**

**🎯 PUBLICACIÓN MULTI-CANAL:**
• Publica simultáneamente en múltiples canales
• Personaliza contenido por canal específico
• Vista previa con alcance total
• Gestión centralizada de canales

**📺 GESTIÓN DE CANALES:**
• Añadir canales: `/canales`
• Verificación automática de permisos
• Estadísticas de alcance
• Detección de canales inválidos

**📱 MULTIMEDIA SOPORTADO:**
• 📸 Imágenes (individuales/álbumes)
• 🎥 Videos, GIFs, video mensajes
• 🔊 Audio, notas de voz
• 📎 Documentos, PDFs
• 😊 Stickers

**🔘 BOTONES INTERACTIVOS:**
• 🌐 Enlaces web
• 📱 Canales/grupos
• ⚡ Callbacks personalizados
• 📞 Contacto

**🎨 PERSONALIZACIÓN:**
• Texto diferente por canal
• Botones globales
• Formato Markdown/HTML
• Vista previa detallada

**📊 ESTADÍSTICAS:**
• Alcance total por publicación
• Éxito/error por canal
• Conteo de miembros
• Rendimiento de canales

**🚀 COMANDOS PRINCIPALES:**
• `/nueva` - Nueva publicación multi-canal
• `/canales` - Gestionar canales
• `/programar` - Programar envíos (próximamente)

**💡 FLUJO RECOMENDADO:**
1. Configura tus canales (`/canales`)
2. Crea nueva publicación (`/nueva`)
3. Selecciona canales objetivo
4. Añade contenido (texto, media, botones)
5. Personaliza por canal (opcional)
6. Vista previa y publica

**🔧 CONFIGURACIÓN DE CANALES:**
Para que funcione correctamente:
• Añade el bot como administrador
• Dale permisos de "Publicar mensajes"
• Verifica que tengas permisos de administrador
• Usa: @canal, t.me/canal, o ID numérico
        """
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    def run(self):
        """Ejecuta el bot"""
        print("🚀 Bot Publicador Multi-Canal iniciado...")
        print("📺 Funciones: Múltiples canales, personalización, multimedia")
        print("🎯 Publicación simultánea con alcance masivo")
        print("⭐ Presiona Ctrl+C para detener.")
        self.app.run_polling()

# Función principal
def main():
    """Función principal para ejecutar el bot"""
    if BOT_TOKEN == "TU_TOKEN_AQUI":
        print("❌ ERROR: Configura tu token de bot")
        print("1. Habla con @BotFather en Telegram")
        print("2. Crea un nuevo bot con /newbot")
        print("3. Establece la variable de entorno BOT_TOKEN")
        print("   export BOT_TOKEN='tu_token_aqui'")
        return
    
    bot = TelegramPublisher()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Bot Multi-Canal detenido correctamente.")
    except Exception as e:
        logger.error(f"Error crítico: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()