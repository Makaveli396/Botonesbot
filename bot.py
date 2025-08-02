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

class PostButton:
    """Clase para representar un botón de publicación"""
    def __init__(self, text, url=None, callback_data=None, button_type='url'):
        self.text = text
        self.url = url
        self.callback_data = callback_data
        self.button_type = button_type  # 'url', 'callback', 'inline_query'
    
    def to_telegram_button(self):
        """Convierte a botón de Telegram"""
        if self.button_type == 'url' and self.url:
            return InlineKeyboardButton(self.text, url=self.url)
        elif self.button_type == 'callback' and self.callback_data:
            return InlineKeyboardButton(self.text, callback_data=self.callback_data)
        else:
            return InlineKeyboardButton(self.text, url=self.url or "https://t.me")

class MediaPost:
    def __init__(self):
        self.text = ""
        self.media = []
        self.target_channels = set()
        self.buttons = []  # Lista de botones
        self.button_layout = "horizontal"  # "horizontal", "vertical", "grid"
        
    def add_media(self, file_id, media_type, caption=None):
        self.media.append({
            'file_id': file_id, 
            'type': media_type,
            'caption': caption
        })
    
    def add_button(self, text, url=None, callback_data=None, button_type='url'):
        """Añade un botón a la publicación"""
        button = PostButton(text, url, callback_data, button_type)
        self.buttons.append(button)
    
    def remove_button(self, index):
        """Elimina un botón por índice"""
        if 0 <= index < len(self.buttons):
            self.buttons.pop(index)
    
    def get_inline_keyboard(self):
        """Genera el teclado inline para la publicación"""
        if not self.buttons:
            return None
        
        keyboard = []
        
        if self.button_layout == "horizontal":
            # Todos los botones en una fila (máximo 3 por fila)
            row = []
            for i, button in enumerate(self.buttons):
                row.append(button.to_telegram_button())
                if len(row) == 3 or i == len(self.buttons) - 1:
                    keyboard.append(row)
                    row = []
                    
        elif self.button_layout == "vertical":
            # Un botón por fila
            for button in self.buttons:
                keyboard.append([button.to_telegram_button()])
                
        elif self.button_layout == "grid":
            # Grid 2x2 o 2xN
            row = []
            for i, button in enumerate(self.buttons):
                row.append(button.to_telegram_button())
                if len(row) == 2 or i == len(self.buttons) - 1:
                    keyboard.append(row)
                    row = []
        
        return InlineKeyboardMarkup(keyboard) if keyboard else None
    
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
                'last_activity': datetime.now(),
                'button_templates': self.get_default_button_templates()
            }
        user_data[user_id]['last_activity'] = datetime.now()
        return user_data[user_id]
    
    def get_default_button_templates(self):
        """Plantillas de botones predefinidas"""
        return {
            'ecommerce': [
                {'text': '🛒 Comprar Ahora', 'url': 'https://ejemplo.com/producto'},
                {'text': '📞 Contactar', 'url': 'https://wa.me/1234567890'},
                {'text': '⭐ Valorar', 'url': 'https://ejemplo.com/review'}
            ],
            'social': [
                {'text': '👍 Like', 'callback_data': 'like_post'},
                {'text': '💬 Comentar', 'url': 'https://t.me/mi_canal'},
                {'text': '🔄 Compartir', 'callback_data': 'share_post'}
            ],
            'educational': [
                {'text': '📚 Ver Curso', 'url': 'https://ejemplo.com/curso'},
                {'text': '🎓 Inscribirse', 'url': 'https://ejemplo.com/registro'},
                {'text': '💬 Preguntas', 'url': 'https://t.me/soporte'}
            ],
            'news': [
                {'text': '📖 Leer Más', 'url': 'https://ejemplo.com/noticia'},
                {'text': '🔔 Suscribirse', 'url': 'https://t.me/noticias'},
                {'text': '📤 Compartir', 'callback_data': 'share_news'}
            ]
        }
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user = update.effective_user
        self.get_user_data(user.id)
        
        text = f"""🚀 **Bot Publicador Multi-Canal con Botones**

¡Hola {user.first_name}! 👋

**FUNCIONES PRINCIPALES:**
• 📝 Crear publicaciones multimedia
• 🔘 Añadir botones interactivos
• 📺 Gestionar múltiples canales
• 🎯 Publicar simultáneamente

**TIPOS DE BOTONES:**
• 🔗 Links externos
• 📞 WhatsApp/Telegram
• 🛒 Tiendas online
• 📊 Encuestas y formularios

**COMANDOS:**
• /nueva - Nueva publicación
• /canales - Gestionar canales
• /help - Ayuda completa

¡Crea contenido interactivo! 🎉"""
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("🔘 Plantillas de Botones"), KeyboardButton("❓ Ayuda")]
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
            [InlineKeyboardButton("📝 Añadir Texto", callback_data="add_text"),
             InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("🔘 Gestionar Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview"),
             InlineKeyboardButton("📤 Publicar", callback_data="publish")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await update.message.reply_text(
            f"🎯 **Nueva Publicación con Botones**\n\n"
            f"📺 Canales disponibles: **{len(data['channels'])}**\n"
            f"🔘 Botones: **0**\n"
            f"📋 Estado: **Creando**\n\n"
            f"**Siguiente paso:** Añade contenido y botones",
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
        
        # Gestión de botones
        if callback_data == "manage_buttons":
            await self.show_button_management(query, data)
        elif callback_data == "add_button":
            await self.add_button_menu(query, data)
        elif callback_data == "remove_button":
            await self.remove_button_menu(query, data)
        elif callback_data == "button_layout":
            await self.button_layout_menu(query, data)
        elif callback_data.startswith("layout_"):
            layout = callback_data.replace("layout_", "")
            if data.get('current_post'):
                data['current_post'].button_layout = layout
                await query.edit_message_text(
                    f"✅ **Layout actualizado**: {layout}",
                    parse_mode=ParseMode.MARKDOWN
                )
        elif callback_data.startswith("template_"):
            template_name = callback_data.replace("template_", "")
            await self.apply_button_template(query, data, template_name)
        elif callback_data.startswith("remove_btn_"):
            btn_index = int(callback_data.replace("remove_btn_", ""))
            if data.get('current_post'):
                data['current_post'].remove_button(btn_index)
                await self.show_button_management(query, data)
        
        # Callbacks adicionales para botones
        elif callback_data == "add_url_button":
            data['step'] = 'adding_button_text'
            await query.edit_message_text(
                "➕ **Crear Botón con Link**\n\n"
                "✍️ **Paso 1:** Envía el texto del botón\n\n"
                "**Ejemplos:**\n"
                "• `🛒 Comprar Ahora`\n"
                "• `📞 Contactar`\n"
                "• `📖 Leer Más`\n\n"
                "Para cancelar, usa /cancelar"
            )
        
        elif callback_data == "add_whatsapp_button":
            await query.edit_message_text(
                "📞 **Botón de WhatsApp**\n\n"
                "Envía el número en formato:\n"
                "`https://wa.me/1234567890`\n\n"
                "El bot creará un botón automáticamente."
            )
        
        elif callback_data == "add_telegram_button":
            await query.edit_message_text(
                "📺 **Botón de Telegram**\n\n"
                "Envía el enlace del canal/grupo:\n"
                "• `https://t.me/mi_canal`\n"
                "• `@mi_canal`\n\n"
                "El bot creará el botón automáticamente."
            )
        
        elif callback_data == "button_templates":
            await self.show_button_template_selection(query, data)
        
        elif callback_data == "back_to_post":
            await self.show_post_menu(query, data)
        
        elif callback_data == "new_post_quick":
            # Redirigir a crear nueva publicación
            data['current_post'] = MediaPost()
            data['step'] = 'creating'
            await self.show_post_menu(query, data)
        
        # Resto de callbacks existentes
        elif callback_data == "add_channel":
            data['step'] = 'adding_channel'
            await query.edit_message_text(
                """➕ **Añadir Canal**

**Instrucciones:**
1️⃣ Añade el bot como administrador
2️⃣ Otorga permisos de publicación  
3️⃣ Envía el identificador del canal

**Formatos válidos:**
• `@nombre_canal`
• `https://t.me/nombre_canal`
• `-100xxxxxxxxx`

📝 **Envía el identificador:**""",
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
                "✨ Puedes usar formato **negrita**, *cursiva*\n\n"
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
    
    async def show_button_management(self, query, data):
        """Muestra el menú de gestión de botones"""
        post = data.get('current_post')
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        text = f"🔘 **Gestión de Botones**\n\n"
        text += f"📊 **Botones actuales:** {len(post.buttons)}\n"
        text += f"📐 **Layout:** {post.button_layout}\n\n"
        
        if post.buttons:
            text += "**Botones configurados:**\n"
            for i, button in enumerate(post.buttons, 1):
                icon = "🔗" if button.button_type == 'url' else "⚡"
                text += f"{i}. {icon} {button.text}\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Añadir Botón", callback_data="add_button")],
            [InlineKeyboardButton("📐 Cambiar Layout", callback_data="button_layout")],
            [InlineKeyboardButton("📋 Usar Plantilla", callback_data="button_templates")]
        ]
        
        if post.buttons:
            keyboard.insert(1, [InlineKeyboardButton("🗑️ Quitar Botón", callback_data="remove_button")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="back_to_post")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def add_button_menu(self, query, data):
        """Menú para añadir botón"""
        keyboard = [
            [InlineKeyboardButton("🔗 Botón con Link", callback_data="add_url_button")],
            [InlineKeyboardButton("📞 WhatsApp", callback_data="add_whatsapp_button")],
            [InlineKeyboardButton("📺 Canal/Grupo", callback_data="add_telegram_button")],
            [InlineKeyboardButton("📋 Usar Plantilla", callback_data="button_templates")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="manage_buttons")]
        ]
        
        await query.edit_message_text(
            "➕ **Añadir Botón**\n\n"
            "Selecciona el tipo de botón que quieres añadir:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def button_layout_menu(self, query, data):
        """Menú para cambiar layout de botones"""
        keyboard = [
            [InlineKeyboardButton("↔️ Horizontal", callback_data="layout_horizontal")],
            [InlineKeyboardButton("↕️ Vertical", callback_data="layout_vertical")],
            [InlineKeyboardButton("⬜ Grid 2x2", callback_data="layout_grid")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="manage_buttons")]
        ]
        
        await query.edit_message_text(
            "📐 **Layout de Botones**\n\n"
            "**Horizontal:** Botones en fila (máx 3)\n"
            "**Vertical:** Un botón por fila\n"
            "**Grid:** Botones en cuadrícula 2x2\n\n"
            "Selecciona el layout:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def remove_button_menu(self, query, data):
        """Menú para quitar botones"""
        post = data.get('current_post')
        if not post or not post.buttons:
            await query.edit_message_text("❌ No hay botones para quitar")
            return
        
        keyboard = []
        for i, button in enumerate(post.buttons):
            keyboard.append([InlineKeyboardButton(
                f"🗑️ {button.text[:20]}...",
                callback_data=f"remove_btn_{i}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="manage_buttons")])
        
        await query.edit_message_text(
            "🗑️ **Quitar Botón**\n\nSelecciona el botón a eliminar:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def show_preview(self, query, data):
        """Muestra vista previa con botones"""
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
            text += f"🎭 **Media:** {len(post.media)} archivo(s)\n\n"
        
        if post.buttons:
            text += f"🔘 **Botones:** {len(post.buttons)} ({post.button_layout})\n"
            for i, button in enumerate(post.buttons, 1):
                icon = "🔗" if button.button_type == 'url' else "⚡"
                text += f"{i}. {icon} {button.text}\n"
            text += "\n"
        
        if post.target_channels:
            text += f"🎯 **Canales:** {len(post.target_channels)} seleccionados\n"
        
        # Mostrar cómo se verían los botones
        preview_keyboard = post.get_inline_keyboard()
        
        control_keyboard = [
            [InlineKeyboardButton("🔘 Gestionar Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish"), 
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            text + "\n**⬇️ Vista previa de botones:**",
            reply_markup=InlineKeyboardMarkup(control_keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Enviar mensaje adicional con preview de botones
        if preview_keyboard:
            await query.message.reply_text(
                "📝 **Así se verá tu publicación:**\n\n" + (post.text or "Tu contenido aquí"),
                reply_markup=preview_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def apply_button_template(self, query, data, template_name):
        """Aplica una plantilla de botones"""
        post = data.get('current_post')
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        templates = data.get('button_templates', {})
        if template_name not in templates:
            await query.edit_message_text("❌ Plantilla no encontrada")
            return
        
        # Limpiar botones existentes
        post.buttons = []
        
        # Añadir botones de la plantilla
        for btn_data in templates[template_name]:
            post.add_button(
                text=btn_data['text'],
                url=btn_data.get('url'),
                callback_data=btn_data.get('callback_data'),
                button_type=btn_data.get('button_type', 'url')
            )
        
        await query.edit_message_text(
            f"✅ **Plantilla aplicada: {template_name}**\n\n"
            f"📊 Botones añadidos: {len(post.buttons)}\n\n"
            f"Puedes editarlos individualmente si necesitas.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def publish_post(self, query, user_id):
        """Publica la publicación con botones"""
        data = self.get_user_data(user_id)
        post = data.get('current_post')
        
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        if not post.target_channels:
            await query.edit_message_text("❌ Selecciona al menos un canal")
            return
        
        if not post.has_content():
            await query.edit_message_text("❌ La publicación está vacía")
            return
        
        # Mostrar progreso
        await query.edit_message_text("🚀 **Publicando con botones...**\n\n⏳ Enviando a los canales...")
        
        # Generar teclado de botones
        reply_markup = post.get_inline_keyboard()
        
        # Publicar
        results = []
        success_count = 0
        
        for i, ch_id in enumerate(post.target_channels, 1):
            try:
                channel_info = data['channels'][ch_id]
                channel_name = channel_info.get('title', 'Canal')
                
                # Enviar contenido con botones
                if post.media:
                    media_item = post.media[0]
                    if media_item['type'] == 'photo':
                        await self.app.bot.send_photo(
                            chat_id=ch_id,
                            photo=media_item['file_id'],
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'video':
                        await self.app.bot.send_video(
                            chat_id=ch_id,
                            video=media_item['file_id'],
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'animation':
                        await self.app.bot.send_animation(
                            chat_id=ch_id,
                            animation=media_item['file_id'],
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'audio':
                        await self.app.bot.send_audio(
                            chat_id=ch_id,
                            audio=media_item['file_id'],
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'voice':
                        await self.app.bot.send_voice(
                            chat_id=ch_id,
                            voice=media_item['file_id'],
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_item['type'] == 'document':
                        await self.app.bot.send_document(
                            chat_id=ch_id,
                            document=media_item['file_id'],
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                else:
                    # Solo texto con botones
                    await self.app.bot.send_message(
                        chat_id=ch_id,
                        text=post.text or "📢 Publicación",
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                results.append(f"✅ **{channel_name}** (con {len(post.buttons)} botones)")
                success_count += 1
                
            except Exception as e:
                results.append(f"❌ **{channel_name}**: Error")
                logger.error(f"Error publicando en {ch_id}: {e}")
        
        # Mostrar resultados
        result_text = f"📊 **Resultados de Publicación**\n\n"
        result_text += f"✅ **Exitosas:** {success_count}/{len(post.target_channels)}\n"
        result_text += f"🔘 **Botones por post:** {len(post.buttons)}\n"
        result_text += f"📐 **Layout:** {post.button_layout}\n\n"
        result_text += "**Detalle:**\n" + "\n".join(results[:8])
        
        # Limpiar datos
        data['current_post'] = None
        data['step'] = 'idle'
        
        await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja texto y comandos especiales"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        text = update.message.text
        
        # Botones del teclado principal
        if text == "📝 Nueva Publicación":
            await self.new_post(update, context)
            return
        elif text == "🔘 Plantillas de Botones":
            await self.show_button_templates(update, data)
            return
        elif text == "📺 Mis Canales":
            await self.manage_channels(update, context)
            return
        elif text == "❓ Ayuda":
            await self.help_cmd(update, context)
            return
        
        # Manejar pasos específicos
        step = data.get('step', 'idle')
        
        if step == 'adding_channel':
            await self.add_channel(update, user_id, text)
            return
        
        if step == 'adding_text' and data.get('current_post'):
            if len(text) > 4096:
                await update.message.reply_text(
                    f"❌ **Texto muy largo** ({len(text)}/4096 caracteres)"
                )
                return
            
            data['current_post'].text = text
            data['step'] = 'creating'
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            await update.message.reply_text(
                f"📝 **Texto añadido** ({len(text)} caracteres)\n\n"
                f"💡 **Siguiente:** Añade botones interactivos",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif step.startswith('adding_button_'):
            # Manejar la creación de botones personalizados
            await self.handle_button_creation(update, data, text)
        
        else:
            await update.message.reply_text("💡 Usa los botones del menú principal")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja fotos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            photo = update.message.photo[-1]
            data['current_post'].add_media(photo.file_id, 'photo')
            
            caption = update.message.caption
            if caption and not data['current_post'].text:
                data['current_post'].text = caption
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            await update.message.reply_text(
                f"📸 **Imagen añadida**\n\n"
                f"💡 **Sugerencia:** Añade botones para mayor interacción",
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
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            await update.message.reply_text(
                f"🎥 **Video añadido**\n\n"
                f"💡 **Tip:** Los videos con botones tienen más engagement",
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
            
            caption = update.message.caption
            if caption and not data['current_post'].text:
                data['current_post'].text = caption
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            await update.message.reply_text(
                f"🎭 **GIF/Animación añadida**\n\n"
                f"💡 **Tip:** Los GIFs con botones son muy virales",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja archivos de audio"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            audio = update.message.audio
            data['current_post'].add_media(audio.file_id, 'audio')
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            await update.message.reply_text(
                f"🎵 **Audio añadido**\n\n"
                f"💡 **Idea:** Añade botones para streaming o descarga",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja mensajes de voz"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            voice = update.message.voice
            data['current_post'].add_media(voice.file_id, 'voice')
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            await update.message.reply_text(
                f"🎤 **Mensaje de voz añadido**\n\n"
                f"💡 **Sugerencia:** Perfecto para podcasts con botones",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja documentos/archivos"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        if data.get('current_post'):
            document = update.message.document
            data['current_post'].add_media(document.file_id, 'document')
            
            caption = update.message.caption
            if caption and not data['current_post'].text:
                data['current_post'].text = caption
            
            keyboard = [
                [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")]
            ]
            
            file_name = document.file_name or "archivo"
            await update.message.reply_text(
                f"📄 **Documento añadido**\n\n"
                f"📁 Archivo: `{file_name}`\n"
                f"💡 **Idea:** Añade botones de descarga o más info",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("💡 **Usa /nueva para crear una publicación primero**")
    
    async def show_button_templates(self, update, data):
        """Muestra plantillas de botones disponibles"""
        templates = data.get('button_templates', {})
        
        text = "📋 **Plantillas de Botones**\n\n"
        
        for name, buttons in templates.items():
            text += f"**{name.title()}:**\n"
            for btn in buttons[:2]:  # Mostrar solo los primeros 2
                text += f"• {btn['text']}\n"
            if len(buttons) > 2:
                text += f"• ... y {len(buttons) - 2} más\n"
            text += "\n"
        
        keyboard = []
        for template_name in templates.keys():
            keyboard.append([InlineKeyboardButton(
                f"📋 {template_name.title()}",
                callback_data=f"template_{template_name}"
            )])
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_button_creation(self, update, data, text):
        """Maneja la creación personalizada de botones"""
        step = data.get('step', '')
        post = data.get('current_post')
        
        if not post:
            return
        
        if step == 'adding_button_text':
            # Guardar texto del botón temporalmente
            data['temp_button_text'] = text
            data['step'] = 'adding_button_url'
            await update.message.reply_text(
                f"🔗 **URL del botón**\n\n"
                f"Botón: `{text}`\n\n"
                f"Envía la URL completa:\n"
                f"• https://ejemplo.com\n"
                f"• https://wa.me/1234567890\n"
                f"• https://t.me/canal"
            )
        
        elif step == 'adding_button_url':
            # Crear el botón completo
            button_text = data.get('temp_button_text', 'Botón')
            
            # Validar URL
            if not (text.startswith('http') or text.startswith('https') or text.startswith('tg:')):
                await update.message.reply_text(
                    "❌ **URL inválida**\n\n"
                    "La URL debe empezar con:\n"
                    "• `https://`\n"
                    "• `http://`\n"
                    "• `tg://`"
                )
                return
            
            # Añadir botón a la publicación
            post.add_button(button_text, url=text, button_type='url')
            
            # Limpiar datos temporales
            data['step'] = 'creating'
            data.pop('temp_button_text', None)
            
            keyboard = [
                [InlineKeyboardButton("➕ Otro Botón", callback_data="add_button")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                f"✅ **Botón añadido**\n\n"
                f"🔘 **Texto:** {button_text}\n"
                f"🔗 **URL:** {text}\n\n"
                f"📊 **Total botones:** {len(post.buttons)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
    
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
            [InlineKeyboardButton("🔘 Gestionar Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
            [InlineKeyboardButton("📤 Publicar", callback_data="publish")]
        ])
        
        post = data.get('current_post')
        button_info = f"🔘 Botones: **{len(post.buttons)}**" if post else ""
        
        text = f"🎯 **Seleccionar Canales**\n\n" \
               f"✅ Seleccionados: **{selected_count}**\n" \
               f"📺 Disponibles: **{len(data['channels'])}**\n" \
               f"{button_info}\n\n" \
               f"Toca los canales para seleccionar"
        
        await query.edit_message_text(
            text,
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
3. Usa el botón para añadir"""
        else:
            keyboard = [
                [InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")],
                [InlineKeyboardButton("🗑️ Eliminar Canal", callback_data="remove_channel")]
            ]
            
            text = f"📺 **Tus Canales** ({len(data['channels'])})\n\n"
            
            for i, (ch_id, ch_info) in enumerate(list(data['channels'].items())[:8], 1):
                title = ch_info.get('title', 'Canal sin nombre')
                username = ch_info.get('username', '')
                if username:
                    text += f"{i}. **{title}** (@{username})\n"
                else:
                    text += f"{i}. **{title}**\n"
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def add_channel(self, update, user_id, channel_text):
        """Añade un canal con validación"""
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
            # Obtener información del chat
            if channel_text.startswith('@'):
                chat = await self.app.bot.get_chat(channel_text)
            elif channel_text.startswith('-'):
                chat_id = int(channel_text)
                chat = await self.app.bot.get_chat(chat_id)
            else:
                raise BadRequest("Formato inválido")
            
            # Verificar permisos del bot
            bot_member = await self.app.bot.get_chat_member(chat.id, self.app.bot.id)
            if bot_member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    f"❌ **Sin permisos de administrador**\n\n"
                    f"📢 Canal: **{chat.title}**\n\n"
                    f"**Solución:**\n"
                    f"1. Añade el bot como administrador\n"
                    f"2. Otorga permisos de publicación"
                )
                return
            
            # Verificar si ya existe
            if str(chat.id) in data['channels']:
                await update.message.reply_text(
                    f"⚠️ **Canal ya configurado**\n\n📢 {chat.title}"
                )
                return
            
            # Guardar canal
            data['channels'][str(chat.id)] = {
                'title': chat.title,
                'username': chat.username,
                'type': chat.type,
                'added_date': datetime.now().isoformat()
            }
            
            data['step'] = 'idle'
            
            keyboard = [
                [InlineKeyboardButton("📝 Nueva Publicación", callback_data="new_post_quick")],
                [InlineKeyboardButton("➕ Añadir Otro Canal", callback_data="add_channel")]
            ]
            
            await update.message.reply_text(
                f"✅ **Canal añadido exitosamente**\n\n"
                f"📢 **Nombre:** {chat.title}\n"
                f"📊 **Total canales:** {len(data['channels'])}\n\n"
                f"🔘 **Ahora puedes crear publicaciones con botones interactivos**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error añadiendo canal {original_text}: {e}")
            await update.message.reply_text(
                f"❌ **Error:** {str(e)}\n\n"
                f"🔍 Canal: `{original_text}`"
            )
    
    async def show_button_template_selection(self, query, data):
        """Muestra selección de plantillas de botones"""
        templates = data.get('button_templates', {})
        
        keyboard = []
        for template_name in templates.keys():
            keyboard.append([InlineKeyboardButton(
                f"📋 {template_name.title()}",
                callback_data=f"template_{template_name}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="manage_buttons")])
        
        text = "📋 **Plantillas de Botones**\n\n"
        for name, buttons in templates.items():
            text += f"**{name.title()}:**\n"
            for btn in buttons[:2]:
                text += f"• {btn['text']}\n"
            if len(buttons) > 2:
                text += f"• ... y {len(buttons) - 2} más\n"
            text += "\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_post_menu(self, query, data):
        """Muestra el menú principal de publicación"""
        post = data.get('current_post')
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 Añadir Texto", callback_data="add_text"),
             InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("🔘 Gestionar Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview"),
             InlineKeyboardButton("📤 Publicar", callback_data="publish")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        text = f"🎯 **Nueva Publicación con Botones**\n\n"
        text += f"📺 Canales disponibles: **{len(data['channels'])}**\n"
        text += f"🔘 Botones: **{len(post.buttons)}**\n"
        text += f"📋 Estado: **Creando**\n\n"
        text += f"**Siguiente paso:** Añade contenido y botones"
        
        await query.edit_message_text(
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
            text += f"• Botones: **{len(post.buttons)}** ({post.button_layout})\n"
            text += f"• Canales: **{len(post.target_channels)}** seleccionados\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancelar acción actual"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        data['current_post'] = None
        data['step'] = 'idle'
        data.pop('temp_button_text', None)
        
        await update.message.reply_text("❌ **Acción cancelada**\n\nPuedes empezar de nuevo cuando quieras.")
    
    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de ayuda mejorado con botones"""
        text = """🚀 **Bot Publicador Multi-Canal con Botones**

**📋 COMANDOS:**
• `/nueva` - Crear publicación con botones
• `/canales` - Gestionar canales
• `/estado` - Ver estado actual
• `/help` - Esta ayuda

**🔘 TIPOS DE BOTONES:**
• **🔗 Links externos** - Sitios web, tiendas
• **📞 WhatsApp** - Contacto directo
• **📺 Telegram** - Canales y grupos
• **🛒 E-commerce** - Botones de compra
• **📊 Encuestas** - Interacción con usuarios

**📋 PLANTILLAS DISPONIBLES:**
• **E-commerce** - Comprar, Contactar, Valorar
• **Social** - Like, Comentar, Compartir
• **Educativo** - Ver Curso, Inscribirse
• **Noticias** - Leer Más, Suscribirse

**🎯 EJEMPLOS DE USO:**
```
📝 "Nueva oferta disponible!"
🔘 [🛒 Comprar Ahora] [📞 WhatsApp]

🎥 Video tutorial de programación
🔘 [📚 Ver Curso Completo]
🔘 [💬 Grupo de Estudiantes]

📰 Noticia importante
🔘 [📖 Leer Artículo] [🔔 Suscribirse]
```

**⚙️ LAYOUTS DE BOTONES:**
• **Horizontal** - Botones en fila (máx 3)
• **Vertical** - Un botón por fila  
• **Grid** - Cuadrícula 2x2

**💡 CONSEJOS:**
• Los botones aumentan el engagement
• Usa CTAs (Call To Action) claros
• Máximo 8 botones por mensaje
• Combina diferentes tipos de botones

**🚀 ¡Crea contenido interactivo que genere acción!**"""
        
        keyboard = [
            [KeyboardButton("📝 Nueva Publicación"), KeyboardButton("📺 Mis Canales")],
            [KeyboardButton("🔘 Plantillas de Botones"), KeyboardButton("📊 Estado")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )

# Resto del código (servidor web, etc.) se mantiene igual
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
    try:
        bot_info = await bot.app.bot.get_me()
        return Response(
            text=json.dumps({
                "status": "OK",
                "bot_username": bot_info.username,
                "active_users": len(user_data),
                "features": ["multi_channel", "buttons", "multimedia"],
                "timestamp": datetime.now().isoformat()
            }),
            content_type="application/json"
        )
    except Exception as e:
        return Response(text=f"ERROR: {e}", status=500)

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
        
        logger.info(f"🚀 Bot con Botones Interactivos INICIADO")
        logger.info(f"🌐 Puerto: {PORT}")
        logger.info(f"🔗 Webhook: {WEBHOOK_URL}")
        logger.info(f"🔘 Funcionalidades: Multi-canal + Botones")
        
        web.run_app(app, host='0.0.0.0', port=PORT)
        
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    main()