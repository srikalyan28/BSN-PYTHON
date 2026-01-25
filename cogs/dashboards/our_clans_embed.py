import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import coc
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
            embeds, file = await self.build_clan_embed(clan)
            
            # Send and Pin
            if embeds and file:
                msg = await thread.send(embeds=embeds, file=file)
                await msg.pin()
            else:
                return False, "Failed to build embed/file."
            
            # Save IDs
            await mongo_manager.update_clan_field(clan_tag, "thread_id", str(thread.id))
            await mongo_manager.update_clan_field(clan_tag, "embed_message_id", str(msg.id))
            
            return True, f"Directory created: {thread.mention}"
            
        except Exception as e:
            print(f"Error creating directory for {clan_tag}: {e}")
            return False, str(e)

    async def delete_clan_directory(self, clan_tag):
        # Called by ClanDashboard to clean up
        channel = self.bot.get_channel(self.channel_id)
        if not channel: return

        clans = await mongo_manager.get_clans()
        clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
        
        if clan and clan.get('thread_id'):
            try:
                thread = channel.get_thread(int(clan['thread_id']))
                if thread:
                     await thread.delete()
                     print(f"Deleted directory thread for {clan_tag}")
            except Exception as e:
                print(f"Error deleting thread for {clan_tag}: {e}")


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
                embeds, file = await self.build_clan_embed(clan)
                if embeds and file:
                    # To update attachments, we must pass the new file and clear the old ones?
                    # edit(attachments=[...]) replaces them.
                    await msg.edit(embeds=embeds, attachments=[file])
        except Exception as e:
            print(f"Failed to update embed for {clan_tag}: {e}")

    async def build_clan_embed(self, clan):
        # Fetch fresh data
        details = await coc_api.get_clan(clan['clan_tag'])
        if not details:
            return None, None

        name = details.name
        tag = details.tag
        in_game_desc = details.description
        leaders_note = clan.get('leaders_note', '')
        
        # Images
        badge_url = details.badge.url
        custom_logo = clan.get('logo_url', '')
        
        # Determine Footer Asset based on Category
        category = clan.get('category', 'Trial').lower()
        footer_file = "Gray_Footer.png"
        
        if category == "main": footer_file = "Red_Footer.png"
        elif category == "feeder": footer_file = "Blue_Footer (1).png"
        elif category == "farming": footer_file = "Green_Footer.png"
        elif category == "trial": footer_file = "Orange_Footer.png"
        
        # Asset Path
        # Use relative path compatible with both Windows and Linux container
        asset_path = os.path.join(os.getcwd(), "assets", footer_file)
        file = discord.File(asset_path, filename=footer_file)

        # --- Main Embed (Content + Logo) ---
        embed = discord.Embed(description="", color=discord.Color.dark_theme())
        
        # Author: Name (Tag)
        embed.set_author(name=f"{name} ({tag})", icon_url=badge_url)
        
        # Thumbnail: Badge (Always Badge per user req "same like this exactly with clan badge as showing here")
        embed.set_thumbnail(url=badge_url)
        
        # Main Stats Block
        stats_lines = []
        stats_lines.append(f"🚩 **Level {details.level}**   👥 **{details.member_count}/50**")
        
        location = details.location.name if details.location else "Global"
        stats_lines.append(f"🌍 **{location}**")
        
        # War Stats
        streak = details.war_win_streak
        stats_lines.append(f"⚔️ **W {details.war_wins}** / **D {details.war_ties}** / **L {details.war_losses}** (Streak: {streak})")
        
        # Leagues
        war_league = details.war_league.name if details.war_league else "Unranked"
        stats_lines.append(f"🏆 **{war_league}**")
        
        # Capital
        ch_level = "N/A"
        ch_trophies = "0"
        
        # Safe access for Capital Hall
        ch_lvl_val = getattr(details, "capital_hall_level", None)
        if ch_lvl_val:
             ch_level = str(ch_lvl_val)
             # Try to get points
             ch_trophies = str(getattr(details, "clan_capital_points", 0))
        elif hasattr(details, 'capital_districts'):
             # Logic to find CH level from districts if needed
             districts = details.capital_districts
             for d in districts:
                 if d.name == "Capital Peak":
                     ch_level = str(d.hall_level)
                     break
        
        stats_lines.append(f"🛖 **CH {ch_level}**   💎 **{ch_trophies}** Trophies")
        
        leader_name = "Unknown"
        # Find leader
        for member in details.members:
            if member.role == coc.Role.leader:
                leader_name = member.name
                break
        stats_lines.append(f"👑 **{leader_name}**")
        
        embed.description = "\n".join(stats_lines)
        
        # Townhall Breakdown
        th_counts = {}
        for m in details.members:
            th = m.town_hall
            th_counts[th] = th_counts.get(th, 0) + 1
        
        sorted_ths = sorted(th_counts.items(), key=lambda x: x[0], reverse=True)
        th_str_parts = []
        for th, count in sorted_ths:
             th_str_parts.append(f"**TH{th}**: {count}")
        
        if th_str_parts:
             embed.add_field(name="Townhall Breakdown", value=" | ".join(th_str_parts), inline=False)

             
        # Big Image: Custom Logo (Dragon Shield etc) - Main Embed
             
        # Big Image: Custom Logo (Dragon Shield etc) - Main Embed
        if custom_logo:
             embed.set_image(url=custom_logo)
        
        # Add Main Embed to list
        embed_list = [embed]

        # --- "About Clan" Embed ---
        if in_game_desc:
            desc_embed = discord.Embed(title="About Clan", description=in_game_desc, color=discord.Color.dark_theme())
            embed_list.append(desc_embed)

        # --- "Leader's Note" Embed ---
        if leaders_note:
            note_embed = discord.Embed(title="Leader's Note", description=leaders_note, color=discord.Color.dark_theme())
            embed_list.append(note_embed)

        # --- Footer Embed (Banner + Apply Link) ---
        footer_embed = discord.Embed(description="**Apply to join:** <#1440648795972046848>", color=discord.Color.dark_theme())
        footer_embed.set_image(url=f"attachment://{footer_file}")
        footer_embed.set_footer(text=f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        embed_list.append(footer_embed)

        return embed_list, file

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
        matches = []
        if category == "Trial":
            matches = [c for c in clans if (c.get('status') or '').lower() == 'trial']
        else:
            matches = [c for c in clans if (c.get('status') or '').lower() == 'family' and (c.get('category') or '').lower() == category.lower()]
            
        if not matches:
            await interaction.response.send_message(f"No clans found in **{category}** category.", ephemeral=True)
            return
            
        # Send Dropdown View
        view = CategorySelectView(matches, category, self, interaction.guild)
        await interaction.response.send_message(f"**{category} Clans**\nSelect a clan to view details:", view=view, ephemeral=True)

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

class CategorySelectView(discord.ui.View):
    def __init__(self, clans, category, cog_view, guild):
        super().__init__(timeout=180) # Ephemeral views expire
        self.clans = clans
        self.category = category
        self.cog_view = cog_view 
        self.guild = guild
        
        # Sort by CWL
        cwl_order = {
            "Champion League I": 18, "Champion League II": 17, "Champion League III": 16,
            "Master League I": 15, "Master League II": 14, "Master League III": 13,
            "Crystal League I": 12, "Crystal League II": 11, "Crystal League III": 10,
            "Gold League I": 9, "Gold League II": 8, "Gold League III": 7,
            "Silver League I": 6, "Silver League II": 5, "Silver League III": 4,
            "Bronze League I": 3, "Bronze League II": 2, "Bronze League III": 1,
            "Unranked": 0
        }
        def get_rank_val(clan):
            league = clan.get('war_league', 'Unranked')
            return cwl_order.get(league, 0)
        self.clans.sort(key=get_rank_val, reverse=True)
        
        options = []
        for c in self.clans:
            # Emoji Logic: Try to find a custom emoji matching Clan Name or Tag
            # Sanitize name: "Indo Clan Lords" -> "indoclanlords"
            emoji = "🛡️" # Default
            sanitized_name = c['name'].replace(" ", "").lower()
            sanitized_tag = c['clan_tag'].replace("#", "").lower()
            
            # Search guild emojis
            if self.guild:
                found_emoji = discord.utils.get(self.guild.emojis, name=sanitized_name)
                if not found_emoji:
                    found_emoji = discord.utils.get(self.guild.emojis, name=sanitized_tag)
                
                if found_emoji:
                    emoji = found_emoji

            # Description (League only, no Tag)
            desc = f"{c.get('war_league', 'Unranked')}"
            options.append(discord.SelectOption(label=c['name'], value=c['clan_tag'], description=desc, emoji=emoji))
            
        self.select_clan.options = options[:25]

    @discord.ui.select(placeholder="Select a clan to view details...")
    async def select_clan(self, interaction: discord.Interaction, select: discord.ui.Select):
        clan_tag = select.values[0]
        
        # Fetch Cog to use builder
        cog = interaction.client.get_cog("OurClansCog")
        if not cog:
            await interaction.response.send_message("System Error.", ephemeral=True)
            return
            
        # Get clan data from list
        clan = next((c for c in self.clans if c['clan_tag'] == clan_tag), None)
        if not clan: return
        
        await interaction.response.defer(ephemeral=True)
        
        embeds, file = await cog.build_clan_embed(clan)
        if not embeds:
             await interaction.followup.send("Failed to load clan details.", ephemeral=True)
             return
             
        # Add Jump Button
        view = discord.ui.View()
        # Add Join Button
        view = discord.ui.View()
        
        # Priority: Stored 'clan_link' -> Generated CoC Link
        join_url = clan.get('clan_link')
        if not join_url:
             # Fallback to standard deep link
             clean_tag = clan['clan_tag'].replace("#", "")
             join_url = f"https://link.clashofclans.com/en?action=OpenClanProfile&tag={clean_tag}"
             
        view.add_item(discord.ui.Button(label="Visit Clan", url=join_url, style=discord.ButtonStyle.link))
        
        # Send
        await interaction.followup.send(embeds=embeds, file=file, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(OurClansCog(bot))
