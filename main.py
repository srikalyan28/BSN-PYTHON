import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.mongo_manager import mongo_manager

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

class BlackspireBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        await mongo_manager.connect()
        
        # Load cogs
        for root, dirs, files in os.walk("cogs"):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    path = os.path.join(root, file)
                    module_path = path.replace(os.sep, ".")[:-3]
                    try:
                        await self.load_extension(module_path)
                        print(f"Loaded extension: {module_path}")
                    except Exception as e:
                        print(f"Failed to load extension {module_path}: {e}")

        await self.tree.sync()
        print("Synced slash commands.")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

bot = BlackspireBot()

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found in .env")
    else:
        print(f"Owner ID from env: {os.getenv('OWNER_ID')}")
        bot.run(BOT_TOKEN)
