import discord
from discord.ext import commands
from discord import app_commands
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import datetime
import itertools

class BSNCupSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        print("BSN Cup System Cog Loaded")
        self.bot.add_view(BSNRegistrationView())
        self.bot.add_view(BSNApprovalView())
        self.bot.add_view(BSNDashboardView())
        self.bot.add_view(BSNManageTeamsView())
        self.bot.add_view(BSNTeamListView())
        self.bot.add_view(BSNManageMatchesView())
        self.bot.add_view(BSNMatchupsView())

# --- Helper Decorator ---
def is_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id != 1272176835769405552:
            await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

    # --- Commands ---

    @app_commands.command(name="bsn_ping", description="Test command to check visibility")
    async def bsn_ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong! BSN Cup system is loaded.", ephemeral=True)

    @app_commands.command(name="bsn_panel", description="Drop the BSN Cup Registration Panel")
    @is_owner()
    async def bsn_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏆 BSN CUP Season 3: Pick & Ban Edition",
            description="**Registration is OPEN!**\n\n"
                        "**Requirements:**\n"
                        "- Team Name\n"
                        "- Captain Tag (Must be one of the 3 players)\n"
                        "- 1x TH18 Player\n"
                        "- 1x TH17 Player\n"
                        "- 1x TH16 Player\n\n"
                        "Click the button below to apply!",
            color=discord.Color.gold()
        )
        embed.set_image(url="https://i.imgur.com/placeholder.png") # Placeholder or user provided image?
        view = BSNRegistrationView()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="bsn_dashboard", description="Admin Dashboard for BSN Cup")
    @is_owner()
    async def bsn_dashboard(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🛠️ BSN Cup Admin Dashboard", color=discord.Color.dark_grey())
        view = BSNDashboardView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="bsn_teams", description="View Registered Teams and Rosters")
    async def bsn_teams(self, interaction: discord.Interaction):
        teams = await mongo_manager.get_bsn_teams()
        if not teams:
            await interaction.response.send_message("No teams registered yet.", ephemeral=True)
            return

        options = [discord.SelectOption(label=t["name"], value=t["name"]) for t in teams]
        view = BSNTeamListView()
        
        # Populate select
        select = [x for x in view.children if isinstance(x, discord.ui.Select)][0]
        select.options = options[:25]
        
        embed = discord.Embed(title="🛡️ Registered Teams", description=f"Total Teams: {len(teams)}\nSelect a team below to view full roster.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view)

class BSNRegistrationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register Team", style=discord.ButtonStyle.green, custom_id="bsn_register_team")
    async def register_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BSNRegistrationModal())

class BSNRegistrationModal(discord.ui.Modal, title="BSN Cup Registration"):
    team_name = discord.ui.TextInput(label="Team Name", placeholder="Enter Team Name")
    captain_tag = discord.ui.TextInput(label="Captain Tag", placeholder="#TAG")
    th18_tag = discord.ui.TextInput(label="TH18 Player Tag", placeholder="#TAG")
    th17_tag = discord.ui.TextInput(label="TH17 Player Tag", placeholder="#TAG")
    th16_tag = discord.ui.TextInput(label="TH16 Player Tag", placeholder="#TAG")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        t_name = self.team_name.value
        c_tag = self.captain_tag.value.strip().upper()
        th18 = self.th18_tag.value.strip().upper()
        th17 = self.th17_tag.value.strip().upper()
        th16 = self.th16_tag.value.strip().upper()

        # 1. Validate Tags & TH Levels
        tags_to_check = [(th18, 18), (th17, 17), (th16, 16)]
        players_data = []
        
        # Check for duplicate tags
        all_tags = [th18, th17, th16]
        if len(set(all_tags)) != 3:
             await interaction.followup.send("❌ Duplicate tags detected. Please use 3 different players.", ephemeral=True)
             return

        for tag, required_th in tags_to_check:
            player = await coc_api.get_player(tag)
            if not player:
                await interaction.followup.send(f"❌ Invalid Player Tag: {tag}", ephemeral=True)
                return
            
            # Strict TH Check? "Input 3 = TH18..."
            # User said "have 3 different options of Th18 , Th17 and Th16 and take tag only if it matches the town hall"
            # Assuming strict match.
            if player.town_hall != required_th:
                await interaction.followup.send(f"❌ Player {player.name} ({tag}) is TH{player.town_hall}, but must be TH{required_th}.", ephemeral=True)
                return
            
            players_data.append({"tag": player.tag, "name": player.name, "th": player.town_hall})

        # 2. Validate Captain
        captain_found = False
        captain_name = "Unknown"
        for p in players_data:
            if p["tag"] == c_tag:
                captain_found = True
                captain_name = p["name"]
                break
        
        if not captain_found:
            await interaction.followup.send(f"❌ Captain Tag {c_tag} must be one of the 3 registered players.", ephemeral=True)
            return

        # 3. Save to Pending
        team_data = {
            "name": t_name,
            "captain_tag": c_tag,
            "captain_name": captain_name,
            "players": players_data,
            "captain_discord_id": interaction.user.id,
            "status": "pending",
            "registered_at": datetime.datetime.now().isoformat()
        }
        
        await mongo_manager.save_bsn_pending_team(team_data)
        
        # 4. Notify Staff
        settings = await mongo_manager.get_bsn_settings()
        if settings and "approval_channel_id" in settings:
            channel = interaction.guild.get_channel(settings["approval_channel_id"])
            if channel:
                embed = discord.Embed(title="📝 New BSN Cup Application", color=discord.Color.orange())
                embed.add_field(name="Team Name", value=t_name, inline=False)
                embed.add_field(name="Captain", value=f"{captain_name} ({c_tag})", inline=False)
                embed.add_field(name="Roster", value=f"TH18: {players_data[0]['name']} ({players_data[0]['tag']})\n"
                                                     f"TH17: {players_data[1]['name']} ({players_data[1]['tag']})\n"
                                                     f"TH16: {players_data[2]['name']} ({players_data[2]['tag']})", inline=False)
                embed.add_field(name="Applicant", value=f"<@{interaction.user.id}>", inline=False)
                
                view = BSNApprovalView(team_name=t_name, applicant_id=interaction.user.id)
                await channel.send(embed=embed, view=view)
            else:
                await interaction.followup.send("⚠️ Application saved, but approval channel not found. Please contact admin.", ephemeral=True)
        else:
             await interaction.followup.send("⚠️ Application saved, but approval channel not set. Please contact admin.", ephemeral=True)

        await interaction.followup.send(f"✅ Application for **{t_name}** submitted for approval! You will receive a DM once reviewed.", ephemeral=True)

class BSNApprovalView(discord.ui.View):
    def __init__(self, team_name=None, applicant_id=None):
        super().__init__(timeout=None)
        self.team_name = team_name
        self.applicant_id = applicant_id

    # We need to persist state. Since persistent views can't have dynamic state easily without custom_id hacking,
    # we will encode the team name in the custom_id.
    # Format: bsn_approve_TEAMNAME, bsn_reject_TEAMNAME
    # BUT team names can be long/weird.
    # Better to use the interaction to fetch the pending team from the embed or DB?
    # If we use dynamic custom_id, we need to handle it in `on_interaction` or similar, or just re-create view.
    # For simplicity in this "one-file" approach, let's use a standard custom_id prefix and parse it.
    
    # Actually, the `add_view` in `cog_load` expects a class.
    # If we use dynamic custom_ids, we need to register the handler differently or use a listener.
    # OR we can just use `bsn_approve` and `bsn_reject` and find the team name from the Embed fields?
    # Yes, parsing embed is easier for stateless persistence.
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="bsn_approve_btn")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Parse Team Name from Embed
        if not interaction.message.embeds:
            await interaction.response.send_message("❌ Error: No embed found.", ephemeral=True)
            return
        
        embed = interaction.message.embeds[0]
        # Team Name is Field 0
        team_name = embed.fields[0].value
        applicant_field = embed.fields[3].value # <@ID>
        applicant_id = int(applicant_field.replace("<@", "").replace(">", ""))
        
        pending_team = await mongo_manager.get_bsn_pending_team(team_name)
        if not pending_team:
            await interaction.response.send_message(f"❌ Team **{team_name}** not found in pending list (maybe already processed?).", ephemeral=True)
            return

        # Move to Active
        pending_team["status"] = "active"
        await mongo_manager.save_bsn_team(pending_team)
        await mongo_manager.delete_bsn_pending_team(team_name)
        
        # Disable Buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.response.send_message(f"✅ Team **{team_name}** Approved!", ephemeral=True)
        
        # DM User
        try:
            user = await interaction.client.fetch_user(applicant_id)
            if user:
                await user.send(f"🎉 **Congratulations!**\nYour team **{team_name}** has been accepted into **BSN Cup Season 3: Pick & Ban Edition**!\nGood luck!")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Could not DM user: {e}", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="bsn_reject_btn")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds:
            return
        embed = interaction.message.embeds[0]
        team_name = embed.fields[0].value
        applicant_field = embed.fields[3].value
        applicant_id = int(applicant_field.replace("<@", "").replace(">", ""))

        await interaction.response.send_modal(BSNRejectModal(team_name, applicant_id, interaction.message))

class BSNRejectModal(discord.ui.Modal):
    def __init__(self, team_name, applicant_id, message):
        super().__init__(title="Reject Application")
        self.team_name = team_name
        self.applicant_id = applicant_id
        self.message = message
        self.reason = discord.ui.TextInput(label="Reason for Rejection", placeholder="e.g. Invalid Tags, Duplicate Players...", style=discord.TextStyle.paragraph)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        await mongo_manager.delete_bsn_pending_team(self.team_name)
        
        # Disable Buttons on original message
        view = BSNApprovalView()
        for child in view.children:
            child.disabled = True
        await self.message.edit(view=view)
        
        await interaction.followup.send(f"❌ Team **{self.team_name}** Rejected.", ephemeral=True)
        
        # DM User
        try:
            user = await interaction.client.fetch_user(self.applicant_id)
            if user:
                await user.send(f"❌ **Application Update**\nYour application for team **{self.team_name}** in BSN Cup Season 3 has been **REJECTED**.\n\n**Reason:** {self.reason.value}\n\nPlease correct the issues and re-apply if you wish.")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Could not DM user: {e}", ephemeral=True)

class BSNDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Manage Teams", style=discord.ButtonStyle.primary, custom_id="bsn_manage_teams")
    async def manage_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select an action:", view=BSNManageTeamsView(), ephemeral=True)

    @discord.ui.button(label="Manage Matches", style=discord.ButtonStyle.secondary, custom_id="bsn_manage_matches")
    async def manage_matches(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select an action:", view=BSNManageMatchesView(), ephemeral=True)

    @discord.ui.button(label="Reset Tournament", style=discord.ButtonStyle.danger, row=2, custom_id="bsn_reset_tournament")
    async def reset_tournament(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != 1272176835769405552:
            await interaction.response.send_message("❌ Only the Owner can reset the tournament.", ephemeral=True)
            return
        
        # Confirmation
        view = BSNConfirmResetView()
        await interaction.response.send_message("⚠️ **ARE YOU SURE?**\nThis will delete ALL matches and reset the tournament. Teams will remain.", view=view, ephemeral=True)

class BSNConfirmResetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="CONFIRM RESET", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        matches = await mongo_manager.get_bsn_matches()
        for m in matches:
            await mongo_manager.delete_bsn_match(m["id"])
        
        await interaction.followup.send("✅ Tournament Reset! All matches deleted.", ephemeral=True)
        # TODO: Trigger leaderboard updates to clear them

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)

class BSNManageTeamsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Remove Team", style=discord.ButtonStyle.danger, custom_id="bsn_remove_team")
    async def remove_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        teams = await mongo_manager.get_bsn_teams()
        if not teams:
            await interaction.response.send_message("No teams to remove.", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=t["name"], value=t["name"]) for t in teams]
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Team to Remove", options=options[:25])
        
        async def callback(inter: discord.Interaction):
            team_name = select.values[0]
            await mongo_manager.delete_bsn_team(team_name)
            await inter.response.send_message(f"Removed team {team_name}", ephemeral=True)

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select team:", view=view, ephemeral=True)

    @discord.ui.button(label="Edit Team", style=discord.ButtonStyle.secondary, custom_id="bsn_edit_team")
    async def edit_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        teams = await mongo_manager.get_bsn_teams()
        if not teams:
            await interaction.response.send_message("No teams to edit.", ephemeral=True)
            return
            
        options = [discord.SelectOption(label=t["name"], value=t["name"]) for t in teams]
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Team to Edit", options=options[:25])
        
        async def callback(inter: discord.Interaction):
            team_name = select.values[0]
            team = next((t for t in teams if t["name"] == team_name), None)
            await inter.response.send_modal(BSNEditTeamModal(team))

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select team to edit:", view=view, ephemeral=True)

class BSNEditTeamModal(discord.ui.Modal):
    def __init__(self, team_data):
        super().__init__(title=f"Edit: {team_data['name']}"[:45])
        self.team_data = team_data
        self.team_name = discord.ui.TextInput(label="Team Name", default=team_data["name"])
        
        # Extract tags
        th18 = next((p["tag"] for p in team_data["players"] if p.get("th") == 18), "")
        th17 = next((p["tag"] for p in team_data["players"] if p.get("th") == 17), "")
        th16 = next((p["tag"] for p in team_data["players"] if p.get("th") == 16), "")
        
        self.th18_tag = discord.ui.TextInput(label="TH18 Tag", default=th18)
        self.th17_tag = discord.ui.TextInput(label="TH17 Tag", default=th17)
        self.th16_tag = discord.ui.TextInput(label="TH16 Tag", default=th16)
        
        self.add_item(self.team_name)
        self.add_item(self.th18_tag)
        self.add_item(self.th17_tag)
        self.add_item(self.th16_tag)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        new_name = self.team_name.value
        th18 = self.th18_tag.value.strip().upper()
        th17 = self.th17_tag.value.strip().upper()
        th16 = self.th16_tag.value.strip().upper()
        
        # Validate
        tags_to_check = [(th18, 18), (th17, 17), (th16, 16)]
        players_data = []
        
        for tag, required_th in tags_to_check:
            player = await coc_api.get_player(tag)
            if not player:
                await interaction.followup.send(f"❌ Invalid Player Tag: {tag}", ephemeral=True)
                return
            if player.town_hall != required_th:
                await interaction.followup.send(f"❌ Player {player.name} ({tag}) is TH{player.town_hall}, but must be TH{required_th}.", ephemeral=True)
                return
            players_data.append({"tag": player.tag, "name": player.name, "th": player.town_hall})
            
        # Update
        if new_name != self.team_data["name"]:
            await mongo_manager.delete_bsn_team(self.team_data["name"])
            
        self.team_data["name"] = new_name
        self.team_data["players"] = players_data
        # Keep captain same or reset? 
        # Captain tag might have changed if they swapped the player.
        # Check if old captain tag is still in new players.
        # If not, default to TH18 player as captain? Or ask?
        # Let's just keep old captain tag if present, else set to TH18 player.
        old_cap = self.team_data.get("captain_tag")
        new_tags = [p["tag"] for p in players_data]
        if old_cap not in new_tags:
            self.team_data["captain_tag"] = players_data[0]["tag"] # TH18
            self.team_data["captain_name"] = players_data[0]["name"]
        
        await mongo_manager.save_bsn_team(self.team_data)
        await interaction.followup.send(f"✅ Team updated successfully!", ephemeral=True)

class BSNTeamListView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(placeholder="Select a team to view roster", custom_id="bsn_team_list_select", options=[discord.SelectOption(label="Loading...", value="loading")])
    async def select_team(self, interaction: discord.Interaction, select: discord.ui.Select):
        team_name = select.values[0]
        teams = await mongo_manager.get_bsn_teams()
        team = next((t for t in teams if t["name"] == team_name), None)
        
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
            
        embed = discord.Embed(title=f"🛡️ {team['name']}", color=discord.Color.blue())
        embed.add_field(name="Captain", value=f"{team.get('captain_name', 'Unknown')} ({team.get('captain_tag')})", inline=False)
        
        roster = ""
        for p in team["players"]:
            roster += f"TH{p.get('th', '?')}: {p['name']} ({p['tag']})\n"
        
        embed.add_field(name="Roster", value=roster, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class BSNManageMatchesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Generate Round 1 (Random)", style=discord.ButtonStyle.primary, custom_id="bsn_gen_r1")
    async def gen_r1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # Check existing
        matches = await mongo_manager.get_bsn_matches()
        if any(m["round"] == 1 for m in matches):
            await interaction.followup.send("❌ Round 1 matches already exist.", ephemeral=True)
            return

        teams = await mongo_manager.get_bsn_teams()
        if len(teams) < 16:
            await interaction.followup.send(f"⚠️ Warning: Only {len(teams)} teams registered. Need 16 for full bracket. Proceeding anyway...", ephemeral=True)
        
        import random
        random.shuffle(teams)
        
        generated = []
        # Pair up
        for i in range(0, len(teams), 2):
            if i + 1 >= len(teams): break # Odd number, last one bye?
            t1 = teams[i]
            t2 = teams[i+1]
            
            match_id = f"R1_M{i//2 + 1}"
            match_data = {
                "id": match_id,
                "label": f"Round 1 - Match {i//2 + 1}",
                "team1": t1["name"],
                "team2": t2["name"],
                "round": 1,
                "completed": False,
                "winner": None
            }
            generated.append(match_data)
            await mongo_manager.save_bsn_match(match_data)
            
        await interaction.followup.send(f"✅ Generated {len(generated)} matches for Round 1.", ephemeral=True)

    @discord.ui.button(label="Generate Round 2 (Single Elim)", style=discord.ButtonStyle.primary, custom_id="bsn_gen_r2")
    async def gen_r2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        matches = await mongo_manager.get_bsn_matches()
        r1_matches = [m for m in matches if m["round"] == 1]
        
        if not all(m["completed"] for m in r1_matches):
            await interaction.followup.send("❌ Round 1 is not complete yet.", ephemeral=True)
            return
            
        winners = [m["winner"] for m in r1_matches if m["winner"]]
        if len(winners) < 2:
             await interaction.followup.send("❌ Not enough winners to generate Round 2.", ephemeral=True)
             return
             
        # Pair winners
        generated = []
        for i in range(0, len(winners), 2):
            if i + 1 >= len(winners): break
            t1 = winners[i]
            t2 = winners[i+1]
            
            match_id = f"R2_M{i//2 + 1}"
            match_data = {
                "id": match_id,
                "label": f"Round 2 - Match {i//2 + 1}",
                "team1": t1,
                "team2": t2,
                "round": 2,
                "completed": False,
                "winner": None
            }
            generated.append(match_data)
            await mongo_manager.save_bsn_match(match_data)
            
        await interaction.followup.send(f"✅ Generated {len(generated)} matches for Round 2.", ephemeral=True)

    @discord.ui.button(label="Generate Round 3 (Double Elim)", style=discord.ButtonStyle.primary, custom_id="bsn_gen_r3")
    async def gen_r3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        matches = await mongo_manager.get_bsn_matches()
        r2_matches = [m for m in matches if m["round"] == 2]
        
        if not all(m["completed"] for m in r2_matches):
            await interaction.followup.send("❌ Round 2 is not complete yet.", ephemeral=True)
            return

        winners = [m["winner"] for m in r2_matches if m["winner"]]
        losers = [] 
        # Wait, user said "Round 3 will be double elimination. lets say we have 4 teams A , B , C ,D . and we did A vs B and C vs D . WINNERS ARE a AND C . a & c will go to winners bracket , b AND d WILL GO TO LOSERS BRACKET"
        # This implies Round 3 IS the start of Double Elim for the 4 winners of Round 2.
        # So we take the 4 winners of Round 2.
        
        if len(winners) != 4:
            await interaction.followup.send(f"❌ Need exactly 4 winners from Round 2 to start Double Elim (Found {len(winners)}).", ephemeral=True)
            return
            
        # Create Initial Double Elim Matches (Upper Bracket Semi-Finals)
        # Match 1: W1 vs W2
        # Match 2: W3 vs W4
        
        m1 = {
            "id": "DE_UB_SF1",
            "label": "Upper Bracket Semi 1",
            "team1": winners[0],
            "team2": winners[1],
            "round": 3,
            "bracket": "upper",
            "completed": False,
            "winner": None
        }
        m2 = {
            "id": "DE_UB_SF2",
            "label": "Upper Bracket Semi 2",
            "team1": winners[2],
            "team2": winners[3],
            "round": 3,
            "bracket": "upper",
            "completed": False,
            "winner": None
        }
        
        await mongo_manager.save_bsn_match(m1)
        await mongo_manager.save_bsn_match(m2)
        
        await interaction.followup.send("✅ Generated Double Elimination Bracket (Upper Semis). Lower bracket matches will generate automatically as results come in.", ephemeral=True)

    @discord.ui.button(label="Enter Result", style=discord.ButtonStyle.success, custom_id="bsn_enter_result")
    async def enter_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        matches = await mongo_manager.get_bsn_matches()
        incomplete = [m for m in matches if not m.get("completed")]
        
        if not incomplete:
            await interaction.response.send_message("No incomplete matches.", ephemeral=True)
            return
            
        options = []
        for m in incomplete[:25]:
            options.append(discord.SelectOption(label=f"{m['label']}: {m['team1']} vs {m['team2']}", value=m['id']))
            
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Match", options=options)
        
        async def callback(inter: discord.Interaction):
            match_id = select.values[0]
            match = next((m for m in matches if m["id"] == match_id), None)
            await inter.response.send_modal(BSNResultModal(match))
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select match:", view=view, ephemeral=True)

class BSNResultModal(discord.ui.Modal):
    def __init__(self, match_data):
        super().__init__(title=f"Result: {match_data['team1']} vs {match_data['team2']}"[:45])
        self.match_data = match_data
        self.winner = discord.ui.TextInput(label="Winner Name (Exact)", placeholder=match_data["team1"])
        self.score1 = discord.ui.TextInput(label=f"Score {match_data['team1']}", placeholder="Stars")
        self.score2 = discord.ui.TextInput(label=f"Score {match_data['team2']}", placeholder="Stars")
        
        self.add_item(self.winner)
        self.add_item(self.score1)
        self.add_item(self.score2)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        winner_name = self.winner.value.strip()
        if winner_name != self.match_data["team1"] and winner_name != self.match_data["team2"]:
             await interaction.followup.send(f"❌ Winner must be exactly '{self.match_data['team1']}' or '{self.match_data['team2']}'.", ephemeral=True)
             return
             
        self.match_data["winner"] = winner_name
        self.match_data["completed"] = True
        self.match_data["score1"] = self.score1.value
        self.match_data["score2"] = self.score2.value
        
        await mongo_manager.save_bsn_match(self.match_data)
        
        # Handle Double Elim Progression
        if self.match_data.get("round") == 3:
            await self.handle_double_elim_progression(self.match_data)
            
        await interaction.followup.send(f"✅ Result saved! Winner: {winner_name}", ephemeral=True)

    async def handle_double_elim_progression(self, match):
        # Logic for DE progression
        # IDs: DE_UB_SF1, DE_UB_SF2 -> Winners go to DE_UB_F, Losers go to DE_LB_R1
        
        matches = await mongo_manager.get_bsn_matches()
        
        if match["id"] in ["DE_UB_SF1", "DE_UB_SF2"]:
            # Check if both SFs are done
            sf1 = next((m for m in matches if m["id"] == "DE_UB_SF1"), None)
            sf2 = next((m for m in matches if m["id"] == "DE_UB_SF2"), None)
            
            if sf1 and sf1["completed"] and sf2 and sf2["completed"]:
                # Create UB Final and LB R1
                ub_final = {
                    "id": "DE_UB_F",
                    "label": "Upper Bracket Final",
                    "team1": sf1["winner"],
                    "team2": sf2["winner"],
                    "round": 3,
                    "bracket": "upper",
                    "completed": False,
                    "winner": None
                }
                
                loser1 = sf1["team1"] if sf1["winner"] == sf1["team2"] else sf1["team2"]
                loser2 = sf2["team1"] if sf2["winner"] == sf2["team2"] else sf2["team2"]
                
                lb_r1 = {
                    "id": "DE_LB_R1",
                    "label": "Lower Bracket Round 1",
                    "team1": loser1,
                    "team2": loser2,
                    "round": 3,
                    "bracket": "lower",
                    "completed": False,
                    "winner": None
                }
                
                await mongo_manager.save_bsn_match(ub_final)
                await mongo_manager.save_bsn_match(lb_r1)
        
        elif match["id"] == "DE_LB_R1":
            # Winner goes to LB Final (Semi-Final in user terms)
            # Loser Eliminated
            # Wait, user said: "WINNER GOES TO SEMI FINALS AND LOSERS IS ELIMIINATED"
            # "Winner between A & c (UB Final) WILL GO TO FINALS , LOSER GOES TO SEMI FINALS"
            # "NOW IN LOSERS BRACKET B VS D (LB R1), WINNER GOES TO SEMI FINALS"
            # So Semi-Final = Loser of UB Final vs Winner of LB R1.
            
            # We need UB Final to be done to know the loser.
            ub_final = next((m for m in matches if m["id"] == "DE_UB_F"), None)
            if ub_final and ub_final["completed"]:
                # Create Semi Final
                ub_loser = ub_final["team1"] if ub_final["winner"] == ub_final["team2"] else ub_final["team2"]
                lb_winner = match["winner"]
                
                semi = {
                    "id": "DE_LB_SF",
                    "label": "Semi-Final",
                    "team1": ub_loser,
                    "team2": lb_winner,
                    "round": 3,
                    "bracket": "lower",
                    "completed": False,
                    "winner": None
                }
                await mongo_manager.save_bsn_match(semi)
        
        elif match["id"] == "DE_UB_F":
            # Loser goes to Semi Final. Check if LB R1 is done.
            lb_r1 = next((m for m in matches if m["id"] == "DE_LB_R1"), None)
            if lb_r1 and lb_r1["completed"]:
                ub_loser = match["team1"] if match["winner"] == match["team2"] else match["team2"]
                lb_winner = lb_r1["winner"]
                
                semi = {
                    "id": "DE_LB_SF",
                    "label": "Semi-Final",
                    "team1": ub_loser,
                    "team2": lb_winner,
                    "round": 3,
                    "bracket": "lower",
                    "completed": False,
                    "winner": None
                }
                await mongo_manager.save_bsn_match(semi)
                
        elif match["id"] == "DE_LB_SF":
            # Winner goes to Grand Final against UB Final Winner
            ub_final = next((m for m in matches if m["id"] == "DE_UB_F"), None)
            if ub_final:
                grand_final = {
                    "id": "DE_GF",
                    "label": "Grand Final",
                    "team1": ub_final["winner"],
                    "team2": match["winner"],
                    "round": 3,
                    "bracket": "final",
                    "completed": False,
                    "winner": None
                }
                await mongo_manager.save_bsn_match(grand_final)

class BSNMatchupsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def get_embed(self, pages, sorted_days, current_page):
        matches = pages[current_page]
        day_label = sorted_days[current_page]
        
        embed = discord.Embed(title=f"📅 Matchups - {day_label}", color=discord.Color.blue())
        
        desc = ""
        for m in matches:
            status = "✅" if m["completed"] else "🕒"
            winner = f"Winner: **{m['winner']}**" if m["completed"] else ""
            desc += f"**{m['team1']}** vs **{m['team2']}**\n{status} {winner}\n\n"
            
        embed.description = desc
        embed.set_footer(text=f"Page {current_page+1}/{len(pages)}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="bsn_matchups_prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_page(interaction, -1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="bsn_matchups_next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_page(interaction, 1)

    async def handle_page(self, interaction, direction):
        # We need to reconstruct the pages logic here or store state.
        # Stateless pagination is hard without storing page in custom_id or footer.
        # Let's parse footer.
        if not interaction.message.embeds: return
        footer = interaction.message.embeds[0].footer.text
        try:
            current = int(footer.split(" ")[1].split("/")[0]) - 1
            total = int(footer.split("/")[1])
        except:
            current = 0
            total = 1
            
        new_page = current + direction
        if new_page < 0 or new_page >= total:
            await interaction.response.defer() # No change
            return
            
        # Fetch matches again
        matches = await mongo_manager.get_bsn_matches()
        # Group by Round/Bracket
        # Actually, user asked for "matchups automatically".
        # Let's group by Round.
        groups = {}
        for m in matches:
            label = f"Round {m['round']}"
            if m.get("bracket"): label += f" ({m['bracket'].title()})"
            if label not in groups: groups[label] = []
            groups[label].append(m)
            
        sorted_keys = sorted(groups.keys())
        pages = [groups[k] for k in sorted_keys]
        
        if not pages:
            await interaction.response.defer()
            return
            
        embed = await self.get_embed(pages, sorted_keys, new_page)
        await interaction.response.edit_message(embed=embed, view=self)

    # --- Leaderboard Helpers ---

    async def update_leaderboard(self):
        settings = await mongo_manager.get_bsn_settings()
        if not settings or "leaderboard_channel_id" not in settings: return
        
        channel = self.bot.get_channel(settings["leaderboard_channel_id"])
        if not channel: return
        try:
            message = await channel.fetch_message(settings["leaderboard_message_id"])
        except: return

        teams = await mongo_manager.get_bsn_teams()
        matches = await mongo_manager.get_bsn_matches()
        
        stats = {t["name"]: {"wins": 0, "losses": 0, "played": 0} for t in teams}
        
        for m in matches:
            if not m["completed"]: continue
            w = m["winner"]
            l = m["team1"] if w == m["team2"] else m["team2"]
            
            if w in stats:
                stats[w]["wins"] += 1
                stats[w]["played"] += 1
            if l in stats:
                stats[l]["losses"] += 1
                stats[l]["played"] += 1
                
        sorted_teams = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)
        
        embed = discord.Embed(title="🏆 BSN Cup Leaderboard", color=discord.Color.gold())
        desc = ""
        for i, (name, s) in enumerate(sorted_teams):
            desc += f"**{i+1}. {name}** - {s['wins']}W / {s['losses']}L\n"
            
        embed.description = desc
        embed.timestamp = datetime.datetime.now()
        await message.edit(embed=embed)

    async def update_bracket(self):
        settings = await mongo_manager.get_bsn_settings()
        if not settings or "bracket_channel_id" not in settings: return
        
        channel = self.bot.get_channel(settings["bracket_channel_id"])
        if not channel: return
        try:
            message = await channel.fetch_message(settings["bracket_message_id"])
        except: return
        
        matches = await mongo_manager.get_bsn_matches()
        
        # Simple text representation of bracket
        embed = discord.Embed(title="⚔️ Tournament Bracket", color=discord.Color.blue())
        
        r1 = [m for m in matches if m["round"] == 1]
        r2 = [m for m in matches if m["round"] == 2]
        r3 = [m for m in matches if m["round"] == 3]
        
        def format_match(m):
            w = f"**{m['winner']}**" if m['winner'] else "TBD"
            return f"{m['label']}: {m['team1']} vs {m['team2']} -> {w}"

        if r1:
            embed.add_field(name="Round 1", value="\n".join([format_match(m) for m in r1])[:1024], inline=False)
        if r2:
            embed.add_field(name="Round 2", value="\n".join([format_match(m) for m in r2])[:1024], inline=False)
        if r3:
            embed.add_field(name="Round 3 (Double Elim)", value="\n".join([format_match(m) for m in r3])[:1024], inline=False)
            
        embed.timestamp = datetime.datetime.now()
        await message.edit(embed=embed)

    # --- Commands for Leaderboards ---

    @app_commands.command(name="bsn_leaderboard", description="Post Auto-Updating Leaderboard")
    @is_owner()
    async def bsn_leaderboard(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🏆 BSN Cup Leaderboard", description="Initializing...", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        settings = await mongo_manager.get_bsn_settings() or {}
        settings["leaderboard_channel_id"] = msg.channel.id
        settings["leaderboard_message_id"] = msg.id
        await mongo_manager.save_bsn_settings(settings)
        await self.update_leaderboard()

    @app_commands.command(name="bsn_bracket", description="Post Auto-Updating Bracket")
    @is_owner()
    async def bsn_bracket(self, interaction: discord.Interaction):
        embed = discord.Embed(title="⚔️ Tournament Bracket", description="Initializing...", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        settings = await mongo_manager.get_bsn_settings() or {}
        settings["bracket_channel_id"] = msg.channel.id
        settings["bracket_message_id"] = msg.id
        await mongo_manager.save_bsn_settings(settings)
        await self.update_bracket()

    @app_commands.command(name="bsn_matchups", description="View Matchups")
    async def bsn_matchups(self, interaction: discord.Interaction):
        matches = await mongo_manager.get_bsn_matches()
        if not matches:
            await interaction.response.send_message("No matches found.", ephemeral=True)
            return
            
        # Group by Round
        groups = {}
        for m in matches:
            label = f"Round {m['round']}"
            if m.get("bracket"): label += f" ({m['bracket'].title()})"
            if label not in groups: groups[label] = []
            groups[label].append(m)
            
        sorted_keys = sorted(groups.keys())
        pages = [groups[k] for k in sorted_keys]
        
        view = BSNMatchupsView()
        embed = await view.get_embed(pages, sorted_keys, 0)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(BSNCupSystem(bot))
