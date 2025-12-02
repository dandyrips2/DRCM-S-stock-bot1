# =======================================================
# 1. IMPORTS Y CONFIGURACIÓN INICIAL (24/7 Y DISCORD)
# =======================================================
import discord
from discord import app_commands
import json
import os
import time
from threading import Thread
from flask import Flask

# Rutas de los archivos de stock y cooldown
STOCK_FILE = 'stock.json'
COOLDOWN_FILE = 'cooldown.json'

# Token: Se cargará desde las variables de entorno (Replit Secrets)
# Si pruebas en local, puedes cambiar esta línea a BOT_TOKEN = 'TU_TOKEN_SECRETO'
BOT_TOKEN = os.environ.get('BOT_TOKEN') # ¡NO uses el token directo aquí!

# ID de tu servidor (Guild ID)
# 🚨 ¡REEMPLAZA ESTE VALOR CON EL ID REAL DE TU SERVIDOR!
GUILD_ID = 1445495133918330912

# Cooldown en segundos (1 hora = 3600 segundos)
COOLDOWN_SECONDS = 3600 

# =======================================================
# 2. FUNCIONES DE LECTURA Y ESCRITURA JSON
# =======================================================

def load_data(filename):
    """Carga los datos de un archivo JSON. Retorna un diccionario vacío si falla."""
    try:
        if not os.path.exists(filename) or os.stat(filename).st_size == 0:
            return {}
        with open(filename, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
        print(f"Error al cargar {filename}: {e}. Retornando diccionario vacío.")
        return {}

def save_data(data, filename):
    """Guarda los datos en un archivo JSON."""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error al guardar en {filename}: {e}")

# =======================================================
# 3. CONFIGURACIÓN DEL CLIENTE DISCORD Y CLASES
# =======================================================

class StockBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f'🤖 Bot conectado como: {self.user} (ID: {self.user.id})')
        # Sincroniza comandos slash solo con el servidor especificado (más rápido)
        try:
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
            print("Comandos slash sincronizados con el servidor.")
        except Exception as e:
            print(f"⚠️ Error al sincronizar comandos: {e}")
            print("Asegúrate de que el GUILD_ID es correcto y que el bot tiene permisos.")

# Inicializar el bot con los intents necesarios
intents = discord.Intents.default()
bot = StockBot(intents=intents)

# =======================================================
# 4. COMANDOS SLASH (LÓGICA DEL BOT)
# =======================================================

# --- COMANDO /GENERATE (USO DE STOCK Y COOLDOWN) ---
@bot.tree.command(name="generate", description="Genera un ítem del stock disponible.", guild=discord.Object(id=GUILD_ID))
async def generate_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True) # Respuesta diferida y privada
    
    user_id = str(interaction.user.id)
    cooldowns = load_data(COOLDOWN_FILE)
    stock = load_data(STOCK_FILE)

    # 1. Verificación de Cooldown
    if user_id in cooldowns:
        last_usage_time = cooldowns[user_id]
        time_since_last_use = time.time() - last_usage_time
        
        if time_since_last_use < COOLDOWN_SECONDS:
            # Calcular tiempo restante
            time_left = COOLDOWN_SECONDS - time_since_last_use
            minutes = int(time_left // 60)
            seconds = int(time_left % 60)
            
            await interaction.followup.send(
                f"⏰ ¡Tranquilo! Debes esperar **{minutes}m {seconds}s** antes de usar este comando de nuevo.",
                ephemeral=True
            )
            return

    # 2. Verificación de Stock Disponible
    if not stock:
        await interaction.followup.send(
            "❌ **¡Stock Agotado!** No hay ítems disponibles en este momento.", 
            ephemeral=True
        )
        return

    # 3. Obtener y Eliminar una Cuenta
    try:
        # popitem() obtiene un par (clave, valor) y lo elimina del diccionario.
        key, account_info = stock.popitem() 
        
        # 4. Actualizar el Cooldown y el Stock
        cooldowns[user_id] = time.time() # Guardar el timestamp actual
        save_data(cooldowns, COOLDOWN_FILE)
        save_data(stock, STOCK_FILE) # Guardar el stock con el ítem eliminado

        # 5. Enviar la Respuesta
        await interaction.followup.send(
            f"✅ ¡Ítem Generado!\n\n||{account_info}||\n\n*(Este ítem ha sido removido del stock. Próximo uso disponible en 1 hora.)*", 
            ephemeral=True
        )
        
    except Exception as e:
        print(f"Error al procesar stock: {e}")
        await interaction.followup.send(
            "⚠️ Ocurrió un error inesperado al intentar generar el ítem. Inténtalo de nuevo.", 
            ephemeral=True
        )


# --- COMANDO /ADD_STOCK (ADMIN) ---
@bot.tree.command(name="add_stock", description="Añade ítems al stock (una por línea).", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(items="Pega las cuentas o links separados por un salto de línea.")
# Restringe el uso del comando solo a administradores del servidor
@app_commands.default_permissions(administrator=True) 
async def add_stock_command(interaction: discord.Interaction, items: str):
    await interaction.response.defer(ephemeral=True)
        
    new_items = items.split('\n')
    stock = load_data(STOCK_FILE)
    
    count = 0
    for item in new_items:
        item = item.strip()
        if item:
            # Usar un timestamp como clave única
            unique_key = str(time.time()).replace('.', '')
            stock[unique_key] = item 
            count += 1
            
    save_data(stock, STOCK_FILE)
    
    await interaction.followup.send(
        f"➕ **¡Stock Actualizado!** Se añadieron **{count}** nuevos ítems al stock. Stock total: {len(stock)}", 
        ephemeral=True
    )

# --- COMANDO /CHECK_STOCK ---
@bot.tree.command(name="check_stock", description="Muestra el número de ítems disponibles.", guild=discord.Object(id=GUILD_ID))
async def check_stock_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    stock = load_data(STOCK_FILE)
    count = len(stock)
    
    await interaction.followup.send(
        f"📊 **Stock Disponible:** Hay **{count}** ítems listos para ser generados.", 
        ephemeral=True
    )

# =======================================================
# 5. CONFIGURACIÓN DEL HOSTING 24/7 (REPLIT)
# =======================================================

app = Flask('')

@app.route('/')
def home():
    return "🤖 ¡El Bot de Stock está activo 24/7!"

def run():
  app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():  
    t = Thread(target=run)
    t.start()

# =======================================================
# 6. INICIO DEL BOT
# =======================================================

if __name__ == '__main__':
    # Creación inicial de archivos si no existen
    for file in [STOCK_FILE, COOLDOWN_FILE]:
        if not os.path.exists(file) or os.stat(file).st_size == 0:
             save_data({}, file)
    
    try:
        if BOT_TOKEN:
            keep_alive() # Inicia el servidor web para el 24/7
            print("Iniciando conexión con Discord...")
            bot.run(BOT_TOKEN)
        else:
            print("❌ ERROR: El Token del Bot (BOT_TOKEN) no fue encontrado.")
            print("Asegúrate de configurar los 'Secrets' en Replit.")

    except discord.errors.LoginFailure:
        print("\n\n❌ ERROR: El Token del Bot es inválido.")
    except Exception as e:
        print(f"\n\n❌ Ocurrió un error al iniciar el bot: {e}")