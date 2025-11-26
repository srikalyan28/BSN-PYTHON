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

    @commands.command(name="sync_tree")
    async def sync_tree(self, ctx):
        owner_id = os.getenv("OWNER_ID")
        if not owner_id or ctx.author.id != int(owner_id):
            return
        
        await ctx.send("Syncing...")
        try:
            await self.bot.tree.sync()
            await ctx.send("✅ Slash commands synced globally.")
        except Exception as e:
            await ctx.send(f"❌ Sync failed: {e}")

    @app_commands.command(name="force_sync", description="Force sync slash commands (Owner only).")
    async def force_sync(self, interaction: discord.Interaction):
        owner_id = os.getenv("OWNER_ID")
        if not owner_id or interaction.user.id != int(owner_id):
            await interaction.response.send_message("❌ Not authorized.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.tree.sync()
            await interaction.followup.send("✅ Slash commands synced globally.")
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}")

    @app_commands.command(name="force_sync", description="Force sync slash commands (Owner only).")
    async def force_sync(self, interaction: discord.Interaction):
        owner_id = os.getenv("OWNER_ID")
        if not owner_id or interaction.user.id != int(owner_id):
            await interaction.response.send_message("❌ Not authorized.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.tree.sync()
            await interaction.followup.send("✅ Slash commands synced globally.")
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}")

async def setup(bot):
    await bot.add_cog(OwnerCommandsCog(bot))
