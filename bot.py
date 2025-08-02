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
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview"),
             InlineKeyboardButton("📤 Replicar", callback_data="publish")]
        ])
        
        post = data.get('current_post')
        button_info = f"🔘 Botones: **{len(post.buttons)}**" if post else ""
        
        text = f"🎯 **Seleccionar Canales Destino**\n\n" \
               f"✅ Seleccionados: **{selected_count}**\n" \
               f"📺 Disponibles: **{len(data['channels'])}**\n" \
               f"{button_info}\n\n" \
               f"Toca los canales donde quieres replicar"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_button_templates_main(self, update, data):
        """Muestra plantillas de botones desde el menú principal"""
        templates = data.get('button_templates', {})
        
        text = "📋 **Plantillas de Botones Disponibles**\n\n"
        
        for name, buttons in templates.items():
            text += f"**{name.title()}:**\n"
            for btn in buttons:
                text += f"• {btn['text']}\n"
            text += "\n"
        
        text += "💡 **Uso:** Reenvía una publicación al bot y selecciona 'Usar Plantilla'"
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostrar estado actual"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        text = f"📊 **Estado del Bot Replicador**\n\n"
        text += f"👤 **Usuario:** {update.effective_user.first_name}\n"
        text += f"📺 **Canales configurados:** {len(data['channels'])}\n"
        text += f"🔄 **Estado actual:** {data['step']}\n"
        text += f"🕐 **Última actividad:** {data['last_activity'].strftime('%H:%M')}\n\n"
        
        if data.get('current_post'):
            post = data['current_post']
            text += f"📝 **Publicación en Proceso:**\n"
            text += f"• **Contenido:** {'✅' if post.text or post.media else '❌'}\n"
            text += f"• **Botones:** {len(post.buttons)} ({post.button_layout})\n"
            text += f"• **Canales destino:** {len(post.target_channels)} seleccionados\n"
            text += f"• **Origen:** {post.forward_from}\n\n"
            
            text += f"📤 **Listo para replicar:** {'✅' if post.target_channels and post.has_content() else '❌'}"
        else:
            text += f"💡 **Tip:** Reenvía cualquier publicación para empezar a replicar con botones"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancelar acción actual"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        
        data['current_post'] = None
        data['step'] = 'idle'
        data.pop('temp_button_text', None)
        
        await update.message.reply_text(
            "❌ **Replicación cancelada**\n\n"
            "🔄 Puedes reenviar otra publicación cuando quieras."
        )
    
    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de ayuda mejorado"""
        text = """🚀 **Bot Replicador con Botones Interactivos**

**🔄 CÓMO FUNCIONA:**
1. **Reenvía** cualquier publicación al bot
2. El bot la **captura automáticamente**
3. **Añade botones** interactivos
4. **Selecciona canales** destino
5. **¡Replica con un clic!**

**📋 COMANDOS:**
• `/canales` - Gestionar canales destino
• `/estado` - Ver estado actual
• `/help` - Esta ayuda

**🔘 TIPOS DE BOTONES:**
• **🔗 Links externos** - Sitios web, tiendas online
• **📞 WhatsApp** - Contacto directo (wa.me)
• **📺 Telegram** - Canales y grupos
• **📧 Email** - Contacto por correo
• **🛒 E-commerce** - Botones de compra

**📋 PLANTILLAS INCLUIDAS:**
• **E-commerce** - Comprar, Contactar, Valorar
• **Social** - Me Gusta, Comentar, Compartir  
• **Noticias** - Leer Más, Suscribirse
• **Educativo** - Ver Curso, Inscribirse
• **Contacto** - WhatsApp, Email, Web

**🎯 EJEMPLOS DE USO:**

```
🛒 Reenvías: "Nueva oferta 50% OFF"
➕ Añades: [🛒 Comprar] [📞 WhatsApp]
📤 Replicas en 5 canales simultáneamente
```

```
📰 Reenvías: Noticia importante
➕ Añades: [📖 Leer Más] [🔔 Suscribirse]  
📤 Se publica con botones en todos tus canales
```

**⚙️ LAYOUTS DISPONIBLES:**
• **Horizontal** - Botones en fila (1-3 por fila)
• **Vertical** - Un botón por fila
• **Grid** - Cuadrícula 2x2

**💡 VENTAJAS:**
✅ **Rápido** - Sin crear desde cero
✅ **Consistente** - Mismo contenido, múltiples canales
✅ **Interactivo** - Botones aumentan engagement
✅ **Profesional** - Aspecto uniforme

**🚀 ¡Convierte cualquier contenido en publicación interactiva!**"""
        
        keyboard = [
            [KeyboardButton("📺 Mis Canales"), KeyboardButton("🔘 Plantillas")],
            [KeyboardButton("📊 Estado"), KeyboardButton("❓ Ayuda")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )

# Resto del código del servidor web
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
        bot_info = await bot.app.bot.get_me()
        return Response(
            text=json.dumps({
                "status": "OK",
                "bot_username": bot_info.username,
                "active_users": len(user_data),
                "features": ["forward_replication", "interactive_buttons", "multi_channel"],
                "version": "2.0 - Forwarder Edition",
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
        
        logger.info(f"🚀 Bot Replicador con Botones INICIADO")
        logger.info(f"🌐 Puerto: {PORT}")
        logger.info(f"🔗 Webhook: {WEBHOOK_URL}")
        logger.info(f"🔄 Funcionalidad: Reenvío + Botones + Multi-canal")
        
        web.run_app(app, host='0.0.0.0', port=PORT)
        
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    main()markup=InlineKeyboardMarkup(keyboard),
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

**Para replicar contenido necesitas:**
1. Añadir el bot como administrador del canal
2. Darle permisos de publicación
3. Registrar el canal en el bot

🔄 **Una vez configurado, simplemente reenvía cualquier publicación al bot**"""
        else:
            keyboard = [
                [InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")],
                [InlineKeyboardButton("🗑️ Eliminar Canal", callback_data="remove_channel")]
            ]
            
            text = f"📺 **Canales Configurados** ({len(data['channels'])})\n\n"
            
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
                    f"2. Otorga permisos de publicación\n"
                    f"3. Intenta nuevamente"
                )
                return
            
            # Verificar si ya existe
            if str(chat.id) in data['channels']:
                await update.message.reply_text(
                    f"⚠️ **Canal ya configurado**\n\n📢 {chat.title}\n\n"
                    f"🔄 Puedes empezar a reenviar publicaciones para replicar"
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
                [InlineKeyboardButton("➕ Añadir Otro Canal", callback_data="add_channel")]
            ]
            
            await update.message.reply_text(
                f"✅ **Canal añadido exitosamente**\n\n"
                f"📢 **Nombre:** {chat.title}\n"
                f"📊 **Total canales:** {len(data['channels'])}\n\n"
                f"🔄 **¡Listo!** Ahora reenvía cualquier publicación al bot y él te permitirá añadir botones y replicarla en tus canales.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error añadiendo canal {original_text}: {e}")
            await update.message.reply_text(
                f"❌ **Error:** No se pudo añadir el canal\n\n"
                f"🔍 **Verificar:**\n"
                f"• El bot es administrador\n"
                f"• Tiene permisos de publicación\n"
                f"• El identificador es correcto\n\n"
                f"Formato enviado: `{original_text}`",
                parse_mode=ParseMode.MARKDOWN
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
        
        text += "💡 **Tip:** Las plantillas reemplazan botones existentes"
        
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
            [InlineKeyboardButton("🔘 Gestionar Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("✏️ Editar Texto", callback_data="edit_text"),
             InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📋 Usar Plantilla", callback_data="button_templates")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview"),
             InlineKeyboardButton("📤 Replicar", callback_data="publish")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        # Info del contenido
        content_type = "📝 Texto"
        if post.media:
            media_type = post.media[0]['type']
            content_icons = {
                'photo': '📸 Imagen', 'video': '🎥 Video', 'animation': '🎭 GIF',
                'audio': '🎵 Audio', 'voice': '🎤 Voz', 'document': '📄 Documento',
                'sticker': '😀 Sticker'
            }
            content_type = content_icons.get(media_type, '📎 Media')
        
        text = f"🔄 **Replicación de Contenido**\n\n"
        text += f"📂 **Tipo:** {content_type}\n"
        text += f"📺 **Canales disponibles:** {len(data['channels'])}\n"
        text += f"🔘 **Botones:** {len(post.buttons)}\n"
        text += f"🎯 **Seleccionados:** {len(post.target_channels)}\n\n"
        text += f"**¿Qué quieres hacer?**"
        
        await query.edit_message_text(
            text,
            reply_import logging
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
WEBHOOK_URL = os.getenv('WEBHOOK_URL', f'https://botonesbot.onrender.com')

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

class ForwardedPost:
    """Clase para manejar publicaciones reenviadas"""
    def __init__(self, original_message):
        self.original_message = original_message
        self.text = self.extract_text()
        self.media = self.extract_media()
        self.target_channels = set()
        self.buttons = []
        self.button_layout = "horizontal"
        self.original_date = original_message.date
        self.forward_from = self.get_forward_info()
    
    def extract_text(self):
        """Extrae el texto del mensaje original"""
        if self.original_message.text:
            return self.original_message.text
        elif self.original_message.caption:
            return self.original_message.caption
        return ""
    
    def extract_media(self):
        """Extrae media del mensaje original"""
        media = []
        
        if self.original_message.photo:
            photo = self.original_message.photo[-1]  # Mejor resolución
            media.append({
                'file_id': photo.file_id,
                'type': 'photo'
            })
        elif self.original_message.video:
            media.append({
                'file_id': self.original_message.video.file_id,
                'type': 'video'
            })
        elif self.original_message.animation:
            media.append({
                'file_id': self.original_message.animation.file_id,
                'type': 'animation'
            })
        elif self.original_message.audio:
            media.append({
                'file_id': self.original_message.audio.file_id,
                'type': 'audio'
            })
        elif self.original_message.voice:
            media.append({
                'file_id': self.original_message.voice.file_id,
                'type': 'voice'
            })
        elif self.original_message.document:
            media.append({
                'file_id': self.original_message.document.file_id,
                'type': 'document'
            })
        elif self.original_message.sticker:
            media.append({
                'file_id': self.original_message.sticker.file_id,
                'type': 'sticker'
            })
        
        return media
    
    def get_forward_info(self):
        """Obtiene información del reenvío - VERSIÓN CORREGIDA"""
        try:
            # Verificar si es un mensaje reenviado usando los nuevos atributos
            if hasattr(self.original_message, 'forward_origin') and self.original_message.forward_origin:
                forward_origin = self.original_message.forward_origin
                
                # Verificar el tipo de origen del reenvío
                if hasattr(forward_origin, 'type'):
                    if forward_origin.type == 'user':
                        if hasattr(forward_origin, 'sender_user') and forward_origin.sender_user:
                            return f"Usuario: {forward_origin.sender_user.first_name}"
                        return "Usuario: Usuario"
                    elif forward_origin.type == 'chat':
                        if hasattr(forward_origin, 'sender_chat') and forward_origin.sender_chat:
                            return f"Chat: {forward_origin.sender_chat.title}"
                        return "Chat: Chat"
                    elif forward_origin.type == 'channel':
                        if hasattr(forward_origin, 'chat') and forward_origin.chat:
                            return f"Canal: {forward_origin.chat.title}"
                        return "Canal: Canal"
                    elif forward_origin.type == 'hidden_user':
                        if hasattr(forward_origin, 'sender_user_name'):
                            return f"Cuenta oculta: {forward_origin.sender_user_name}"
                        return "Cuenta oculta"
                
                return "Mensaje reenviado"
            
            # Verificar atributos legacy por compatibilidad (versiones anteriores)
            elif hasattr(self.original_message, 'forward_from') and self.original_message.forward_from:
                return f"Usuario: {self.original_message.forward_from.first_name}"
            elif hasattr(self.original_message, 'forward_from_chat') and self.original_message.forward_from_chat:
                return f"Canal: {self.original_message.forward_from_chat.title}"
            elif hasattr(self.original_message, 'forward_sender_name') and self.original_message.forward_sender_name:
                return f"Cuenta oculta: {self.original_message.forward_sender_name}"
            
            # Si no es un reenvío, indicar que es mensaje original
            return "Mensaje original"
            
        except Exception as e:
            logger.error(f"Error obteniendo info de reenvío: {e}")
            return "Mensaje original"
    
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
            row = []
            for i, button in enumerate(self.buttons):
                row.append(button.to_telegram_button())
                if len(row) == 3 or i == len(self.buttons) - 1:
                    keyboard.append(row)
                    row = []
                    
        elif self.button_layout == "vertical":
            for button in self.buttons:
                keyboard.append([button.to_telegram_button()])
                
        elif self.button_layout == "grid":
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
        self.app.add_handler(CommandHandler("canales", self.manage_channels))
        self.app.add_handler(CommandHandler("estado", self.status))
        self.app.add_handler(CommandHandler("cancelar", self.cancel))
        
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Manejador PRINCIPAL para mensajes reenviados/cualquiera
        self.app.add_handler(MessageHandler(
            filters.ALL & ~filters.COMMAND, 
            self.handle_forwarded_message
        ))
    
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
                {'text': '👍 Me Gusta', 'callback_data': 'like_post'},
                {'text': '💬 Comentar', 'url': 'https://t.me/mi_canal'},
                {'text': '🔄 Compartir', 'callback_data': 'share_post'}
            ],
            'news': [
                {'text': '📖 Leer Más', 'url': 'https://ejemplo.com/noticia'},
                {'text': '🔔 Suscribirse', 'url': 'https://t.me/noticias'},
                {'text': '📤 Compartir', 'callback_data': 'share_news'}
            ],
            'educational': [
                {'text': '📚 Ver Curso', 'url': 'https://ejemplo.com/curso'},
                {'text': '🎓 Inscribirse', 'url': 'https://ejemplo.com/registro'},
                {'text': '💬 Preguntas', 'url': 'https://t.me/soporte'}
            ],
            'contact': [
                {'text': '📞 WhatsApp', 'url': 'https://wa.me/1234567890'},
                {'text': '📧 Email', 'url': 'mailto:contacto@ejemplo.com'},
                {'text': '🌐 Web', 'url': 'https://ejemplo.com'}
            ]
        }
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user = update.effective_user
        self.get_user_data(user.id)
        
        text = f"""🚀 **Bot Replicador con Botones**

¡Hola {user.first_name}! 👋

**🔄 FUNCIONALIDAD PRINCIPAL:**
**Reenvía cualquier publicación al bot** y él te permitirá:

• 🔘 **Añadir botones interactivos**
• 📺 **Replicar en múltiples canales**
• 🎯 **Personalizar el layout**
• 📊 **Usar plantillas predefinidas**

**📝 CÓMO USAR:**
1. **Reenvía** una publicación al bot
2. El bot la **detecta automáticamente**
3. **Añade botones** que quieras
4. **Selecciona canales** destino
5. **¡Publica con un clic!**

**🔘 TIPOS DE BOTONES:**
• 🔗 Links externos • 📞 WhatsApp
• 📺 Telegram • 🛒 E-commerce

**COMANDOS:**
• /canales - Gestionar canales
• /help - Ayuda completa

**🎯 ¡Simplemente reenvía y replica!**"""
        
        keyboard = [
            [KeyboardButton("📺 Mis Canales"), KeyboardButton("🔘 Plantillas")],
            [KeyboardButton("📊 Estado"), KeyboardButton("❓ Ayuda")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_forwarded_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja CUALQUIER mensaje (reenviado o no) para replicar"""
        user_id = update.effective_user.id
        data = self.get_user_data(user_id)
        message = update.message
        
        # Si está en un paso específico, manejar eso primero
        step = data.get('step', 'idle')
        
        # Manejar pasos específicos
        if step == 'adding_channel':
            await self.add_channel(update, user_id, message.text)
            return
        elif step.startswith('adding_button_'):
            await self.handle_button_creation(update, data, message.text)
            return
        elif step == 'adding_text' and data.get('current_post'):
            await self.handle_custom_text(update, data, message.text)
            return
        
        # Manejar botones del teclado principal
        if message.text:
            if message.text == "📺 Mis Canales":
                await self.manage_channels(update, context)
                return
            elif message.text == "🔘 Plantillas":
                await self.show_button_templates_main(update, data)
                return
            elif message.text == "📊 Estado":
                await self.status(update, context)
                return
            elif message.text == "❓ Ayuda":
                await self.help_cmd(update, context)
                return
        
        # Verificar canales
        if not data['channels']:
            keyboard = [[InlineKeyboardButton("➕ Añadir Canal", callback_data="add_channel")]]
            await message.reply_text(
                "❌ **Primero configura canales**\n\n"
                "Para replicar publicaciones necesitas canales destino.\n"
                "Añade al menos un canal donde tengas permisos de administrador.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # AQUÍ ES LA MAGIA: Crear publicación desde mensaje
        try:
            forwarded_post = ForwardedPost(message)
            data['current_post'] = forwarded_post
            data['step'] = 'editing'
        except Exception as e:
            logger.error(f"Error creando ForwardedPost: {e}")
            await message.reply_text(
                "❌ **Error procesando mensaje**\n\n"
                "Intenta reenviar el mensaje nuevamente."
            )
            return
        
        # Determinar tipo de contenido
        content_type = "📝 Texto"
        if forwarded_post.media:
            media_type = forwarded_post.media[0]['type']
            content_icons = {
                'photo': '📸 Imagen',
                'video': '🎥 Video', 
                'animation': '🎭 GIF',
                'audio': '🎵 Audio',
                'voice': '🎤 Voz',
                'document': '📄 Documento',
                'sticker': '😀 Sticker'
            }
            content_type = content_icons.get(media_type, '📎 Media')
        
        # Mostrar menú de edición
        keyboard = [
            [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("✏️ Editar Texto", callback_data="edit_text"),
             InlineKeyboardButton("🎯 Seleccionar Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📋 Usar Plantilla", callback_data="button_templates")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview"),
             InlineKeyboardButton("📤 Replicar", callback_data="publish")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        # Texto de confirmación
        preview_text = forwarded_post.text[:100] + "..." if len(forwarded_post.text) > 100 else forwarded_post.text
        
        confirmation_text = f"✅ **Publicación Capturada**\n\n"
        confirmation_text += f"📂 **Tipo:** {content_type}\n"
        confirmation_text += f"📏 **Longitud:** {len(forwarded_post.text)} caracteres\n"
        confirmation_text += f"📅 **Origen:** {forwarded_post.forward_from}\n"
        confirmation_text += f"📺 **Canales disponibles:** {len(data['channels'])}\n\n"
        
        if preview_text:
            confirmation_text += f"**Vista previa:**\n_{preview_text}_\n\n"
        
        confirmation_text += f"🔘 **¿Qué quieres hacer?**"
        
        await message.reply_text(
            confirmation_text,
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
                    f"✅ **Layout actualizado**: {layout.title()}",
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
        
        # Callbacks para creación de botones
        elif callback_data == "add_url_button":
            data['step'] = 'adding_button_text'
            await query.edit_message_text(
                "➕ **Crear Botón con Link**\n\n"
                "✍️ **Paso 1:** Envía el texto del botón\n\n"
                "**Ejemplos:**\n"
                "• `🛒 Comprar Ahora`\n"
                "• `📞 Contactar`\n"
                "• `📖 Leer Más`\n\n"
                "Para cancelar, usa /cancelar",
                parse_mode=ParseMode.MARKDOWN
            )
        elif callback_data == "add_whatsapp_button":
            data['step'] = 'adding_whatsapp_text'
            await query.edit_message_text(
                "📞 **Crear Botón de WhatsApp**\n\n"
                "✍️ **Paso 1:** Envía el texto del botón\n\n"
                "**Ejemplos:**\n"
                "• `📞 Contactar por WhatsApp`\n"
                "• `💬 Chatear ahora`\n"
                "• `📱 Escribir mensaje`\n\n"
                "Para cancelar, usa /cancelar",
                parse_mode=ParseMode.MARKDOWN
            )
        elif callback_data == "add_telegram_button":
            data['step'] = 'adding_telegram_text'
            await query.edit_message_text(
                "📺 **Crear Botón de Telegram**\n\n"
                "✍️ **Paso 1:** Envía el texto del botón\n\n"
                "**Ejemplos:**\n"
                "• `📺 Unirse al Canal`\n"
                "• `💬 Ir al Grupo`\n"
                "• `📢 Seguir Canal`\n\n"
                "Para cancelar, usa /cancelar",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif callback_data == "button_templates":
            await self.show_button_template_selection(query, data)
        
        elif callback_data == "back_to_post":
            await self.show_post_menu(query, data)
        
        # Callbacks principales
        elif callback_data == "add_channel":
            data['step'] = 'adding_channel'
            await query.edit_message_text(
                """➕ **Añadir Canal**

**Instrucciones:**
1️⃣ Añade el bot como administrador del canal
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
        
        elif callback_data == "edit_text":
            data['step'] = 'adding_text'
            current_text = data['current_post'].text if data.get('current_post') else ""
            await query.edit_message_text(
                f"✏️ **Editar Texto**\n\n"
                f"📝 **Texto actual:**\n_{current_text}_\n\n"
                f"Envía el nuevo texto o usa /cancelar para mantener el actual",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif callback_data == "preview":
            await self.show_preview(query, data)
        
        elif callback_data == "publish":
            await self.publish_post(query, user_id)
        
        elif callback_data == "cancel":
            data['current_post'] = None
            data['step'] = 'idle'
            await query.edit_message_text(
                "❌ **Replicación cancelada**\n\n"
                "🔄 Puedes reenviar otra publicación cuando quieras"
            )
    
    async def handle_custom_text(self, update, data, text):
        """Maneja texto personalizado para la publicación"""
        if len(text) > 4096:
            await update.message.reply_text(
                f"❌ **Texto muy largo** ({len(text)}/4096 caracteres)"
            )
            return
        
        data['current_post'].text = text
        data['step'] = 'editing'
        
        keyboard = [
            [InlineKeyboardButton("🔘 Añadir Botones", callback_data="manage_buttons")],
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview"),
             InlineKeyboardButton("📤 Replicar", callback_data="publish")]
        ]
        
        await update.message.reply_text(
            f"✅ **Texto actualizado** ({len(text)} caracteres)\n\n"
            f"💡 **Siguiente:** Añade botones para mayor interacción",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_button_management(self, query, data):
        """Muestra el menú de gestión de botones"""
        post = data.get('current_post')
        if not post:
            await query.edit_message_text("❌ No hay publicación activa")
            return
        
        text = f"🔘 **Gestión de Botones**\n\n"
        text += f"📊 **Botones actuales:** {len(post.buttons)}\n"
        text += f"📐 **Layout:** {post.button_layout.title()}\n"
        text += f"📺 **Canales seleccionados:** {len(post.target_channels)}\n\n"
        
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
        
        keyboard.extend([
            [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="back_to_post")]
        ])
        
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
                f"🗑️ {button.text[:25]}...",
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
        
        text = "👀 **Vista Previa de Replicación**\n\n"
        
        # Info del contenido
        if post.media:
            media_type = post.media[0]['type']
            content_icons = {
                'photo': '📸 Imagen', 'video': '🎥 Video', 'animation': '🎭 GIF',
                'audio': '🎵 Audio', 'voice': '🎤 Voz', 'document': '📄 Documento',
                'sticker': '😀 Sticker'
            }
            text += f"📂 **Contenido:** {content_icons.get(media_type, '📎 Media')}\n"
        
        if post.text:
            preview_text = post.text[:150] + "..." if len(post.text) > 150 else post.text
            text += f"📝 **Texto:** _{preview_text}_\n\n"
        
        if post.buttons:
            text += f"🔘 **Botones:** {len(post.buttons)} ({post.button_layout})\n"
            for i, button in enumerate(post.buttons, 1):
                icon = "🔗" if button.button_type == 'url' else "⚡"
                text += f"{i}. {icon} {button.text}\n"
            text += "\n"
        
        text += f"🎯 **Canales destino:** {len(post.target_channels)} seleccionados\n"
        text += f"📅 **Origen:** {post.forward_from}\n\n"
        
        # Mostrar preview de botones si existen
        preview_keyboard = post.get_inline_keyboard()
        
        control_keyboard = [
            [InlineKeyboardButton("🔘 Gestionar Botones", callback_data="manage_buttons"),
             InlineKeyboardButton("🎯 Canales", callback_data="select_channels")],
            [InlineKeyboardButton("📤 Replicar Ahora", callback_data="publish"), 
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        
        await query.edit_message_text(
            text + "**⬇️ Así se verá la publicación:**",
            reply_markup=InlineKeyboardMarkup(control_keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Enviar preview real si hay botones
        if preview_keyboard:
            await query.message.reply_text(
                post.text or "📢 Tu contenido replicado",
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
            f"✅ **Plantilla aplicada: {template_name.title()}**\n\n"
            f"📊 Botones añadidos: {len(post.buttons)}\n\n"
            f"Puedes editarlos individualmente si necesitas.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def publish_post(self, query, user_id):
        """Publica/replica la publicación con botones"""
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
        await query.edit_message_text("🚀 **Replicando con botones...**\n\n⏳ Enviando a los canales...")
        
        # Generar teclado de botones
        reply_markup = post.get_inline_keyboard()
        
        # Replicar en cada canal
        results = []
        success_count = 0
        
        for i, ch_id in enumerate(post.target_channels, 1):
            try:
                channel_info = data['channels'][ch_id]
                channel_name = channel_info.get('title', 'Canal')
                
                # Enviar contenido con botones según el tipo
                if post.media:
                    media_item = post.media[0]
                    media_type = media_item['type']
                    file_id = media_item['file_id']
                    
                    if media_type == 'photo':
                        await self.app.bot.send_photo(
                            chat_id=ch_id,
                            photo=file_id,
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_type == 'video':
                        await self.app.bot.send_video(
                            chat_id=ch_id,
                            video=file_id,
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_type == 'animation':
                        await self.app.bot.send_animation(
                            chat_id=ch_id,
                            animation=file_id,
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_type == 'audio':
                        await self.app.bot.send_audio(
                            chat_id=ch_id,
                            audio=file_id,
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_type == 'voice':
                        await self.app.bot.send_voice(
                            chat_id=ch_id,
                            voice=file_id,
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_type == 'document':
                        await self.app.bot.send_document(
                            chat_id=ch_id,
                            document=file_id,
                            caption=post.text or "",
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif media_type == 'sticker':
                        # Los stickers no pueden tener caption, enviamos texto separado si hay botones
                        await self.app.bot.send_sticker(
                            chat_id=ch_id,
                            sticker=file_id
                        )
                        if post.text or reply_markup:
                            await self.app.bot.send_message(
                                chat_id=ch_id,
                                text=post.text or "📢 Contenido replicado",
                                reply_markup=reply_markup,
                                parse_mode=ParseMode.MARKDOWN
                            )
                else:
                    # Solo texto con botones
                    await self.app.bot.send_message(
                        chat_id=ch_id,
                        text=post.text or "📢 Contenido replicado",
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                results.append(f"✅ **{channel_name}**")
                success_count += 1
                
            except Exception as e:
                results.append(f"❌ **{channel_name}**: Error")
                logger.error(f"Error replicando en {ch_id}: {e}")
        
        # Mostrar resultados
        result_text = f"📊 **Resultados de Replicación**\n\n"
        result_text += f"✅ **Exitosas:** {success_count}/{len(post.target_channels)}\n"
        result_text += f"🔘 **Con botones:** {len(post.buttons)}\n"
        result_text += f"📐 **Layout:** {post.button_layout.title()}\n"
        result_text += f"📅 **Origen:** {post.forward_from}\n\n"
        result_text += "**Detalle:**\n" + "\n".join(results[:10])
        
        if len(results) > 10:
            result_text += f"\n... y {len(results) - 10} más"
        
        # Limpiar datos
        data['current_post'] = None
        data['step'] = 'idle'
        
        keyboard = [[InlineKeyboardButton("🔄 Replicar Otra", callback_data="new_replication")]]
        
        await query.edit_message_text(
            result_text, 
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
                f"• https://t.me/canal",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif step == 'adding_button_url':
            # Crear el botón completo
            button_text = data.get('temp_button_text', 'Botón')
            
            # Validar URL básica
            if not (text.startswith('http') or text.startswith('https') or text.startswith('tg:') or text.startswith('mailto:')):
                await update.message.reply_text(
                    "❌ **URL inválida**\n\n"
                    "La URL debe empezar con:\n"
                    "• `https://` • `http://`\n"
                    "• `tg://` • `mailto:`"
                )
                return
            
            # Añadir botón a la publicación
            post.add_button(button_text, url=text, button_type='url')
            
            # Limpiar datos temporales
            data['step'] = 'editing'
            data.pop('temp_button_text', None)
            
            keyboard = [
                [InlineKeyboardButton("➕ Otro Botón", callback_data="add_button")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Replicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                f"✅ **Botón añadido**\n\n"
                f"🔘 **Texto:** {button_text}\n"
                f"🔗 **URL:** {text}\n\n"
                f"📊 **Total botones:** {len(post.buttons)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Manejo de botones de WhatsApp
        elif step == 'adding_whatsapp_text':
            data['temp_button_text'] = text
            data['step'] = 'adding_whatsapp_url'
            await update.message.reply_text(
                f"📞 **Número de WhatsApp**\n\n"
                f"Botón: `{text}`\n\n"
                f"Envía el número de WhatsApp:\n"
                f"• `1234567890`\n"
                f"• `+1234567890`\n"
                f"• O la URL completa: `https://wa.me/1234567890`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif step == 'adding_whatsapp_url':
            button_text = data.get('temp_button_text', 'WhatsApp')
            
            # Formatear número de WhatsApp
            whatsapp_url = text.strip()
            if whatsapp_url.startswith('https://wa.me/'):
                # Ya está formateado
                pass
            elif whatsapp_url.startswith('+'):
                whatsapp_url = f"https://wa.me/{whatsapp_url[1:]}"
            elif whatsapp_url.isdigit():
                whatsapp_url = f"https://wa.me/{whatsapp_url}"
            else:
                await update.message.reply_text(
                    "❌ **Número inválido**\n\n"
                    "Formato válido:\n"
                    "• `1234567890`\n"
                    "• `+1234567890`"
                )
                return
            
            post.add_button(button_text, url=whatsapp_url, button_type='url')
            data['step'] = 'editing'
            data.pop('temp_button_text', None)
            
            keyboard = [
                [InlineKeyboardButton("➕ Otro Botón", callback_data="add_button")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Replicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                f"✅ **Botón de WhatsApp añadido**\n\n"
                f"🔘 **Texto:** {button_text}\n"
                f"📞 **URL:** {whatsapp_url}\n\n"
                f"📊 **Total botones:** {len(post.buttons)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Manejo de botones de Telegram
        elif step == 'adding_telegram_text':
            data['temp_button_text'] = text
            data['step'] = 'adding_telegram_url'
            await update.message.reply_text(
                f"📺 **Canal/Grupo de Telegram**\n\n"
                f"Botón: `{text}`\n\n"
                f"Envía el enlace del canal/grupo:\n"
                f"• `@nombrecanal`\n"
                f"• `https://t.me/nombrecanal`\n"
                f"• `https://t.me/joinchat/xxxxx`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif step == 'adding_telegram_url':
            button_text = data.get('temp_button_text', 'Telegram')
            
            # Formatear URL de Telegram
            telegram_url = text.strip()
            if telegram_url.startswith('https://t.me/'):
                # Ya está formateado
                pass
            elif telegram_url.startswith('@'):
                telegram_url = f"https://t.me/{telegram_url[1:]}"
            elif not telegram_url.startswith('http'):
                telegram_url = f"https://t.me/{telegram_url}"
            
            post.add_button(button_text, url=telegram_url, button_type='url')
            data['step'] = 'editing'
            data.pop('temp_button_text', None)
            
            keyboard = [
                [InlineKeyboardButton("➕ Otro Botón", callback_data="add_button")],
                [InlineKeyboardButton("👀 Vista Previa", callback_data="preview")],
                [InlineKeyboardButton("📤 Replicar", callback_data="publish")]
            ]
            
            await update.message.reply_text(
                f"✅ **Botón de Telegram añadido**\n\n"
                f"🔘 **Texto:** {button_text}\n"
                f"📺 **URL:** {telegram_url}\n\n"
                f"📊 **Total botones:** {len(post.buttons)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )