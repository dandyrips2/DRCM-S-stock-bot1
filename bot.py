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
from typing import List # Necesario para las opciones de selección dinámica

# Rutas de los archivos de stock y cooldown
STOCK_FILE = 'stock.json'
COOLDOWN_FILE = 'cooldown.json'

# Token: Se cargará desde las variables de entorno (Replit Secrets)
BOT_TOKEN = os.environ.get('BOT_TOKEN') 

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
            # La estructura de stock ahora es anidada: {"netflix": ["cuenta1", "cuenta2"], "spotify": [...]}
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
        try:
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
            print("Comandos slash sincronizados con el servidor.")
        except Exception as e:
            print(f"⚠️ Error al sincronizar comandos: {e}")

# Inicializar el bot con los intents necesarios
intents = discord.Intents.default()
bot = StockBot(intents=intents)

# =======================================================
# 4. COMANDOS SLASH (LÓGICA DEL BOT)
# =======================================================

# --- COMANDO /ADD_STOCK (ADMIN) ---
@bot.tree.command(name="add_stock", description="Añade ítems a una categoría de stock específica.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    category="El nombre de la categoría del stock (ej: Netflix, Spotify).",
    item="El item a añadir (ej: usuario:contraseña o un link)."
)
@app_commands.default_permissions(administrator=True) 
async def add_stock_command(interaction: discord.Interaction, category: str, item: str):
    await interaction.response.defer(ephemeral=True)
    
    category = category.lower().strip() # Normalizar la categoría a minúsculas
    item = item.strip()

    if not item:
        await interaction.followup.send("❌ El ítem no puede estar vacío.", ephemeral=True)
        return
        
    stock = load_data(STOCK_FILE)
    
    # Asegurar que la categoría exista como una lista
    if category not in stock:
        stock[category] = []
        
    # Añadir el ítem a la lista de esa categoría
    stock[category].append(item)
    save_data(stock, STOCK_FILE)
    
    await interaction.followup.send(
        f"➕ **¡Stock Añadido!** Se agregó un ítem a la categoría **{category.upper()}**.\nStock actual para {category.upper()}: **{len(stock[category])}**", 
        ephemeral=True
    )

# --- AUTOCOMPLETADO PARA /GENERATE ---
# Esta función es llamada por Discord para sugerir opciones mientras el usuario escribe.
async def stock_category_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    stock = load_data(STOCK_FILE)
    choices = []
    
    # Filtrar solo las categorías que tienen stock disponible
    available_categories = [
        key for key, value in stock.items() if value and len(value) > 0
    ]
    
    # Construir las opciones basadas en lo que el usuario está escribiendo
    for category in available_categories:
        if current.lower() in category:
            choices.append(app_commands.Choice(name=category.upper(), value=category))

    # Limitar las opciones (Discord tiene un límite)
    return choices[:25]


# --- COMANDO /GENERATE (USO DE STOCK Y COOLDOWN) ---
@bot.tree.command(name="generate", description="Genera un ítem de la categoría de stock seleccionada.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(category="Selecciona la categoría de stock que deseas generar.")
# Aquí adjuntamos la función de autocompletado al parámetro 'category'
@app_commands.autocomplete(category=stock_category_autocomplete) 
async def generate_command(interaction: discord.Interaction, category: str):
    await interaction.response.defer(ephemeral=True) 
    
    user_id = str(interaction.user.id)
    cooldowns = load_data(COOLDOWN_FILE)
    stock = load_data(STOCK_FILE)
    category = category.lower().strip()

    # 1. Verificación de Cooldown
    if user_id in cooldowns:
        last_usage_time = cooldowns[user_id]
        time_since_last_use = time.time() - last_usage_time
        
        if time_since_last_use < COOLDOWN_SECONDS:
            time_left = COOLDOWN_SECONDS - time_since_last_use
            minutes = int(time_left // 60)
            seconds = int(time_left % 60)
            
            await interaction.followup.send(
                f"⏰ ¡Tranquilo! Debes esperar **{minutes}m {seconds}s** antes de usar este comando de nuevo.",
                ephemeral=True
            )
            return

    # 2. Verificación de Stock y Categoría
    if category not in stock or not stock[category]:
        await interaction.followup.send(
            f"❌ **Stock Agotado** o la categoría **{category.upper()}** no existe o está vacía.", 
            ephemeral=True
        )
        return

    # 3. Obtener y Eliminar una Cuenta
    try:
        # Usamos .pop(0) para obtener y eliminar el primer ítem de la lista (FIFO)
        account_info = stock[category].pop(0) 
        
        # 4. Actualizar el Cooldown y el Stock
        cooldowns[user_id] = time.time() 
        save_data(cooldowns, COOLDOWN_FILE)
        save_data(stock, STOCK_FILE) # Guardar el stock modificado

        # 5. Enviar la Respuesta
        await interaction.followup.send(
            f"✅ ¡{category.upper()} Generada!\n\n||{account_info}||\n\n*(Este ítem ha sido removido. Próximo uso disponible en 1 hora.)*", 
            ephemeral=True
        )
        
    except Exception as e:
        print(f"Error al procesar stock: {e}")
        await interaction.followup.send(
            "⚠️ Ocurrió un error inesperado al intentar generar el ítem.", 
            ephemeral=True
        )


# --- COMANDO /CHECK_STOCK ---
@bot.tree.command(name="check_stock", description="Muestra el stock disponible por categoría.", guild=discord.Object(id=GUILD_ID))
async def check_stock_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    stock = load_data(STOCK_FILE)
    
    if not stock:
        await interaction.followup.send('ℹ️ Actualmente no hay ningún stock registrado.', ephemeral=True)
        return
        
    embed = discord.Embed(
        title="📦 Estado Actual del Stock por Categoría",
        color=discord.Color.blue()
    )

    total_items = 0
    for category, items in stock.items():
        count = len(items)
        if count > 0:
            embed.add_field(name=f'🔹 {category.upper()}', value=f'**{count}** ítems', inline=True)
            total_items += count

    if total_items == 0:
        await interaction.followup.send('⚠️ No hay ítems disponibles en ninguna categoría.', ephemeral=True)
    else:
        embed.set_footer(text=f"Total de ítems disponibles: {total_items}")
        await interaction.followup.send(embed=embed, ephemeral=True)


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
            keep_alive() 
            print("Iniciando conexión con Discord...")
            bot.run(BOT_TOKEN)
        else:
            print("❌ ERROR: El Token del Bot (BOT_TOKEN) no fue encontrado.")

    except discord.errors.LoginFailure:
        print("\n\n❌ ERROR: El Token del Bot es inválido.")
    except Exception as e:
        print(f"\n\n❌ Ocurrió un error al iniciar el bot: {e}")