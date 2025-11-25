import discord
from discord.ext import commands
from discord import app_commands
import os

class OwnerCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="say", description="Make the bot say something (Owner only).")
    @app_commands.describe(message="The message to send")
    async def say(self, interaction: discord.Interaction, message: str):
        owner_id = os.getenv("OWNER_ID")
        
        # Check if OWNER_ID is set and matches the user
        if not owner_id or interaction.user.id != int(owner_id):
            await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
            return

        # Send the message to the channel
        await interaction.channel.send(message)
        
        # Confirm to the user (ephemeral so no one else sees)
        await interaction.response.send_message("Message sent.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(OwnerCommandsCog(bot))
