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

# ID del usuario para recibir comprobantes (el usuario <@816767606429057026>)
CONFIRMATION_USER_ID = 816767606429057026

# =======================================================
# 2. FUNCIONES DE LECTURA Y ESCRITURA JSON
# =======================================================

def load_data(filename):
    """Carga los datos de un archivo JSON. Retorna un diccionario vacío si falla."""
    # Estructura del Stock: {"category": {"premium": [items], "free": [items]}}
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
        try:
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
            print("Comandos slash sincronizados con el servidor.")
        except Exception as e:
            print(f"⚠️ Error al sincronizar comandos: {e}")

# Inicializar el bot con los intents necesarios
intents = discord.Intents.default()
bot = StockBot(intents=intents)

# =======================================================
# 4. FUNCIONES DE AUTOCOMPLETADO
# =======================================================

# Autocompletado para el campo 'category' en /generate
async def stock_category_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    stock = load_data(STOCK_FILE)
    choices = []
    
    # Identificar las categorías que tienen stock (premium O free)
    available_categories = []
    for category, sub_types in stock.items():
        premium_count = len(sub_types.get("premium", []))
        free_count = len(sub_types.get("free", []))
        
        if premium_count > 0 or free_count > 0:
            available_categories.append(category)
    
    # Construir las opciones basadas en lo que el usuario está escribiendo
    for category in available_categories:
        if current.lower() in category:
            # name se muestra al usuario, value se usa internamente
            choices.append(app_commands.Choice(name=category.upper(), value=category))

    return choices[:25]

# Autocompletado para el campo 'subscription_type' en /generate
async def subscription_type_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    choices = [
        app_commands.Choice(name="Premium", value="premium"),
        app_commands.Choice(name="Gratis (Free)", value="free"),
    ]
    return [choice for choice in choices if current.lower() in choice.value or current.lower() in choice.name.lower()][:25]


# =======================================================
# 5. COMANDOS SLASH (LÓGICA DEL BOT)
# =======================================================

# --- COMANDO /ADD_STOCK (ADMIN) ---
@bot.tree.command(name="add_stock", description="Añade un ítem a una categoría y tipo de stock específico.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    category="El nombre de la categoría (ej: Netflix, HBO).",
    subscription_type="premium o free (gratis).",
    item="El item a añadir (ej: usuario:contraseña o un link)."
)
@app_commands.choices(subscription_type=[
    app_commands.Choice(name="Premium", value="premium"),
    app_commands.Choice(name="Gratis (Free)", value="free"),
])
@app_commands.default_permissions(administrator=True) 
async def add_stock_command(interaction: discord.Interaction, category: str, subscription_type: str, item: str):
    await interaction.response.defer(ephemeral=True)
    
    category = category.lower().strip() 
    subscription_type = subscription_type.lower().strip()
    item = item.strip()

    if not item:
        await interaction.followup.send("❌ El ítem no puede estar vacío.", ephemeral=True)
        return
        
    stock = load_data(STOCK_FILE)
    
    # 1. Asegurar la estructura anidada
    if category not in stock:
        stock[category] = {"premium": [], "free": []}
    
    # 2. Asegurar que el sub-tipo exista (aunque las choices lo garantizan, es un seguro)
    if subscription_type not in stock[category]:
        stock[category][subscription_type] = []

    # 3. Añadir el ítem
    stock[category][subscription_type].append(item)
    save_data(stock, STOCK_FILE)
    
    current_count = len(stock[category][subscription_type])
    
    await interaction.followup.send(
        f"➕ **¡Stock Añadido!** Se agregó un ítem a la categoría **{category.upper()}** ({subscription_type.upper()}).\nStock actual para esta categoría: **{current_count}**", 
        ephemeral=True
    )


# --- COMANDO /GENERATE (USO DE STOCK Y COOLDOWN) ---
@bot.tree.command(name="generate", description="Genera un ítem de la categoría de stock seleccionada.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    category="Selecciona la categoría disponible (ej: Netflix).",
    subscription_type="Selecciona el tipo de suscripción (Premium/Gratis)."
)
@app_commands.autocomplete(
    category=stock_category_autocomplete, 
    subscription_type=subscription_type_autocomplete
) 
async def generate_command(interaction: discord.Interaction, category: str, subscription_type: str):
    await interaction.response.defer(ephemeral=True) 
    
    user_id = str(interaction.user.id)
    cooldowns = load_data(COOLDOWN_FILE)
    stock = load_data(STOCK_FILE)
    category = category.lower().strip()
    subscription_type = subscription_type.lower().strip()

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

    # 2. Verificación de Acceso Premium (Placeholder)
    if subscription_type == "premium":
        # ⚠️ AQUÍ DEBES IMPLEMENTAR LA VERIFICACIÓN DEL ROL PREMIUM ⚠️
        # Ejemplo: Si el usuario NO tiene el rol con ID 123456789...
        # premium_role_id = 123456789012345678 
        # if not any(role.id == premium_role_id for role in interaction.user.roles):
        #    await interaction.followup.send("❌ Necesitas la membresía Premium para generar este stock. Usa /upgrade_premium.", ephemeral=True)
        #    return
        pass # Por ahora permite el acceso para pruebas.

    # 3. Verificación de Stock y Categoría
    if category not in stock or subscription_type not in stock[category] or not stock[category][subscription_type]:
        await interaction.followup.send(
            f"❌ **Stock Agotado** para la categoría **{category.upper()}** ({subscription_type.upper()}).", 
            ephemeral=True
        )
        return

    # 4. Obtener y Eliminar una Cuenta
    try:
        # Usamos .pop(0) para obtener y eliminar el primer ítem de la lista (FIFO)
        account_info = stock[category][subscription_type].pop(0) 
        
        # 5. Actualizar el Cooldown y el Stock
        cooldowns[user_id] = time.time() 
        save_data(cooldowns, COOLDOWN_FILE)
        save_data(stock, STOCK_FILE) 

        # 6. Enviar la Respuesta
        await interaction.followup.send(
            f"✅ ¡{category.upper()} Generada ({subscription_type.upper()})!\n\n||{account_info}||\n\n*(Próximo uso disponible en 1 hora.)*", 
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
    for category, sub_types in stock.items():
        premium_count = len(sub_types.get("premium", []))
        free_count = len(sub_types.get("free", []))
        
        if premium_count > 0 or free_count > 0:
            field_value = ""
            if premium_count > 0:
                field_value += f"**Premium:** {premium_count}\n"
            if free_count > 0:
                field_value += f"**Gratis:** {free_count}\n"
            
            embed.add_field(name=f'🔹 {category.upper()}', value=field_value.strip(), inline=True)
            total_items += premium_count + free_count

    if total_items == 0:
        await interaction.followup.send('⚠️ No hay ítems disponibles en ninguna categoría.', ephemeral=True)
    else:
        embed.set_footer(text=f"Total de ítems disponibles: {total_items}")
        await interaction.followup.send(embed=embed, ephemeral=True)


# --- COMANDO /UPGRADE_PREMIUM (MENSAJE DE PAGO) ---
@bot.tree.command(name="upgrade_premium", description="Obtén la información para pagar la suscripción Premium.", guild=discord.Object(id=GUILD_ID))
async def upgrade_premium_command(interaction: discord.Interaction):
    
    # 🚨 REEMPLAZA ESTOS VALORES CON TU INFORMACIÓN REAL 🚨
    LTC_WALLET = "Ld7inkKGEwsHVDac9P8bZMBwK1oFcSY64Q" 
    NEQUI_NUMBER = "3113184699"
    
    embed = discord.Embed(
        title="✨ ¡Actualiza a Membresía Premium! ✨",
        description="Obtén acceso a todo el stock exclusivo por solo **$3 USD**.",
        color=discord.Color.gold()
    )

    embed.add_field(name="🪙 LTC Wallet (Litecoin)", 
                    value=f"Copia y pega:\n`{LTC_WALLET}`", 
                    inline=False)

    embed.add_field(name="🇨🇴 NEQUI (Solo Colombia)", 
                    value=f"Copia y pega:\n`{NEQUI_NUMBER}`", 
                    inline=False)
                    
    embed.add_field(name="2️⃣ Confirmación de Pago", 
                    value=f"Una vez realizado el pago, envía el **comprobante de transferencia** a <@{CONFIRMATION_USER_ID}>. Tu rol Premium será asignado manualmente.", 
                    inline=False)
    
    embed.set_footer(text="Gracias por tu apoyo. ¡Disfruta el stock!")

    await interaction.response.send_message(embed=embed, ephemeral=False)


# =======================================================
# 6. CONFIGURACIÓN DEL HOSTING 24/7 (REPLIT)
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
# 7. INICIO DEL BOT
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