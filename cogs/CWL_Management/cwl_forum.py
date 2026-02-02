import discord
from discord import app_commands
from discord.ext import commands
from .cwl_models import cwl_models
from .cwl_permissions import cwl_permissions
from .cwl_utils import cwl_utils
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import asyncio
import re

async def setup(bot):
    await bot.add_cog(CWLForumCog(bot))

class CWLForumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    cwl_group = app_commands.Group(name="cwl", description="CWL Management System")

    @cwl_group.command(name="forum", description="Start/Resume CWL Forum Wizard")
    async def cwl_forum(self, interaction: discord.Interaction):
        if not cwl_permissions.is_leader_or_co(interaction) and not await cwl_permissions.is_manager(interaction) and not await cwl_permissions.is_rep(interaction, (await cwl_models.get_active_season())['season'] if await cwl_models.get_active_season() else 'N/A'):
             await interaction.response.send_message("❌ You are not a leader or rep.", ephemeral=True)
             return

        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("❌ No active season set.", ephemeral=True)
            return

        clans = await mongo_manager.get_clans()
        view = CWLForumClanSelectView(clans, season['season'])
        await interaction.response.send_message("Select a clan to manage:", view=view, ephemeral=True)

class CWLForumClanSelectView(discord.ui.View):
    def __init__(self, clans, season):
        super().__init__()
        options = [discord.SelectOption(label=c['name'], value=c['clan_tag']) for c in clans[:25]]
        self.add_item(CWLForumClanSelect(options, season))

class CWLForumClanSelect(discord.ui.Select):
    def __init__(self, options, season):
        super().__init__(placeholder="Select Clan...", options=options)
        self.season = season

    async def callback(self, interaction: discord.Interaction):
        clan_tag = self.values[0]
        # Access Check
        can_access = False
        if cwl_permissions.is_owner(interaction): can_access = True
        elif await cwl_permissions.is_manager(interaction): can_access = True
        elif await cwl_permissions.is_rep(interaction, self.season, clan_tag): can_access = True
        else:
             clans = await mongo_manager.get_clans()
             clan_data = next((c for c in clans if c['clan_tag'] == clan_tag), None)
             if clan_data and clan_data.get('leadership_role_id'):
                 role = interaction.guild.get_role(int(clan_data['leadership_role_id']))
                 if role and role in interaction.user.roles:
                     can_access = True
             elif cwl_permissions.is_leader_or_co(interaction):
                 can_access = True
        
        if not can_access:
             await interaction.response.send_message("❌ Access Denied for this clan.", ephemeral=True)
             return

        clan_data = next(c for c in await mongo_manager.get_clans() if c['clan_tag'] == clan_tag)
        channel = await self.ensure_channel(interaction.guild, clan_data, interaction.user)
        await interaction.response.send_message(f"✅ Navigate to {channel.mention} to continue.", ephemeral=True)
        await self.start_wizard(channel, self.season, clan_tag, clan_data['name'])

    async def ensure_channel(self, guild, clan_data, user):
        channel_name = f"cwl-{clan_data.get('clan_abbreviation', clan_data['name'].replace(' ', '-')).lower()}"
        existing = discord.utils.get(guild.channels, name=channel_name)
        if existing: return existing

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if clan_data.get('leadership_role_id'):
            role = guild.get_role(int(clan_data['leadership_role_id']))
            if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
        category = guild.get_channel(1467896783412920506)
        return await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)

    async def start_wizard(self, channel, season, clan_tag, clan_name):
        embed = discord.Embed(title=f"CWL Wizard: {clan_name}", description=f"Season: **{season}**", color=discord.Color.gold())
        meta = await cwl_models.get_forum_metadata(season, clan_tag) or {}
        
        embed.add_field(name="1. Plan", value=meta.get('goal', "Pending"), inline=True)
        embed.add_field(name="2. Master", value=meta.get('master', "Pending"), inline=True)
        embed.add_field(name="3. Format", value=meta.get('format', "Pending"), inline=True)
        
        # Count stats
        overflows = await cwl_models.get_overflows(season, source_clan=clan_tag)
        embed.add_field(name="4. Overflows", value=f"{len(overflows)} Added", inline=True)
        
        needs = await cwl_models.get_requirements(season, clan_tag)
        requirements_str = ", ".join([f"TH{n['th_level']}x{n['count_needed']}" for n in needs]) if needs else "None"
        embed.add_field(name="5. Needs", value=requirements_str, inline=True)
        
        view = WizardMainView(season, clan_tag, clan_name)
        await channel.send(embed=embed, view=view)

class WizardMainView(discord.ui.View):
    def __init__(self, season, clan_tag, clan_name):
        super().__init__(timeout=None)
        self.season = season; self.clan_tag = clan_tag; self.clan_name = clan_name

    @discord.ui.button(label="1. Goal", style=discord.ButtonStyle.primary, row=0)
    async def goal(self, interaction, button):
        await interaction.response.send_message("Select Goal:", view=GoalSelectView(self.season, self.clan_tag), ephemeral=True)

    @discord.ui.button(label="2. Master", style=discord.ButtonStyle.primary, row=0)
    async def master(self, interaction, button):
        await interaction.response.send_modal(MasterModal(self.season, self.clan_tag))

    @discord.ui.button(label="3. Format", style=discord.ButtonStyle.primary, row=0)
    async def format(self, interaction, button):
        await interaction.response.send_message("Select Format:", view=FormatSelectView(self.season, self.clan_tag), ephemeral=True)

    @discord.ui.button(label="4. Overflows", style=discord.ButtonStyle.secondary, row=1)
    async def overflows(self, interaction, button):
        await interaction.response.send_message("Select Town Halls available to overflow:", view=OverflowTHSelectView(self.season, self.clan_tag), ephemeral=True)

    @discord.ui.button(label="5. Needs", style=discord.ButtonStyle.secondary, row=1)
    async def needs(self, interaction, button):
        await interaction.response.send_message("Do you need help?", view=NeedsValuesView(self.season, self.clan_tag), ephemeral=True)

class GoalSelectView(discord.ui.View):
    def __init__(self, season, clan_tag): super().__init__(); self.season=season; self.clan_tag=clan_tag
    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success)
    async def p(self, i, b): await self.save(i, "Promote")
    @discord.ui.button(label="Hold", style=discord.ButtonStyle.gray)
    async def h(self, i, b): await self.save(i, "Hold")
    @discord.ui.button(label="Casual", style=discord.ButtonStyle.danger)
    async def s(self, i, b): await self.save(i, "Casual")
    async def save(self, i, val):
        await cwl_models.save_forum_metadata(self.season, self.clan_tag, {"goal": val})
        await i.response.send_message(f"Goal set to {val}", ephemeral=True)

class MasterModal(discord.ui.Modal, title="CWL Master"):
    name = discord.ui.TextInput(label="Username")
    def __init__(self, season, clan_tag): super().__init__(); self.season=season; self.clan_tag=clan_tag
    async def on_submit(self, i): 
        await cwl_models.save_forum_metadata(self.season, self.clan_tag, {"master": self.name.value})
        await i.response.send_message(f"Master set to {self.name.value}", ephemeral=True)

class FormatSelectView(discord.ui.View):
    def __init__(self, season, clan_tag): super().__init__(); self.season=season; self.clan_tag=clan_tag
    @discord.ui.button(label="15v15", style=discord.ButtonStyle.primary)
    async def f15(self, i, b): await self.save(i, "15v15")
    @discord.ui.button(label="30v30", style=discord.ButtonStyle.primary)
    async def f30(self, i, b): await self.save(i, "30v30")
    async def save(self, i, val): 
        await cwl_models.save_forum_metadata(self.season, self.clan_tag, {"format": val})
        await i.response.send_message(f"Format set to {val}", ephemeral=True)

# --- OVERFLOWS ---
class OverflowTHSelectView(discord.ui.View):
    def __init__(self, season, clan_tag):
        super().__init__()
        options = [discord.SelectOption(label=f"TH {i}", value=str(i)) for i in range(18, 9, -1)]
        self.add_item(OverflowTHSelect(options, season, clan_tag))

class OverflowTHSelect(discord.ui.Select):
    def __init__(self, options, season, clan_tag):
        super().__init__(placeholder="Select Available THs", min_values=1, max_values=len(options), options=options)
        self.season = season; self.clan_tag = clan_tag

    async def callback(self, interaction: discord.Interaction):
        await cwl_models.clear_clan_overflows(self.season, self.clan_tag)
        selected_ths = [int(v) for v in self.values]
        selected_ths.sort(reverse=True)
        # We need to collect counts. Discord Modals allows 5 inputs.
        # If <= 5, one modal. If > 5, chain them? 
        # Simpler: Loop text input via channel or just one modal limiting to top 5?
        # User explicitly asked for dropdown -> form (Modal).
        # We will split into chunks of 5 if needed.
        await interaction.response.send_modal(OverflowCountModal(self.season, self.clan_tag, selected_ths))

class OverflowCountModal(discord.ui.Modal):
    def __init__(self, season, clan_tag, ths, index=0):
        super().__init__(title="Overflow Counts")
        self.season = season; self.clan_tag = clan_tag; self.ths = ths; self.index = index
        self.current_chunk = ths[index:index+5]
        
        for th in self.current_chunk:
            self.add_item(discord.ui.TextInput(label=f"TH {th} Count", placeholder="0", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        # Store counts in a temporary state or pass them along?
        # We need to eventually ask for tags.
        # Let's start the Tag Entry Process immediately after counts.
        counts = {}
        for i, item in enumerate(self.children):
            th = self.current_chunk[i]
            try:
                counts[th] = int(item.value)
            except:
                counts[th] = 0
        
        # Check if more THs remain
        if self.index + 5 < len(self.ths):
             await interaction.response.send_modal(OverflowCountModal(self.season, self.clan_tag, self.ths, self.index+5))
             return
             
        # All counts collected. Start Tag Entry Loop.
        await interaction.response.send_message("✅ Counts recorded. Starting Tag Entry...", ephemeral=True)
        asyncio.create_task(self.start_tag_entry(interaction.channel, counts))

    async def start_tag_entry(self, channel, counts):
        # Iterate High to Low TH
        for th in sorted(counts.keys(), reverse=True):
            count = counts[th]
            if count == 0: continue
            
            await channel.send(f"🔹 **Overflow Entry: TH {th}** ({count} players)")
            for i in range(count):
                await channel.send(f"Enter Tag for **TH{th}** Player #{i+1}:")
                
                valid = False
                while not valid:
                    def check(m): return m.channel.id == channel.id and not m.author.bot
                    try:
                        msg = await channel.client.wait_for('message', check=check, timeout=120)
                        tag = msg.content.upper().replace("#", "")
                        if not tag: continue
                        
                        # Validate API
                        player = await coc_api.get_player(tag)
                        if not player:
                            await channel.send("❌ Invalid Tag. Try again:")
                            continue
                            
                        # Validate TH
                        if player.town_hall != th:
                             await channel.send(f"⚠️ Warning: Player is TH{player.town_hall}, but you are filling TH{th} slot. Proceed? (yes/no)")
                             conf = await channel.client.wait_for('message', check=check, timeout=30)
                             if conf.content.lower() != "yes":
                                 await channel.send("Cancelled. Enter correct tag:")
                                 continue
                        
                        # Save
                        await cwl_models.add_overflow(self.season, self.clan_tag, player.tag, player.name, player.town_hall)
                        await channel.send(f"✅ Added {player.name} (TH{player.town_hall})")
                        valid = True
                        
                    except asyncio.TimeoutError:
                        await channel.send("timeout.")
                        return

        await channel.send("✅ **All Overflows Recorded!**")


# --- NEEDS ---
class NeedsValuesView(discord.ui.View):
    def __init__(self, season, clan_tag): super().__init__(); self.season=season; self.clan_tag=clan_tag
    @discord.ui.button(label="No Help Needed", style=discord.ButtonStyle.success)
    async def n(self, i, b): 
        await cwl_models.clear_clan_requirements(self.season, self.clan_tag)
        await i.response.send_message("Recorded: No Help.", ephemeral=True)
    @discord.ui.button(label="Need Help", style=discord.ButtonStyle.primary)
    async def y(self, i, b):
        options = [discord.SelectOption(label=f"TH {x}", value=str(x)) for x in range(18, 9, -1)]
        await i.response.send_message("Select Needed THs:", view=NeedsSelectView(self.season, self.clan_tag, options), ephemeral=True)

class NeedsSelectView(discord.ui.View):
    def __init__(self, season, clan_tag, options):
        super().__init__()
        self.add_item(NeedsSelect(options, season, clan_tag))

class NeedsSelect(discord.ui.Select):
    def __init__(self, options, season, clan_tag): super().__init__(placeholder="Select THs", min_values=1, max_values=len(options), options=options); self.season=season; self.clan_tag=clan_tag
    async def callback(self, i):
        selected_ths = [int(v) for v in self.values]
        selected_ths.sort(reverse=True)
        try:
            await i.response.send_modal(NeedsCountModal(self.season, self.clan_tag, selected_ths))
        except Exception as e:
            await i.response.send_message(f"Error: {e}", ephemeral=True)

class NeedsCountModal(discord.ui.Modal):
    def __init__(self, season, clan_tag, ths, index=0):
        super().__init__(title="Requirement Counts")
        self.season = season; self.clan_tag = clan_tag; self.ths = ths; self.index = index
        self.current_chunk = ths[index:index+5]
        for th in self.current_chunk:
            self.add_item(discord.ui.TextInput(label=f"TH {th} Needed", placeholder="0", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        for idx, item in enumerate(self.children):
            th = self.current_chunk[idx]
            try: count = int(item.value)
            except: count = 0
            await cwl_models.set_requirement(self.season, self.clan_tag, th, count)
        
        if self.index + 5 < len(self.ths):
             await interaction.response.send_modal(NeedsCountModal(self.season, self.clan_tag, self.ths, self.index+5))
        else:
             await interaction.response.send_message("✅ Requirements Saved!", ephemeral=True)
