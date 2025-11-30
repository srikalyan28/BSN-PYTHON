import discord
from discord.ext import commands
from discord import app_commands
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import datetime
import itertools

# --- Constants ---
OWNER_ID = 1272176835769405552
ALLOWED_ADMINS = [
    1272176835769405552, # Owner
    726332723693748244,
    927445011396689951,
    726332723693748244 # BSN Admin
]

# --- Helper Decorator ---
def is_admin():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id not in ALLOWED_ADMINS:
            await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

def is_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ Only the Owner can use this command.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# --- Views and Modals ---

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
        
        # Check for duplicate tags within the submission
        all_tags = [th18, th17, th16]
        if len(set(all_tags)) != 3:
             await interaction.followup.send("❌ Duplicate tags detected in your entry. Please use 3 different players.", ephemeral=True)
             return

        # Check for duplicate tags across ALL teams
        existing_teams = await mongo_manager.get_bsn_teams()
        for team in existing_teams:
            for p in team.get("players", []):
                if p["tag"] in all_tags:
                    await interaction.followup.send(f"❌ Player {p['tag']} is already registered in team **{team['name']}**.", ephemeral=True)
                    return

        for tag, required_th in tags_to_check:
            player = await coc_api.get_player(tag)
            if not player:
                await interaction.followup.send(f"❌ Invalid Player Tag: {tag}", ephemeral=True)
                return
            
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

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="bsn_approve_btn")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds:
            await interaction.response.send_message("❌ Error: No embed found.", ephemeral=True)
            return
        
        embed = interaction.message.embeds[0]
        team_name = embed.fields[0].value
        applicant_field = embed.fields[3].value
        applicant_id = int(applicant_field.replace("<@", "").replace(">", ""))
        
        pending_team = await mongo_manager.get_bsn_pending_team(team_name)
        if not pending_team:
            await interaction.response.send_message(f"❌ Team **{team_name}** not found in pending list (maybe already processed?).", ephemeral=True)
            return

        pending_team["status"] = "active"
        await mongo_manager.save_bsn_team(pending_team)
        await mongo_manager.delete_bsn_pending_team(team_name)
        
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.response.send_message(f"✅ Team **{team_name}** Approved!", ephemeral=True)
        
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
        
        view = BSNApprovalView()
        for child in view.children:
            child.disabled = True
        await self.message.edit(view=view)
        
        await interaction.followup.send(f"❌ Team **{self.team_name}** Rejected.", ephemeral=True)
        
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
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ Only the Owner can manage teams.", ephemeral=True)
            return
        await interaction.response.send_message("Select an action:", view=BSNManageTeamsView(), ephemeral=True)

    @discord.ui.button(label="Manage Matches", style=discord.ButtonStyle.secondary, custom_id="bsn_manage_matches")
    async def manage_matches(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ALLOWED_ADMINS:
            await interaction.response.send_message("❌ You are not authorized to manage matches.", ephemeral=True)
            return
        await interaction.response.send_message("Select an action:", view=BSNManageMatchesView(), ephemeral=True)

    @discord.ui.button(label="Set Match Date", style=discord.ButtonStyle.secondary, row=2, custom_id="bsn_set_date")
    async def set_match_date(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ALLOWED_ADMINS:
            await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)
            return
            
        matches = await mongo_manager.get_bsn_matches()
        active = [m for m in matches if not m.get("completed")]
        if not active:
            await interaction.response.send_message("No active matches found.", ephemeral=True)
            return
            
        options = []
        for m in active[:25]:
            options.append(discord.SelectOption(label=f"{m['label']}: {m['team1']} vs {m['team2']}", value=m['id']))
            
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Match to Schedule", options=options)
        
        async def callback(inter: discord.Interaction):
            match_id = select.values[0]
            match = next((m for m in matches if m["id"] == match_id), None)
            await inter.response.send_modal(BSNSetDateModal(match))
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select match to set date:", view=view, ephemeral=True)

    @discord.ui.button(label="Reset Tournament", style=discord.ButtonStyle.danger, row=2, custom_id="bsn_reset_tournament")
    async def reset_tournament(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ Only the Owner can reset the tournament.", ephemeral=True)
            return
        
        view = BSNConfirmResetView()
        await interaction.response.send_message("⚠️ **ARE YOU SURE?**\nThis will delete ALL matches and reset the tournament. Teams will remain.", view=view, ephemeral=True)

class BSNConfirmResetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="CONFIRM RESET", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Delete Matches
        matches = await mongo_manager.get_bsn_matches()
        for m in matches:
            await mongo_manager.delete_bsn_match(m["id"])
            
        # 2. Reset Teams (Clear Eliminated Flag)
        teams = await mongo_manager.get_bsn_teams()
        for t in teams:
            if t.get("eliminated"):
                t["eliminated"] = False
                await mongo_manager.save_bsn_team(t)
        
        await interaction.followup.send("✅ Tournament Reset! All matches deleted and teams reinstated.", ephemeral=True)

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
        
        # Check for duplicate tags within the submission
        all_tags = [th18, th17, th16]
        if len(set(all_tags)) != 3:
             await interaction.followup.send("❌ Duplicate tags detected in your entry. Please use 3 different players.", ephemeral=True)
             return

        # Check for duplicate tags across ALL teams (excluding current team)
        existing_teams = await mongo_manager.get_bsn_teams()
        for team in existing_teams:
            if team["name"] == self.team_data["name"]: continue # Skip self
            for p in team.get("players", []):
                if p["tag"] in all_tags:
                    await interaction.followup.send(f"❌ Player {p['tag']} is already registered in team **{team['name']}**.", ephemeral=True)
                    return
        
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
            
        if new_name != self.team_data["name"]:
            await mongo_manager.delete_bsn_team(self.team_data["name"])
            
        self.team_data["name"] = new_name
        self.team_data["players"] = players_data
        
        old_cap = self.team_data.get("captain_tag")
        new_tags = [p["tag"] for p in players_data]
        if old_cap not in new_tags:
            self.team_data["captain_tag"] = players_data[0]["tag"]
        
        if not completed:
            await interaction.response.send_message("No completed matches to edit.", ephemeral=True)
            return
            
        options = []
        for m in completed[:25]:
            options.append(discord.SelectOption(label=f"{m['label']}: {m['team1']} vs {m['team2']}", value=m['id']))
            
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Match to Edit", options=options)
        
        async def callback(inter: discord.Interaction):
            match_id = select.values[0]
            match = next((m for m in matches if m["id"] == match_id), None)
            await inter.response.send_message(f"⚠️ **EDITING RESULT** for **{match['label']}**.\nPrevious Winner: {match.get('winner')}\n\nPlease re-enter stats for BOTH teams to recalculate.", view=BSNResultEntryView(match), ephemeral=True)
            
        select.callback = callback
        view.add_item(select)
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select match to edit:", view=view, ephemeral=True)

class BSNSetDateModal(discord.ui.Modal):
    def __init__(self, match_data):
        super().__init__(title="Set Match Date")
        self.match_data = match_data
        self.date_input = discord.ui.TextInput(label="Date & Time", placeholder="e.g. Friday 8pm EST or 30 Nov 20:00 UTC", default=match_data.get("date_str", ""))
        self.add_item(self.date_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        date_str = self.date_input.value
        self.match_data["date_str"] = date_str
        await mongo_manager.save_bsn_match(self.match_data)
        
        # Try to update thread if exists
        if self.match_data.get("thread_id"):
            try:
                thread = interaction.guild.get_thread(self.match_data["thread_id"])
                if thread:
                    await thread.send(f"📅 **Match Date Updated:** {date_str}")
            except: pass
            
        await interaction.followup.send(f"✅ Date set for **{self.match_data['label']}**: {date_str}", ephemeral=True)

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

    @discord.ui.button(label="Generate Single Elim Round", style=discord.ButtonStyle.success, custom_id="bsn_gen_se")
    async def gen_se(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Check if previous round is complete
        matches = await mongo_manager.get_bsn_matches()
        if matches:
            max_round = max([m["round"] for m in matches])
            active_round_matches = [m for m in matches if m["round"] == max_round]
            if not all(m["completed"] for m in active_round_matches):
                await interaction.followup.send(f"❌ Round {max_round} is not complete yet.", ephemeral=True)
                return
            next_round = max_round + 1
        else:
            next_round = 1

        # 2. Identify Active Teams
        teams = await mongo_manager.get_bsn_teams()
        active_teams = [t for t in teams if not t.get("eliminated")]
        
        # If not Round 1, we need to eliminate losers from previous round
        if next_round > 1:
            prev_round_matches = [m for m in matches if m["round"] == next_round - 1]
            losers = []
            for m in prev_round_matches:
                if m["winner"]:
                    loser = m["team1"] if m["winner"] == m["team2"] else m["team2"]
                    losers.append(loser)
            
            # Mark losers as eliminated
            for t in teams:
                if t["name"] in losers:
                    t["eliminated"] = True
                    await mongo_manager.save_bsn_team(t)
            
            # Refresh active teams
            active_teams = [t for t in teams if not t.get("eliminated")]

        if len(active_teams) < 2:
            await interaction.followup.send("❌ Not enough active teams to generate a round.", ephemeral=True)
            return

        # 3. Pair Teams (Randomly for R1, or based on previous? Random is fine for now as per previous logic)
        # For R1 we shuffle. For subsequent rounds, we just pair the survivors.
        # Ideally we should follow a bracket structure, but "flexible" implies just pairing available teams.
        import random
        if next_round == 1:
            random.shuffle(active_teams)
        else:
            # Sort by something? Or just random? 
            # Let's keep it random to avoid complex seeding logic unless requested.
            # User said "round generating is very messey... not viable when teams more/less than 16"
            # Simple pairing of survivors is the standard "flexible" way.
            random.shuffle(active_teams)

        generated = []
        for i in range(0, len(active_teams), 2):
            if i + 1 >= len(active_teams): 
                # Odd number, last team gets a bye?
                # For now, let's just warn and skip.
                await interaction.followup.send(f"⚠️ Odd number of teams ({len(active_teams)}). **{active_teams[i]['name']}** will not have a match.", ephemeral=True)
                break
                
            t1 = active_teams[i]
            t2 = active_teams[i+1]
            
            match_id = f"R{next_round}_M{i//2 + 1}"
            match_data = {
                "id": match_id,
                "label": f"Round {next_round} - Match {i//2 + 1}",
                "team1": t1["name"],
                "team2": t2["name"],
                "round": next_round,
                "completed": False,
                "winner": None
            }
            generated.append(match_data)
            await mongo_manager.save_bsn_match(match_data)
            
        # Create Threads
        # Rank 3 vs Rank 4 (Eliminator 1)
        e1 = {
            "id": "PP_E1",
            "label": "Eliminator 1 (Rank 3 vs 4)",
            "team1": top_4[2]["name"],
            "team2": top_4[3]["name"],
            "round": next_round,
            "bracket": "page_playoff",
            "completed": False,
            "winner": None
        }
        
        await mongo_manager.save_bsn_match(q1)
        await mongo_manager.save_bsn_match(e1)
        
        # Create Threads
        cog = interaction.client.get_cog("BSNCupSystem")
        if cog:
            await cog.create_match_thread(q1)
            await cog.create_match_thread(e1)
            await cog.update_bracket() # Auto-update bracket
        
        await interaction.followup.send(f"✅ Generated Page Playoff Bracket.\n**Q1**: {q1['team1']} vs {q1['team2']}\n**E1**: {e1['team1']} vs {e1['team2']}", ephemeral=True)

    @discord.ui.button(label="Generate Next Playoff Stage", style=discord.ButtonStyle.success, custom_id="bsn_gen_pp_next")
    async def gen_pp_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        matches = await mongo_manager.get_bsn_matches()
        
        # Check if we are in Page Playoff
        if not any(m.get("bracket") == "page_playoff" for m in matches):
            await interaction.followup.send("❌ No Page Playoff active.", ephemeral=True)
            return

        q1 = next((m for m in matches if m["id"] == "PP_Q1"), None)
        e1 = next((m for m in matches if m["id"] == "PP_E1"), None)
        sf = next((m for m in matches if m["id"] == "PP_SF"), None)
        gf = next((m for m in matches if m["id"] == "PP_GF"), None)
        
        created = []
        
        # Check for SF generation
        if q1 and q1["completed"] and e1 and e1["completed"] and not sf:
            q1_loser = q1["team1"] if q1["winner"] == q1["team2"] else q1["team2"]
            sf_match = {
        if not channel: return
        try:
            message = await channel.fetch_message(settings["bracket_message_id"])
        except: return
        
        matches = await mongo_manager.get_bsn_matches()
        
        embed = discord.Embed(title="⚔️ Tournament Bracket", color=discord.Color.blue())
        
        r1 = sorted([m for m in matches if m["round"] == 1], key=lambda x: x["id"])
        r2 = sorted([m for m in matches if m["round"] == 2], key=lambda x: x["id"])
        r3 = sorted([m for m in matches if m["round"] == 3], key=lambda x: x["id"])
        
        def format_match_line(m):
            w = m.get("winner")
            t1 = m["team1"]
            t2 = m["team2"]
            
            # Diff formatting:
            # + Winner
            # - Loser
            #   Pending
            
            line = ""
            if m["completed"]:
                if w == t1: 
                    line = f"+ {t1}\n- {t2}"
                elif w == t2:
                    line = f"- {t1}\n+ {t2}"
                else: # Draw
                    line = f"  {t1} (Draw)\n  {t2} (Draw)"
            else:
                line = f"  {t1}\n  {t2}"
            
            return line

        if r1:
            lines = [format_match_line(m) for m in r1]
            chunk = "```diff\n" + "\n\n".join(lines) + "\n```"
            embed.add_field(name="🔹 Round 1", value=chunk, inline=False)
            
        if r2:
            lines = [format_match_line(m) for m in r2]
            chunk = "```diff\n" + "\n\n".join(lines) + "\n```"
            embed.add_field(name="🔹 Round 2", value=chunk, inline=False)
            
        if r3:
            # Check if it's Page Playoff or old Double Elim
            is_pp = any(m.get("bracket") == "page_playoff" for m in r3)
            
            if is_pp:
                # Custom Display for Page Playoff
                q1 = next((m for m in r3 if m["id"] == "PP_Q1"), None)
                e1 = next((m for m in r3 if m["id"] == "PP_E1"), None)
                sf = next((m for m in r3 if m["id"] == "PP_SF"), None)
                gf = next((m for m in r3 if m["id"] == "PP_GF"), None)
                
                pp_text = ""
                if q1: pp_text += f"**Qualifier 1** (Winner ➔ GF)\n```diff\n{format_match_line(q1)}\n```\n"
                if e1: pp_text += f"**Eliminator 1** (Loser ➔ Out)\n```diff\n{format_match_line(e1)}\n```\n"
                if sf: pp_text += f"**Semi-Final**\n```diff\n{format_match_line(sf)}\n```\n"
                if gf: pp_text += f"🏆 **GRAND FINAL** 🏆\n```diff\n{format_match_line(gf)}\n```"
                
                embed.add_field(name="🔥 Page Playoff (Final 4)", value=pp_text, inline=False)
            else:
                lines = [format_match_line(m) for m in r3]
                chunk = "```diff\n" + "\n\n".join(lines) + "\n```"
                embed.add_field(name="🔹 Round 3 (Double Elim)", value=chunk, inline=False)
            
        embed.timestamp = datetime.datetime.now()
        await message.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(BSNCupSystem(bot))
