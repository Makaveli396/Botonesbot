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
from telegram.error import TelegramError, Forbidden, BadRequest

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
        self.media_group = []  # Para álbumes de fotos
        
    def add_media(self, file_id, media_type, caption=None):
        self.media.append({
            'file_id': file_id, 
            'type': media_type,
            'caption': caption
        })
    
    def has_content(self):
        return bool(self.text or self.media)

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
        self.app.add_handler(CommandHandler("estado", self.status))
        self.app.add_handler(CommandHandler("cancelar", self.cancel))
        
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Manejadores de multimedia
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        self.app.add_handler(MessageHandler(filters.ANIMATION, self.handle_animation))
        self.app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    def get_user_data(self, user_id):
        """Obtiene datos del usuario"""
        if user_id not in user_data:
            user_data[user_id] = {
                'current_post': None,
                'step': 'idle',
                'channels': {},
                'last_activity': datetime.now()
            }
        user_data[user_id]['last_activity'] = datetime.now()
        return user_data[user_id]
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user = update.effective_user
        self.get_user_data(user.id)
        
        text = f"""🚀 **Bot Publicador Multi-Canal**

¡Hola {user.first_name}! 👋

**FUNCIONES PRINCIPALES:**
• 📝 Crear publicaciones multimedia
• 📺 Gestionar múltiples canales
• 🎯 Publicar simultáneamente
• 📊 Ver estado de publicaciones

**COMANDOS RÁPIDOS:**
• /nueva - Nueva publicación
• /canales - Gestionar canales
• /estado - Ver estado actual
• /cancelar - Cancelar acción
• /help - Ayuda completa

¡Empezamos! 🎉"""
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("📊 Estado"), KeyboardButton("❓ Ayuda")]
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
                "❌ **No tienes canales configurados**\n\n"
                "Primero necesitas añadir canales donde publicar.\n"
                "Haz clic en el botón para empezar.",
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
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish"), 
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await update.message.reply_text(
            f"🎯 **Nueva Publicación**\n\n"
            f"📺 Canales disponibles: **{len(data['channels'])}**\n"
            f"📋 Estado: **Creando**\n\n"
            f"**Siguiente paso:** Selecciona canales y añade contenido",
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

❌ No tienes canales configurados.

**Para añadir un canal:**
1. Añade el bot como administrador
2. Dale permisos de publicación
3. Usa el botón para añadir

**Formatos aceptados:**
• @nombre_canal
• https://t.me/nombre_canal
• -100xxxxxxxxx (ID numérico)"""
        else:
            keyboard = [
                [InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")],
                [InlineKeyboardButton("🗑️ Eliminar Canal", callback_data="remove_channel")]
            ]
            
            text = f"📺 **Tus Canales** ({len(data['channels'])})\n\n"
            
            for i, (ch_id, ch_info) in enumerate(list(data['channels'].items())[:10], 1):
                title = ch_info.get('title', 'Canal sin nombre')
                username = ch_info.get('username', '')
                if username:
                    text += f"{i}. **{title}** (@{username})\n"
                else:
                    text += f"{i}. **{title}**\n"
            
            if len(data['channels']) > 10:
                text += f"\n... y {len(data['channels']) - 10} canales más"
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostrar estado actual"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        text = f"📊 **Estado del Bot**\n\n"
        text += f"👤 Usuario: {update.effective_user.first_name}\n"
        text += f"📺 Canales: **{len(data['channels'])}**\n"
        text += f"🔄 Estado: **{data['step']}**\n"
        
        if data.get('current_post'):
            post = data['current_post']
            text += f"\n📝 **Publicación Actual:**\n"
            text += f"• Texto: {'✅' if post.text else '❌'}\n"
            text += f"• Media: **{len(post.media)}** archivos\n"
            text += f"• Canales: **{len(post.target_channels)}** seleccionados\n"
        
        keyboard = []
        if data.get('current_post'):
            keyboard = [
                [InlineKeyboardButton("📝 Continuar", callback_data="continue_post")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancelar acción actual"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        data['current_post'] = None
        data['step'] = 'idle'
        
        await update.message.reply_text("❌ **Acción cancelada**\n\nPuedes empezar de nuevo cuando quieras.")
    
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

**Instrucciones paso a paso:**

1️⃣ **Añade el bot** como administrador al canal
2️⃣ **Otorga permisos** de publicación de mensajes
3️⃣ **Envía** el identificador del canal

**Formatos válidos:**
• `@nombre_canal`
• `https://t.me/nombre_canal`
• `-100xxxxxxxxx` (ID numérico)

📝 **Envía ahora el identificador:**""",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif callback_data == "remove_channel":
            if not data['channels']:
                await query.edit_message_text("❌ No hay canales para eliminar")
                return
            
            keyboard = []
            for ch_id, ch_info in data['channels'].items():
                title = ch_info.get('title', 'Canal')[:20]
                keyboard.append([InlineKeyboardButton(
                    f"🗑️ {title}",
                    callback_data=f"delete_{ch_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="back_to_channels")])
            
            await query.edit_message_text(
                "🗑️ **Eliminar Canal**\n\nSelecciona el canal a eliminar:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif callback_data.startswith("delete_"):
            ch_id = callback_data.replace("delete_", "")
            if ch_id in data['channels']:
                title = data['channels'][ch_id].get('title', 'Canal')
                del data['channels'][ch_id]
                await query.edit_message_text(
                    f"✅ **Canal eliminado**\n\n🗑️ {title}",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        elif callback_data == "select_channels":
            if not data.get('current_post'):
                await query.edit_message_text("❌ No hay publicación activa")
                return
            
            await self.show_channel_selection(query, data)
        
        elif callback_data.startswith("toggle_"):
            ch_id = callback_data.replace("toggle_", "")
            if data.get('current_post'):
                if ch_id in data['current_post'].target_channels:
                    data['current_post'].target_channels.remove(ch_id)
                else:
                    data['current_post'].target_channels.add(ch_id)
                
                await self.show_channel_selection(query, data)
        
        elif callback_data == "add_text":
            data['step'] = 'adding_text'
            await query.edit_message_text(
                "✍️ **Escribir Texto**\n\n"
                "📝 Envía el texto para la publicación.\n"
                "✨ Puedes usar formato **negrita**, *cursiva* y `código`\n\n"
                "Para cancelar, usa /cancelar"
            )
        
        elif callback_data == "preview":
            await self.show_preview(query, data)
        
        elif callback_data == "publish":
            await self.publish_post(query, user_id)
        
        elif callback_data == "cancel":
            data['current_post'] = None
            data['step'] = 'idle'
            await query.edit_message_text("❌ **Publicación cancelada**")
        
        elif callback_data == "continue_post":
            if data.get('current_post'):
                await self.show_post_menu(query, data)
        
        elif callback_data == "back_to_channels":
            await self.manage_channels_callback(query, data)
    
    async def show_channel_selection(self, query, data):
        """Muestra la selección de canales"""
        keyboard = []
        selected_count = len(data['current_post'].target_channels)
        
        for ch_id, ch_info in data['channels'].items():
            selected = ch_id in data['current_post'].target_channels
            icon = "✅" if selected else "⬜"
            title = ch_info.get('title', 'Canal')[:25]
            keyboard.append([InlineKeyboardButton(
                f"{icon} {title}",
                callback_data=f"toggle_{ch_id}"
            )])
        
        keyboard.extend([
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish"), 
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ])
        
        text = f"🎯 **Seleccionar Canales**\n\n" \
               f"✅ Seleccionados: **{selected_count}**\n" \
               f"📺 Disponibles: **{len(data['channels'])}**\n\n" \
               f"Toca los canales para seleccionar/deseleccionar"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_preview(self, query, data):
        """Muestra vista previa de la publicación"""
        post = data.get('current_post')
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        text = "👀 **Vista Previa**\n\n"
        
        if post.text:
            text += f"📝 **Texto:**\n{post.text[:200]}"
            if len(post.text) > 200:
                text += "..."
            text += "\n\n"
        
        if post.media:
            text += f"🎭 **Media:** {len(post.media)} archivo(s)\n"
            for i, media in enumerate(post.media[:3], 1):
                media_type = media['type']
                emoji = {'photo': '📸', 'video': '🎥', 'document': '📎'}.get(media_type, '📄')
                text += f"{i}. {emoji} {media_type.title()}\n"
            if len(post.media) > 3:
                text += f"... y {len(post.media) - 3} más\n"
            text += "\n"
        
        if post.target_channels:
            text += f"🎯 **Canales:** {len(post.target_channels)} seleccionados\n"
            for ch_id in list(post.target_channels)[:3]:
                ch_title = data['channels'][ch_id].get('title', 'Canal')
                text += f"• {ch_title}\n"
            if len(post.target_channels) > 3:
                text += f"... y {len(post.target_channels) - 3} más\n"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📝 Editar Texto", callback_data="add_text")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish"), 
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_post_menu(self, query, data):
        """Muestra menú de publicación"""
        post = data['current_post']
        
        status_text = "🎯 **Publicación en Progreso**\n\n"
        status_text += f"📝 Texto: {'✅' if post.text else '❌'}\n"
        status_text += f"🎭 Media: **{len(post.media)}** archivos\n"
        status_text += f"🎯 Canales: **{len(post.target_channels)}** seleccionados\n"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📝 Añadir Texto", callback_data="add_text")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish"), 
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            status_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def manage_channels_callback(self, query, data):
        """Callback para gestión de canales"""
        if not data['channels']:
            keyboard = [[InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")]]
            text = "📺 **Gestión de Canales**\n\n❌ No tienes canales configurados."
        else:
            keyboard = [
                [InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")],
                [InlineKeyboardButton("🗑️ Eliminar Canal", callback_data="remove_channel")]
            ]
            text = f"📺 **Tus Canales** ({len(data['channels'])})"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def publish_post(self, query, user_id):
        """Publica la publicación en los canales"""
        data = self.get_user_data(user_id)
        post = data.get('current_post')
        
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        if not post.target_channels:
            await query.edit_message_text("❌ Selecciona al menos un canal")
            return
        
        if not post.has_content():
            await query.edit_message_text("❌ La publicación está vacía. Añade texto o multimedia.")
            return
        
        # Mostrar progreso
        await query.edit_message_text("🚀 **Publicando...**\n\n⏳ Enviando a los canales...")
        
        # Publicar
        results = []
        total_channels = len(post.target_channels)
        success_count = 0
        
        for i, ch_id in enumerate(post.target_channels, 1):
            try:
                channel_info = data['channels'][ch_id]
                channel_name = channel_info.get('title', 'Canal')
                
                # Actualizar progreso
                if i % 2 == 0 or i == total_channels:  # Actualizar cada 2 canales o al final
                    progress_text = f"🚀 **Publicando...** ({i}/{total_channels})\n\n"
                    progress_text += f"📊 Progreso: {int(i/total_channels*100)}%"
                    try:
                        await query.edit_message_text(progress_text, parse_mode=ParseMode.MARKDOWN)
                    except:
                        pass  # Ignorar errores de edición rápida
                
                # Enviar contenido
                if post.media:
                    # Enviar con multimedia
                    media_item = post.media[0]
                    if media_item['type'] == 'photo':
                        await self.app.bot.send_photo(
                            chat_id=ch_id,
                            photo=media_item['file_id'],
                            caption=post.text or "",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'video':
                        await self.app.bot.send_video(
                            chat_id=ch_id,
                            video=media_item['file_id'],
                            caption=post.text or "",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'document':
                        await self.app.bot.send_document(
                            chat_id=ch_id,
                            document=media_item['file_id'],
                            caption=post.text or "",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'animation':
                        await self.app.bot.send_animation(
                            chat_id=ch_id,
                            animation=media_item['file_id'],
                            caption=post.text or "",
                            parse_mode=ParseMode.MARKDOWN
                        )
                else:
                    # Solo texto
                    await self.app.bot.send_message(
                        chat_id=ch_id,
                        text=post.text or "📢 Publicación",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                results.append(f"✅ **{channel_name}**")
                success_count += 1
                
            except Forbidden:
                results.append(f"❌ **{channel_name}**: Sin permisos")
                logger.error(f"Sin permisos en canal {ch_id}")
            except BadRequest as e:
                results.append(f"❌ **{channel_name}**: Error de formato")
                logger.error(f"Error formato en {ch_id}: {e}")
            except Exception as e:
                results.append(f"❌ **{channel_name}**: Error")
                logger.error(f"Error publicando en {ch_id}: {e}")
        
        # Mostrar resultados finales
        result_text = f"📊 **Resultados de Publicación**\n\n"
        result_text += f"✅ **Exitosas:** {success_count}/{total_channels}\n"
        result_text += f"❌ **Fallidas:** {total_channels - success_count}\n\n"
        result_text += "**Detalle:**\n" + "\n".join(results[:10])
        
        if len(results) > 10:
            result_text += f"\n... y {len(results) - 10} más"
        
        # Limpiar datos
        data['current_post'] = None
        data['step'] = 'idle'
        
        keyboard = [[InlineKeyboardButton("📝 Nueva Publicación", callback_data="new_post_quick")]]
        
        await query.edit_message_text(
            result_text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Manejadores de multimedia mejorados
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja fotos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            photo = update.message.photo[-1]  # Mejor calidad
            data['current_post'].add_media(photo.file_id, 'photo')
            
            caption = update.message.caption
            if caption and not data['current_post'].text:
                data['current_post'].text = caption
            
            media_count = len(data['current_post'].media)
            response = f"📸 **Imagen añadida** ({media_count})\n\n"
            
            if caption:
                response += f"📝 Texto detectado: {caption[:50]}..."
            
            keyboard = [
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                response,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja videos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            video = update.message.video
            data['current_post'].add_media(video.file_id, 'video')
            
            caption = update.message.caption
            if caption and not data['current_post'].text:
                data['current_post'].text = caption
            
            duration = video.duration if video.duration else 0
            response = f"🎥 **Video añadido** ({duration}s)\n\n"
            
            keyboard = [
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                response,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def handle_animation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja GIFs/animaciones"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            animation = update.message.animation
            data['current_post'].add_media(animation.file_id, 'animation')
            await update.message.reply_text("🎭 **GIF/Animación añadida**")
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja audio"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            audio = update.message.audio
            data['current_post'].add_media(audio.file_id, 'audio')
            await update.message.reply_text("🎵 **Audio añadido**")
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja notas de voz"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            voice = update.message.voice
            data['current_post'].add_media(voice.file_id, 'voice')
            await update.message.reply_text("🎤 **Nota de voz añadida**")
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja documentos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            document = update.message.document
            file_name = document.file_name or "documento"
            file_size = document.file_size or 0
            
            # Verificar tamaño (límite de Telegram: 50MB)
            if file_size > 50 * 1024 * 1024:
                await update.message.reply_text("❌ **Archivo muy grande** (máximo 50MB)")
                return
            
            data['current_post'].add_media(document.file_id, 'document')
            
            size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
            response = f"📎 **Documento añadido**\n\n"
            response += f"📄 **Nombre:** {file_name}\n"
            if size_mb > 0:
                response += f"📏 **Tamaño:** {size_mb:.1f} MB"
            
            keyboard = [
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                response,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja texto"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        text = update.message.text
        
        # Manejar botones del teclado principal
        if text == "📝 Nueva Publicación":
            await self.new_post(update, context)
            return
        elif text == "📺 Mis Canales":
            await self.manage_channels(update, context)
            return
        elif text == "📊 Estado":
            await self.status(update, context)
            return
        elif text == "❓ Ayuda":
            await self.help_cmd(update, context)
            return
        
        step = data.get('step', 'idle')
        
        if step == 'adding_channel':
            await self.add_channel(update, user_id, text)
        elif step == 'adding_text' and data.get('current_post'):
            # Validar longitud del texto
            if len(text) > 4096:
                await update.message.reply_text(
                    f"❌ **Texto muy largo**\n\n"
                    f"📏 Actual: {len(text)} caracteres\n"
                    f"📏 Máximo: 4096 caracteres\n\n"
                    f"Por favor, acorta el texto."
                )
                return
            
            data['current_post'].text = text
            data['step'] = 'creating'
            
            preview_text = text[:150] + "..." if len(text) > 150 else text
            
            keyboard = [
                [InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                f"📝 **Texto añadido**\n\n"
                f"📄 **Vista previa:**\n{preview_text}\n\n"
                f"📏 **Longitud:** {len(text)} caracteres",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Sugerencias contextuales
            suggestions = [
                "💡 **Comandos disponibles:**",
                "• /nueva - Crear publicación",
                "• /canales - Gestionar canales", 
                "• /estado - Ver estado actual",
                "• /help - Ayuda completa"
            ]
            
            await update.message.reply_text(
                "\n".join(suggestions),
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def add_channel(self, update, user_id, channel_text):
        """Añade un canal con validación mejorada"""
        data = self.get_user_data(user_id)
        
        # Limpiar y normalizar texto
        channel_text = channel_text.strip()
        original_text = channel_text
        
        # Convertir diferentes formatos
        if channel_text.startswith('https://t.me/'):
            channel_text = channel_text.replace('https://t.me/', '@')
        elif channel_text.startswith('t.me/'):
            channel_text = channel_text.replace('t.me/', '@')
        elif not channel_text.startswith('@') and not channel_text.startswith('-'):
            channel_text = f'@{channel_text}'
        
        try:
            # Intentar obtener información del chat
            chat = None
            
            if channel_text.startswith('@'):
                chat = await self.app.bot.get_chat(channel_text)
            elif channel_text.startswith('-'):
                try:
                    chat_id = int(channel_text)
                    chat = await self.app.bot.get_chat(chat_id)
                except ValueError:
                    raise BadRequest("ID de canal inválido")
            
            if not chat:
                raise BadRequest("No se pudo obtener información del canal")
            
            # Verificar que es un canal o supergrupo
            if chat.type not in ['channel', 'supergroup']:
                await update.message.reply_text(
                    f"❌ **Tipo de chat no válido**\n\n"
                    f"🔍 Detectado: {chat.type}\n"
                    f"✅ Requerido: Canal o Supergrupo"
                )
                return
            
            # Verificar permisos del bot
            try:
                bot_member = await self.app.bot.get_chat_member(chat.id, self.app.bot.id)
                if bot_member.status not in ['administrator', 'creator']:
                    await update.message.reply_text(
                        f"❌ **Sin permisos de administrador**\n\n"
                        f"📢 Canal: **{chat.title}**\n"
                        f"🤖 Estado del bot: {bot_member.status}\n\n"
                        f"**Solución:**\n"
                        f"1. Añade el bot como administrador\n"
                        f"2. Otorga permisos de publicación\n"
                        f"3. Intenta de nuevo"
                    )
                    return
                
                # Verificar permisos específicos
                if hasattr(bot_member, 'can_post_messages') and not bot_member.can_post_messages:
                    await update.message.reply_text(
                        f"❌ **Sin permisos de publicación**\n\n"
                        f"📢 Canal: **{chat.title}**\n\n"
                        f"El bot necesita permisos para:\n"
                        f"• Publicar mensajes\n"
                        f"• Editar mensajes del canal"
                    )
                    return
                    
            except BadRequest:
                await update.message.reply_text(
                    f"❌ **No se puede verificar permisos**\n\n"
                    f"📢 Canal: **{chat.title}**\n\n"
                    f"Asegúrate de que:\n"
                    f"• El bot es administrador\n"
                    f"• Tiene permisos de publicación"
                )
                return
            
            # Verificar si ya existe
            if str(chat.id) in data['channels']:
                await update.message.reply_text(
                    f"⚠️ **Canal ya configurado**\n\n"
                    f"📢 {chat.title}"
                )
                return
            
            # Guardar canal
            data['channels'][str(chat.id)] = {
                'title': chat.title,
                'username': chat.username,
                'type': chat.type,
                'description': getattr(chat, 'description', ''),
                'member_count': getattr(chat, 'member_count', None),
                'added_date': datetime.now().isoformat()
            }
            
            data['step'] = 'idle'
            
            # Respuesta de éxito con detalles
            response = f"✅ **Canal añadido exitosamente**\n\n"
            response += f"📢 **Nombre:** {chat.title}\n"
            if chat.username:
                response += f"🔗 **Username:** @{chat.username}\n"
            response += f"📊 **Tipo:** {chat.type.title()}\n"
            if hasattr(chat, 'member_count') and chat.member_count:
                response += f"👥 **Miembros:** {chat.member_count:,}\n"
            
            response += f"\n📈 **Total de canales:** {len(data['channels'])}"
            
            keyboard = [
                [InlineKeyboardButton("📝 Nueva Publicación", callback_data="new_post_quick")],
                [InlineKeyboardButton("➕ Añadir Otro Canal", callback_data="add_channel")]
            ]
            
            await update.message.reply_text(
                response,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Forbidden:
            await update.message.reply_text(
                f"❌ **Acceso denegado**\n\n"
                f"🔍 Canal: `{original_text}`\n\n"
                f"**Posibles causas:**\n"
                f"• Canal privado sin acceso\n"
                f"• Bot bloqueado en el canal\n"
                f"• Canal no existe\n\n"
                f"**Solución:**\n"
                f"• Verifica que el canal existe\n"
                f"• Añade el bot como administrador"
            )
        except BadRequest as e:
            error_msg = str(e).lower()
            if "chat not found" in error_msg:
                await update.message.reply_text(
                    f"❌ **Canal no encontrado**\n\n"
                    f"🔍 Buscado: `{original_text}`\n\n"
                    f"**Verifica:**\n"
                    f"• El nombre es correcto\n"
                    f"• El canal existe\n"
                    f"• Tienes acceso al canal"
                )
            elif "invalid" in error_msg:
                await update.message.reply_text(
                    f"❌ **Formato inválido**\n\n"
                    f"🔍 Recibido: `{original_text}`\n\n"
                    f"**Formatos válidos:**\n"
                    f"• `@nombre_canal`\n"
                    f"• `https://t.me/nombre_canal`\n"
                    f"• `-100xxxxxxxxx` (ID numérico)"
                )
            else:
                await update.message.reply_text(
                    f"❌ **Error:** {str(e)}\n\n"
                    f"🔍 Canal: `{original_text}`"
                )
        except Exception as e:
            logger.error(f"Error inesperado añadiendo canal {original_text}: {e}")
            await update.message.reply_text(
                f"❌ **Error inesperado**\n\n"
                f"Por favor, intenta de nuevo o contacta al soporte.\n"
                f"Error: `{str(e)[:100]}`"
            )
    
    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de ayuda mejorado"""
        text = """🚀 **Bot Publicador Multi-Canal**

**📋 COMANDOS PRINCIPALES:**
• `/start` - Iniciar el bot
• `/nueva` - Crear nueva publicación
• `/canales` - Gestionar canales
• `/estado` - Ver estado actual
• `/cancelar` - Cancelar acción
• `/help` - Esta ayuda

**🔄 FLUJO DE TRABAJO:**
1️⃣ **Configura canales** (/canales)
   • Añade bot como administrador
   • Otorga permisos de publicación

2️⃣ **Crea publicación** (/nueva)
   • Selecciona canales destino
   • Añade contenido (texto/multimedia)

3️⃣ **Publica** 📤
   • Vista previa opcional
   • Publicación simultánea

**🎭 MULTIMEDIA SOPORTADO:**
• 📸 Imágenes (JPG, PNG, WebP)
• 🎥 Videos (MP4, MOV, AVI)
• 🎭 GIFs y animaciones
• 📎 Documentos (PDF, DOC, etc.)
• 🎵 Audio y notas de voz

**⚙️ CONFIGURACIÓN DE CANALES:**
• **Formatos aceptados:**
  - `@nombre_canal`
  - `https://t.me/nombre_canal`
  - `-100xxxxxxxxx` (ID numérico)

• **Requisitos:**
  - Bot como administrador
  - Permisos de publicación
  - Canal público o con acceso

**💡 CONSEJOS:**
• Usa los botones para navegación rápida
• El texto puede usar formato Markdown
• Máximo 4096 caracteres por mensaje
• Documentos hasta 50MB

**🆘 SOPORTE:**
Si tienes problemas, usa /estado para diagnóstico."""
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("📊 Estado"), KeyboardButton("❓ Ayuda")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )

# Configuración del servidor web (sin cambios)
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
    """Health check mejorado"""
    try:
        # Verificar estado del bot
        bot_info = await bot.app.bot.get_me()
        return Response(
            text=json.dumps({
                "status": "OK",
                "bot_username": bot_info.username,
                "bot_id": bot_info.id,
                "active_users": len(user_data),
                "timestamp": datetime.now().isoformat()
            }),
            content_type="application/json"
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return Response(
            text=json.dumps({"status": "ERROR", "error": str(e)}),
            status=500,
            content_type="application/json"
        )

async def setup_webhook():
    """Configura webhook con reintentos"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            webhook_url = f"{WEBHOOK_URL}/webhook"
            await bot.app.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook configurado: {webhook_url}")
            return
        except Exception as e:
            logger.warning(f"⚠️ Intento {attempt + 1}/{max_retries} fallido: {e}")
            if attempt == max_retries - 1:
                logger.error(f"❌ Error configurando webhook después de {max_retries} intentos")
                raise

async def init_app():
    """Inicializa aplicación con manejo de errores"""
    try:
        await bot.app.initialize()
        await bot.app.start()
        await setup_webhook()
        
        app = web.Application()
        app.router.add_post('/webhook', webhook_handler)
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        app.router.add_get('/status', health_check)  # Alias adicional
        
        logger.info("✅ Aplicación inicializada correctamente")
        return app
        
    except Exception as e:
        logger.error(f"❌ Error inicializando aplicación: {e}")
        raise

# Instancia del bot
bot = TelegramBot()

def main():
    """Función principal con manejo de errores mejorado"""
    import asyncio
    
    try:
        # Configurar loop de eventos
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Inicializar aplicación
        app = loop.run_until_complete(init_app())
        
        # Logs de inicio
        logger.info("🚀" + "="*50)
        logger.info(f"🤖 Bot Publicador Multi-Canal INICIADO")
        logger.info(f"🌐 Puerto: {PORT}")
        logger.info(f"🔗 Webhook: {WEBHOOK_URL}")
        logger.info(f"📊 Memoria: {len(user_data)} usuarios")
        logger.info("🚀" + "="*50)
        
        # Iniciar servidor
        web.run_app(
            app, 
            host='0.0.0.0', 
            port=PORT,
            access_log=logger,
            shutdown_timeout=30
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 Detenido por usuario")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")
        raise
    finally:
        logger.info("🔚 Bot finalizado")

if __name__ == "__main__":
    main()