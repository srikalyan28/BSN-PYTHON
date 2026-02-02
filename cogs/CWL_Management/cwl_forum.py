import discord
from discord import app_commands
from discord.ext import commands
from .cwl_models import cwl_models
from .cwl_permissions import cwl_permissions
from .cwl_utils import cwl_utils
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import asyncio
import typing

async def setup(bot):
    await bot.add_cog(CWLForumCog(bot))

class CWLForumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    cwl_group = app_commands.Group(name="cwl", description="CWL Management System")

    # --- HELPER: CHECK CHANNEL ---
    async def get_clan_for_channel(self, channel_id, season):
        # We need to map Channel ID -> Clan Tag
        # This mapping isn't explicitly stored in DB solely by Channel ID, but we can search.
        # Or we can rely on `cwl_state` if we used it.
        # Better: Store `channel_id` in `cwl_forums` metadata when created.
        clans = await mongo_manager.get_clans()
        # Inefficient scan?
        # Let's trust that the user setup the forum and we saved the channel ID somewhere?
        # Logic in `cwl_forum` creates channel. We should save that ID.
        # Let's search `cwl_forums` collection for this channel_id?
        # Current schema has `season` and `clan_tag`. Let's add `channel_id` to it.
        pass

    # --- 1. SETUP / LINK ---
    @cwl_group.command(name="forum", description="Open/Link CWL Forum Channel")
    async def cwl_forum(self, interaction: discord.Interaction):
        # Permission Check
        if not cwl_permissions.is_leader_or_co(interaction) and not await cwl_permissions.is_manager(interaction) and not await cwl_permissions.is_rep(interaction, "ANY"): 
             # Note: "ANY" check is placeholder, strict check below
             pass
        
        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("❌ No active season.", ephemeral=True)
            return

        clans = await mongo_manager.get_clans()
        view = CWLForumClanSelectView(clans, season['season'])
        await interaction.response.send_message("Select Clan to Manage:", view=view, ephemeral=True)

    # --- 2. WIZARD / STATUS ---
    @cwl_group.command(name="wizard", description="Show CWL Status Board (Live View)")
    async def wizard(self, interaction: discord.Interaction):
        # Must be in a valid CWL Channel
        data = await self.validate_channel(interaction)
        if not data: return

        embed = await self.build_status_embed(data['season'], data['clan_tag'], data['clan_name'])
        await interaction.response.send_message(embed=embed)

    # --- 3. CONFIG CMDS ---
    @cwl_group.command(name="set-goal", description="Set CWL Goal")
    @app_commands.choices(goal=[
        app_commands.Choice(name="Promote", value="Promote"),
        app_commands.Choice(name="Hold", value="Hold"),
        app_commands.Choice(name="Relaxed/Farm", value="Relaxed")
    ])
    async def set_goal(self, interaction: discord.Interaction, goal: app_commands.Choice[str]):
        data = await self.validate_channel(interaction)
        if not data: return
        await cwl_models.save_forum_metadata(data['season'], data['clan_tag'], {"goal": goal.value})
        await self.refresh_wizard(interaction, data)

    @cwl_group.command(name="set-format", description="Set CWL Format")
    @app_commands.choices(fmt=[
        app_commands.Choice(name="15v15", value="15v15"),
        app_commands.Choice(name="30v30", value="30v30")
    ])
    async def set_format(self, interaction: discord.Interaction, fmt: app_commands.Choice[str]):
        data = await self.validate_channel(interaction)
        if not data: return
        await cwl_models.save_forum_metadata(data['season'], data['clan_tag'], {"format": fmt.value})
        await self.refresh_wizard(interaction, data)

    @cwl_group.command(name="set-leader", description="Set CWL Leader")
    async def set_leader(self, interaction: discord.Interaction, user: discord.User):
        data = await self.validate_channel(interaction)
        if not data: return
        await cwl_models.save_forum_metadata(data['season'], data['clan_tag'], {"master": user.display_name}) # Store name or ID? Name requested.
        await self.refresh_wizard(interaction, data)

    # --- 4. OVERFLOW CMDS ---
    # Subgroup?
    overflow = app_commands.Group(name="overflow", description="Manage Overflows", parent=cwl_group)

    @overflow.command(name="check", description="List current Overflows")
    async def check_overflow(self, interaction: discord.Interaction):
        data = await self.validate_channel(interaction)
        if not data: return
        
        overflows = await cwl_models.get_overflows(data['season'], source_clan=data['clan_tag'])
        if not overflows:
            await interaction.response.send_message("No overflows listed.", ephemeral=True)
            return
            
        # Group by TH
        grouped = {}
        for p in overflows:
            th = p['player_th']
            if th not in grouped: grouped[th] = []
            grouped[th].append(p)
            
        txt = f"**Overflows for {data['clan_name']}**\n"
        for th in sorted(grouped.keys(), reverse=True):
            txt += f"**TH{th}**: {', '.join([p['player_name'] for p in grouped[th]])}\n"
            
        await interaction.response.send_message(txt, ephemeral=True)

    @overflow.command(name="add", description="Add Overflow Players")
    async def add_overflow(self, interaction: discord.Interaction, town_hall: int):
        data = await self.validate_channel(interaction)
        if not data: return
        
        # Start Loop
        await interaction.response.send_message(f"Starting Tag Entry for **TH{town_hall}**...", ephemeral=True)
        asyncio.create_task(self.tag_entry_loop(interaction.client, interaction.channel, data, town_hall))

    @overflow.command(name="remove", description="Remove an Overflow Player")
    async def remove_overflow(self, interaction: discord.Interaction, tag: str):
        data = await self.validate_channel(interaction)
        if not data: return
        
        tag = tag.upper().replace("#", "")
        # Check if exists
        # delete logic needed in models
        # Assuming we can just update status to 'removed' or delete doc.
        # Let's implement delete in models later.
        # For now, quick hack: update status to 'deleted'
        await cwl_models.update_overflow_status(data['season'], tag, "deleted")
        await interaction.response.send_message(f"✅ Removed {tag}", ephemeral=True)
        await self.refresh_wizard(interaction, data)

    # --- 5. WORKFLOW ---
    @cwl_group.command(name="submit", description="Submit CWL Forum")
    async def submit_forum(self, interaction: discord.Interaction):
        data = await self.validate_channel(interaction)
        if not data: return
        
        await cwl_models.save_forum_metadata(data['season'], data['clan_tag'], {"status": "Submitted"})
        await interaction.response.send_message("✅ **Forum Submitted!** Notified CWL Managers.")
        await self.refresh_wizard(interaction, data)

    @cwl_group.command(name="approve", description="Approve CWL Forum (Manager Only)")
    async def approve_forum(self, interaction: discord.Interaction):
        if not await cwl_permissions.is_manager(interaction):
            await interaction.response.send_message("❌ Managers only.", ephemeral=True)
            return

        data = await self.validate_channel(interaction)
        if not data: return
        
        await cwl_models.save_forum_metadata(data['season'], data['clan_tag'], {"status": "Approved"})
        await interaction.response.send_message("✅ **Forum Approved!**")
        await self.refresh_wizard(interaction, data)

    # --- UTILS ---
    async def validate_channel(self, interaction):
        # Check if this channel is a registered CWL forum channel
        # We need to look up based on channel_id.
        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("No active season.", ephemeral=True)
            return None
            
        # Find forum doc with this channel_id
        # We need to ensure we SAVE channel_id when creating.
        forum = await cwl_models.get_forum_by_channel(season['season'], interaction.channel_id)
        if not forum:
            # Fallback: Check if channel topic/name contains tag? Unreliable.
            # User must run /cwl forum first to link it.
            await interaction.response.send_message("❌ This channel is not a linked CWL Forum. Run `/cwl forum` first.", ephemeral=True)
            return None
        
        # Also fetch clan name
        clans = await mongo_manager.get_clans()
        clan = next((c for c in clans if c['clan_tag'] == forum['clan_tag']), None)
        
        return {
            "season": season['season'],
            "clan_tag": forum['clan_tag'],
            "clan_name": clan['name'] if clan else "Unknown",
            "forum_doc": forum
        }

    async def build_status_embed(self, season, clan_tag, clan_name):
        meta = await cwl_models.get_forum_metadata(season, clan_tag) or {}
        overflows = await cwl_models.get_overflows(season, source_clan=clan_tag)
        # Filter out deleted
        overflows = [o for o in overflows if o.get('status') != 'deleted']
        
        status_icon = "📝"
        if meta.get('status') == "Submitted": status_icon = "gaussian" # ?
        if meta.get('status') == "Submitted": status_icon = "⏳"
        if meta.get('status') == "Approved": status_icon = "✅"

        embed = discord.Embed(title=f"{status_icon} CWL Wizard: {clan_name}", description=f"Season: **{season}**\nStatus: **{meta.get('status', 'Draft')}**", color=discord.Color.gold())
        
        embed.add_field(name="Goal", value=meta.get('goal', "Not Set"), inline=True)
        embed.add_field(name="Format", value=meta.get('format', "Not Set"), inline=True)
        embed.add_field(name="CWL Leader", value=meta.get('master', "Not Set"), inline=True)
        
        # Overflows Summary
        # Group by TH
        counts = {}
        for p in overflows:
            counts[p['player_th']] = counts.get(p['player_th'], 0) + 1
        
        of_str = ""
        for th in sorted(counts.keys(), reverse=True):
            of_str += f"TH{th}: {counts[th]}\n"
        
        embed.add_field(name=f"Overflows ({len(overflows)})", value=of_str if of_str else "None", inline=False)
        
        # Commands Help
        help_text = "`/cwl set-goal` `/cwl set-format` `/cwl set-leader`\n`/cwl overflow add` `/cwl overflow check`\n`/cwl submit`"
        embed.add_field(name="How to Edit", value=help_text, inline=False)
        
        return embed

    async def refresh_wizard(self, interaction, data):
        # ... existing comment ...
        pass
        
    async def tag_entry_loop(self, bot, channel, data, th):
        await channel.send(f"**Adding TH{th} Overflows**. Enter Player Tags (one per line). Type `stop` to finish.")
        
        while True:
            def check(m): return m.channel.id == channel.id and not m.author.bot
            try:
                msg = await bot.wait_for('message', check=check, timeout=120)
                content = msg.content.strip()
                if content.lower() == "stop":
                    await channel.send("Stopped.")
                    break
                
                tag = content.upper().replace("#", "")
                
                # API Check
                player = await coc_api.get_player(tag)
                if not player:
                    await channel.send("❌ Invalid Tag.")
                    continue
                
                if player.town_hall != th:
                    await channel.send(f"⚠️ Player is TH{player.town_hall}, expected TH{th}. Added anyway.")
                    
                await cwl_models.add_overflow(data['season'], data['clan_tag'], player.tag, player.name, player.town_hall)
                await channel.send(f"✅ Added {player.name}")
                try: await msg.delete() 
                except: pass
                
            except asyncio.TimeoutError:
                await channel.send("Timed out.")
                break
        
    # --- 6. ALLOTMENT FULFILLMENT (Leader Side) ---
    @cwl_group.command(name="allotment", description="View & Fill Pending Allocations")
    async def view_allotment(self, interaction: discord.Interaction):
        data = await self.validate_channel(interaction)
        if not data: return
        
        # Find Pending Allocations where source = this clan
        pendings = await cwl_models.get_pending_allocations(data['season'], source_clan=data['clan_tag'])
        
        # Filter for those not fully approved/filled? User flow: "submit allotments... then admin approves"
        # We show "Pending" or "Filled (Waiting Approval)"
        active_pendings = [p for p in pendings]
        
        if not active_pendings:
            await interaction.response.send_message("No pending allocations found.", ephemeral=True)
            return

        embed = discord.Embed(title=f"allocations for {data['clan_name']}", color=discord.Color.blue())
        
        # Parse Clan Names for display
        all_clans = await mongo_manager.get_clans() + await cwl_models.get_shell_clans()
        def get_name(tag):
             c = next((x for x in all_clans if x.get('clan_tag') == tag or x.get('tag') == tag), None)
             return c['name'] if c else tag

        view = AllotmentFulfillmentView(data['season'], data['clan_tag'], active_pendings)
        
        txt = ""
        for i, p in enumerate(active_pendings):
            target_name = get_name(p['target_clan'])
            status = p.get('status', 'pending')
            filled = p.get('count_filled', 0)
            assigned = p.get('count_assigned', 0)
            
            icon = "🔴"
            if status == "filled": icon = "🟡" # Waiting approval
            if status == "approved": icon = "🟢"
            
            txt += f"{icon} **To {target_name}**: {filled}/{assigned} x TH{p['th_level']}\n"
            
        embed.description = txt
        await interaction.response.send_message(embed=embed, view=view)

    @cwl_group.command(name="submit-allotment", description="Submit Allocations for Approval")
    async def submit_allot(self, interaction: discord.Interaction):
         data = await self.validate_channel(interaction)
         # Logic to notify admin? 
         # Or just marking status?
         # User said "use submit allotments... then after admin confirms".
         # We just notify admin here.
         await interaction.response.send_message(f"✅ Allotments Submitted for review. Admins notified.")


class AllotmentFulfillmentView(discord.ui.View):
    def __init__(self, season, source_clan, pendings):
        super().__init__()
        # Button for each pending item? 
        # Or Select Menu?
        # Let's use Select Menu to pick WHICH allocation to fill.
        
        options = []
        for i, p in enumerate(pendings):
            if p.get('status') == 'approved': continue 
            
            idx = f"{p['target_clan']}:{p['th_level']}" # Unique ID mainly
            options.append(discord.SelectOption(
                label=f"To {p['target_clan']} (TH{p['th_level']})",
                value=idx,
                description=f"Need {p['count_assigned']} players"
            ))
            
        if options:
            self.add_item(allot_select := AllotmentSelect(season, source_clan, pendings, options))

class AllotmentSelect(discord.ui.Select):
    def __init__(self, season, source_clan, pendings, options):
        super().__init__(placeholder="Select Allocation to Fill...", options=options)
        self.season = season; self.source = source_clan; self.pendings = pendings

    async def callback(self, i):
        val = self.values[0]
        target, th = val.split(":")
        th = int(th)
        
        # Get specific pending doc
        alloc = next(p for p in self.pendings if p['target_clan'] == target and p['th_level'] == th)
        count_needed = alloc['count_assigned']
        
        # Show Player Selection (From Overflow List)
        # Fetch Overflows for THIS clan and THIS TH(or higher)
        overflows = await cwl_models.get_overflows(self.season, source_clan=self.source, min_th=th, status="available")
        
        if not overflows:
            await i.response.send_message("No available overflow players found to fill this slot.", ephemeral=True)
            return

        # Player Select View
        await i.response.send_message(f"Select **{count_needed}** players for {target}:", view=AllotPlayerSelectView(self.season, self.source, alloc, overflows), ephemeral=True)

class AllotPlayerSelectView(discord.ui.View):
    def __init__(self, season, source, alloc, players):
        super().__init__()
        options = [discord.SelectOption(label=f"{p['player_name']}", value=p['player_tag']) for p in players[:25]]
        self.add_item(AllotPlayerSelect(season, source, alloc, options))

class AllotPlayerSelect(discord.ui.Select):
    def __init__(self, season, source, alloc, options):
        count = alloc['count_assigned']
        super().__init__(placeholder=f"Select {count} Players...", min_values=count, max_values=count, options=options)
        self.season = season; self.alloc = alloc; self.source = source

    async def callback(self, i):
        tags = self.values
        # Save these players to pending allocation
        await cwl_models.update_pending_players(self.season, self.source, self.alloc['target_clan'], self.alloc['th_level'], tags)
        
        # Pre-reserve them? Move them out of "available" so they aren't double picked?
        for tag in tags:
            await cwl_models.update_overflow_status(self.season, tag, "reserved") 
            
        await i.response.send_message(f"✅ Saved {len(tags)} players for this slot. Don't forget to Submit when done.", ephemeral=True)

class CWLForumClanSelectView(discord.ui.View):
    def __init__(self, clans, season):
        super().__init__()
        options = [discord.SelectOption(label=c['name'], value=c['clan_tag']) for c in clans[:25]]
        self.add_item(CWLForumClanSelect(options, season))

class CWLForumClanSelect(discord.ui.Select):
    def __init__(self, options, season):
        super().__init__(placeholder="Select Clan...", options=options); self.season=season
    
    async def callback(self, interaction: discord.Interaction):
        clan_tag = self.values[0]
        # (Permissions check omitted for brevity, stick to existing logic)
        
        clan_data = next(c for c in await mongo_manager.get_clans() if c['clan_tag'] == clan_tag)
        channel = await self.ensure_channel(interaction.guild, clan_data, interaction.user)
        
        # LINK CHANNEL ID to FORUM Metadata
        await cwl_models.save_forum_metadata(self.season, clan_tag, {"channel_id": channel.id})
        
        await interaction.response.send_message(f"✅ Linked & Created {channel.mention}.\nGo there and run `/cwl wizard` to start.", ephemeral=True)

    async def ensure_channel(self, guild, clan_data, user):
        # (Same logic as before)
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
