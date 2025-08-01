#!/usr/bin/env python3
"""
Script de verificación para el Bot Publicador Multi-Canal
Ejecuta este script localmente para verificar que todo está configurado correctamente
"""

import os
import requests
import json
import asyncio
import sys

# Configuración
BOT_TOKEN = os.getenv('BOT_TOKEN', 'TU_TOKEN_AQUI')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://tu-servicio.onrender.com')

def check_bot_token():
    """Verifica que el token del bot es válido"""
    print("🔍 Verificando token del bot...")
    
    if BOT_TOKEN == 'TU_TOKEN_AQUI':
        print("❌ ERROR: BOT_TOKEN no configurado")
        return False
    
    try:
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
        data = response.json()
        
        if data['ok']:
            bot_info = data['result']
            print(f"✅ Bot válido: @{bot_info['username']} ({bot_info['first_name']})")
            return True
        else:
            print(f"❌ Token inválido: {data['description']}")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando token: {e}")
        return False

def check_webhook_info():
    """Verifica información del webhook"""
    print("\n🔍 Verificando webhook...")
    
    try:
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo")
        data = response.json()
        
        if data['ok']:
            webhook_info = data['result']
            
            if webhook_info['url']:
                print(f"✅ Webhook activo: {webhook_info['url']}")
                print(f"📊 Updates pendientes: {webhook_info.get('pending_update_count', 0)}")
                
                if webhook_info.get('last_error_date'):
                    print(f"⚠️ Último error: {webhook_info.get('last_error_message', 'Sin detalles')}")
                
                return True
            else:
                print("❌ No hay webhook configurado")
                return False
        else:
            print(f"❌ Error obteniendo webhook info: {data['description']}")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando webhook: {e}")
        return False

def check_render_service():
    """Verifica que el servicio de Render responde"""
    print("\n🔍 Verificando servicio en Render...")
    
    if WEBHOOK_URL == 'https://tu-servicio.onrender.com':
        print("❌ ERROR: WEBHOOK_URL no configurado correctamente")
        return False
    
    try:
        # Verificar health check
        health_url = WEBHOOK_URL.rstrip('/') + '/health'
        response = requests.get(health_url, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Servicio activo: {health_url}")
            print(f"📝 Respuesta: {response.text}")
            return True
        else:
            print(f"❌ Servicio no responde: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando servicio: {e}")
        print("💡 Tip: El servicio puede estar 'dormido' en el plan free de Render")
        return False

def set_webhook():
    """Configura el webhook"""
    print("\n🔧 Configurando webhook...")
    
    webhook_endpoint = WEBHOOK_URL.rstrip('/') + '/webhook'
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={'url': webhook_endpoint}
        )
        
        data = response.json()
        
        if data['ok']:
            print(f"✅ Webhook configurado: {webhook_endpoint}")
            return True
        else:
            print(f"❌ Error configurando webhook: {data['description']}")
            return False
            
    except Exception as e:
        print(f"❌ Error configurando webhook: {e}")
        return False

def test_bot_commands():
    """Instrucciones para probar el bot"""
    print("\n🧪 PRUEBAS MANUALES:")
    print("1. Busca tu bot en Telegram")
    print("2. Envía /start")
    print("3. Deberías ver el mensaje de bienvenida")
    print("4. Prueba /canales para gestionar canales")
    print("5. Prueba /nueva para crear una publicación")

def show_configuration_summary():
    """Muestra resumen de configuración"""
    print("\n📋 RESUMEN DE CONFIGURACIÓN:")
    print("=" * 50)
    print(f"BOT_TOKEN: {'✅ Configurado' if BOT_TOKEN != 'TU_TOKEN_AQUI' else '❌ No configurado'}")
    print(f"WEBHOOK_URL: {'✅ ' + WEBHOOK_URL if WEBHOOK_URL != 'https://tu-servicio.onrender.com' else '❌ No configurado'}")
    print("=" * 50)

def main():
    """Función principal de verificación"""
    print("🚀 BOT PUBLICADOR MULTI-CANAL - VERIFICACIÓN")
    print("=" * 60)
    
    show_configuration_summary()
    
    # Verificaciones
    checks = [
        ("Token del Bot", check_bot_token),
        ("Servicio Render", check_render_service),
        ("Configurar Webhook", set_webhook),
        ("Info Webhook", check_webhook_info),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error en {name}: {e}")
            results.append((name, False))
    
    # Resumen final
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE VERIFICACIONES:")
    
    success_count = 0
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
        if success:
            success_count += 1
    
    print(f"\n🎯 {success_count}/{len(results)} verificaciones exitosas")
    
    if success_count == len(results):
        print("\n🎉 ¡TODO CONFIGURADO CORRECTAMENTE!")
        test_bot_commands()
    else:
        print("\n⚠️ HAY PROBLEMAS QUE RESOLVER:")
        print("1. Verifica las variables de entorno en Render")
        print("2. Asegúrate de que el servicio esté deployado")
        print("3. Revisa los logs en el dashboard de Render")
        
    print("\n📞 SOPORTE:")
    print("- Logs de Render: Dashboard → Tu servicio → Logs")
    print("- Health check: " + WEBHOOK_URL.rstrip('/') + '/health')
    print("- Webhook info: https://api.telegram.org/bot<TOKEN>/getWebhookInfo")

if __name__ == "__main__":
    main()