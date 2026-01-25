import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import asyncio
from datetime import datetime

class OurClansCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = 1464782526492049561
        self.update_clans_task.start()

    async def cog_load(self):
        print("OurClansCog Loaded")
        # Add persistent view for directory buttons
        self.bot.add_view(OurClansView())

    def cog_unload(self):
        self.update_clans_task.cancel()

    @app_commands.command(name="start_directory", description="Initialize the Clan Directory Button Panel")
    async def start_directory(self, interaction: discord.Interaction):
        if interaction.user.id != int(os.getenv("OWNER_ID")):
             await interaction.response.send_message("You are not authorized.", ephemeral=True)
             return
        
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message(f"Channel {self.channel_id} not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="BSN Clan Directory", 
            description="Use the buttons below to find the perfect clan for you!\n\n🛡️ **Main Clans**: Competitive & War Focused\n🎓 **Feeder Clans**: Training & Development\n🌾 **Farming Clans**: Loot & Chill\n🧪 **Trial Clans**: New Additions", 
            color=discord.Color.blue()
        )
        embed.set_footer(text="BlackSpire Nation • Updated Live")
        
        await channel.send(embed=embed, view=OurClansView())
        await interaction.response.send_message("Directory Panel Created!", ephemeral=True)

    async def create_clan_directory(self, clan_tag):
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return False, "Target channel not found."

        clans = await mongo_manager.get_clans()
        clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
        if not clan:
            return False, "Clan not found in DB."

        # creating thread
        try:
            thread = await channel.create_thread(name=f"{clan['name']} ({clan['clan_tag']})", type=discord.ChannelType.public_thread)
            
            # Fetch stats for embed
            embed = await self.build_clan_embed(clan)
            
            # Send and Pin
            msg = await thread.send(embed=embed)
            await msg.pin()
            
            # Save IDs
            await mongo_manager.update_clan_field(clan_tag, "thread_id", str(thread.id))
            await mongo_manager.update_clan_field(clan_tag, "embed_message_id", str(msg.id))
            
            return True, f"Directory created: {thread.mention}"
            
        except Exception as e:
            print(f"Error creating directory for {clan_tag}: {e}")
            return False, str(e)

    async def update_clan_embed(self, clan_tag):
        # Triggered by edits
        clans = await mongo_manager.get_clans()
        clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
        
        if not clan or not clan.get('thread_id') or not clan.get('embed_message_id'):
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel: return
        
        try:
            thread = channel.get_thread(int(clan['thread_id']))
            if not thread:
                # Thread might be archived or deleted
                # logic to recover? user said "Fail silently if a thread was deleted manually and recreate it once."
                # For now just return
                return
                
            msg = await thread.fetch_message(int(clan['embed_message_id']))
            if msg:
                embed = await self.build_clan_embed(clan)
                await msg.edit(embed=embed)
        except Exception as e:
            print(f"Failed to update embed for {clan_tag}: {e}")

    async def build_clan_embed(self, clan):
        # Fetch fresh data
        details = await coc_api.get_clan(clan['clan_tag'])
        
        name = clan.get('name', 'Unknown')
        tag = clan.get('clan_tag', '')
        desc = clan.get('description', 'No description provided.')
        note = clan.get('leaders_note', '')
        logo = clan.get('logo_url', '')
        
        embed = discord.Embed(title=f"{name} ({tag})", description=desc, color=discord.Color.gold())
        if logo:
            embed.set_thumbnail(url=logo)
        
        if details:
            embed.add_field(name="🏆 War League", value=details.war_league.name if details.war_league else "Unranked", inline=True)
            embed.add_field(name="🏰 Capital Hall", value=str(details.capital_hall_level) if hasattr(details, 'capital_hall_level') else "N/A", inline=True)
            embed.add_field(name="👥 Members", value=f"{details.member_count}/50", inline=True)
            embed.add_field(name="⚔️ War Wins", value=str(details.war_wins), inline=True)
            embed.add_field(name="🔥 Win Streak", value=str(details.war_win_streak), inline=True)
            embed.add_field(name="🌍 Location", value=details.location.name if details.location else "Global", inline=True)
        else:
            embed.add_field(name="Status", value="⚠️ API Data Unavailable", inline=False)

        if note:
             embed.add_field(name="📝 Leader's Note", value=note, inline=False)
             
        embed.set_footer(text=f"Part of BlackSpire Nation • Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return embed

    @tasks.loop(hours=1)
    async def update_clans_task(self):
        print("Running Directory Update Loop...")
        clans = await mongo_manager.get_clans()
        for clan in clans:
            if clan.get('thread_id') and clan.get('embed_message_id'):
                try:
                    await self.update_clan_embed(clan['clan_tag'])
                    await asyncio.sleep(2) # rate limit safe
                except Exception as e:
                    print(f"Loop update error for {clan['clan_tag']}: {e}")

    @update_clans_task.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

class OurClansView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def show_clans(self, interaction, category):
        clans = await mongo_manager.get_clans()
        # Filter by category and status='family' (unless category is trial)
        # Wait, requirement: "Query clans where status = family category = <button category> ... Trial Button show all clans where status = trial"
        
        matches = []
        if category == "Trial":
            matches = [c for c in clans if c.get('status', '').lower() == 'trial']
        else:
            matches = [c for c in clans if c.get('status', '').lower() == 'family' and c.get('category', '').lower() == category.lower()]
            
        if not matches:
            await interaction.response.send_message(f"No clans found in **{category}** category.", ephemeral=True)
            return
            
        desc = ""
        for c in matches:
            thread_id = c.get('thread_id')
            link = f"https://discord.com/channels/{interaction.guild_id}/{interaction.channel_id}/{thread_id}" if thread_id else "#"
            desc += f"• **{c['name']}** ([More Info]({link}))\n"
            
        embed = discord.Embed(title=f"{category} Clans", description=desc, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Main Clans", custom_id="dir_main", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def main_clans(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_clans(interaction, "Main")

    @discord.ui.button(label="Feeder Clans", custom_id="dir_feeder", style=discord.ButtonStyle.secondary, emoji="🎓")
    async def feeder_clans(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_clans(interaction, "Feeder")

    @discord.ui.button(label="Farming Clans", custom_id="dir_farming", style=discord.ButtonStyle.success, emoji="🌾")
    async def farming_clans(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_clans(interaction, "Farming")

    @discord.ui.button(label="Trial Clans", custom_id="dir_trial", style=discord.ButtonStyle.danger, emoji="🧪")
    async def trial_clans(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_clans(interaction, "Trial")

async def setup(bot):
    await bot.add_cog(OurClansCog(bot))
