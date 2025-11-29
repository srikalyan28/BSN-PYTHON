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
        matches = await mongo_manager.get_bsn_matches()
        for m in matches:
            await mongo_manager.delete_bsn_match(m["id"])
        
        await interaction.followup.send("✅ Tournament Reset! All matches deleted.", ephemeral=True)

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
        cog = interaction.client.get_cog("BSNCupSystem")
        if cog:
            count = 0
            for m in generated:
                if await cog.create_match_thread(m): count += 1
            await cog.update_bracket() # Auto-update bracket
            await interaction.followup.send(f"✅ Generated {len(generated)} matches for Round {next_round}. Created {count} threads.", ephemeral=True)

    @discord.ui.button(label="Generate Page Playoff (Top 4)", style=discord.ButtonStyle.primary, custom_id="bsn_gen_pp")
    async def gen_pp(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Check previous round
        matches = await mongo_manager.get_bsn_matches()
        if matches:
            max_round = max([m["round"] for m in matches])
            active_round_matches = [m for m in matches if m["round"] == max_round]
            if not all(m["completed"] for m in active_round_matches):
                await interaction.followup.send(f"❌ Round {max_round} is not complete yet.", ephemeral=True)
                return
            next_round = max_round + 1
        else:
            await interaction.followup.send("❌ No matches found. Cannot start Page Playoff.", ephemeral=True)
            return

        # 2. Eliminate losers from previous round first
        teams = await mongo_manager.get_bsn_teams()
        prev_round_matches = [m for m in matches if m["round"] == next_round - 1]
        losers = []
        for m in prev_round_matches:
            if m["winner"]:
                loser = m["team1"] if m["winner"] == m["team2"] else m["team2"]
                losers.append(loser)
        
        for t in teams:
            if t["name"] in losers:
                t["eliminated"] = True
                await mongo_manager.save_bsn_team(t)

        # 3. Select Top 4 Active Teams based on Leaderboard
        active_teams = [t for t in teams if not t.get("eliminated")]
        
        # Calculate stats for sorting
        stats = {t["name"]: {"wins": 0, "total_stars": 0, "total_perc": 0.0} for t in active_teams}
        for m in matches:
            if not m["completed"]: continue
            t1, t2 = m["team1"], m["team2"]
            if t1 in stats:
                stats[t1]["total_stars"] += m.get("team1_total_stars", 0)
                stats[t1]["total_perc"] += m.get("team1_total_perc", 0.0)
            if t2 in stats:
                stats[t2]["total_stars"] += m.get("team2_total_stars", 0)
                stats[t2]["total_perc"] += m.get("team2_total_perc", 0.0)
            
            w = m["winner"]
            if w in stats: stats[w]["wins"] += 1

        # Sort: Wins -> Stars -> Perc
        sorted_active = sorted(
            active_teams,
            key=lambda t: (
                stats[t["name"]]["wins"],
                stats[t["name"]]["total_stars"],
                stats[t["name"]]["total_perc"]
            ),
            reverse=True
        )

        if len(sorted_active) < 4:
            await interaction.followup.send(f"❌ Need at least 4 active teams for Page Playoff (Found {len(sorted_active)}).", ephemeral=True)
            return

        top_4 = sorted_active[:4]
        
        # Eliminate anyone else (Rank 5+)
        for t in sorted_active[4:]:
            t["eliminated"] = True
            await mongo_manager.save_bsn_team(t)
            
        # 4. Generate Page Playoff Bracket
        # Rank 1 vs Rank 2 (Qualifier 1)
        q1 = {
            "id": "PP_Q1",
            "label": "Qualifier 1 (Rank 1 vs 2)",
            "team1": top_4[0]["name"],
            "team2": top_4[1]["name"],
            "round": next_round,
            "bracket": "page_playoff",
            "completed": False,
            "winner": None
        }
        
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

    @discord.ui.button(label="Enter Result", style=discord.ButtonStyle.primary, custom_id="bsn_enter_result")
    async def enter_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        matches = await mongo_manager.get_bsn_matches()
        active = [m for m in matches if not m["completed"]]
        
        if not active:
            await interaction.response.send_message("No active matches found.", ephemeral=True)
            return
            
        options = []
        for m in active[:25]:
            options.append(discord.SelectOption(label=f"{m['label']}: {m['team1']} vs {m['team2']}", value=m['id']))
            
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Match", options=options)
        
        async def callback(inter: discord.Interaction):
            match_id = select.values[0]
            match = next((m for m in matches if m["id"] == match_id), None)
            await inter.response.send_message(f"Entering result for **{match['label']}**", view=BSNResultEntryView(match), ephemeral=True)
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select match to enter result:", view=view, ephemeral=True)

    @discord.ui.button(label="Edit Result", style=discord.ButtonStyle.secondary, custom_id="bsn_edit_result")
    async def edit_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        matches = await mongo_manager.get_bsn_matches()
        completed = [m for m in matches if m["completed"]]
        
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
        await interaction.response.send_message("Select match to edit:", view=view, ephemeral=True)

class BSNResultEntryView(discord.ui.View):
    def __init__(self, match_data):
        super().__init__(timeout=None)
        self.match_data = match_data

    @discord.ui.button(label="Enter Team 1 Stats", style=discord.ButtonStyle.primary)
    async def team1_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        team_name = self.match_data["team1"]
        teams = await mongo_manager.get_bsn_teams()
        team = next((t for t in teams if t["name"] == team_name), None)
        player_names = [p["name"] for p in team["players"]] if team else ["Player 1", "Player 2", "Player 3"]
        await interaction.response.send_modal(BSNTeamStatsModal(self.match_data, "team1", player_names))

    @discord.ui.button(label="Enter Team 2 Stats", style=discord.ButtonStyle.primary)
    async def team2_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        team_name = self.match_data["team2"]
        teams = await mongo_manager.get_bsn_teams()
        team = next((t for t in teams if t["name"] == team_name), None)
        player_names = [p["name"] for p in team["players"]] if team else ["Player 1", "Player 2", "Player 3"]
        await interaction.response.send_modal(BSNTeamStatsModal(self.match_data, "team2", player_names))

class BSNTeamStatsModal(discord.ui.Modal):
    def __init__(self, match_data, team_key, player_names):
        team_name = match_data[team_key]
        super().__init__(title=f"Stats: {team_name}"[:45])
        self.match_data = match_data
        self.team_key = team_key
        
        # Ensure we have 3 names
        while len(player_names) < 3: player_names.append(f"Player {len(player_names)+1}")
        
        self.p1 = discord.ui.TextInput(label=f"{player_names[0]} (Stars %)", placeholder="e.g. 3 100")
        self.p2 = discord.ui.TextInput(label=f"{player_names[1]} (Stars %)", placeholder="e.g. 2 85")
        self.p3 = discord.ui.TextInput(label=f"{player_names[2]} (Stars %)", placeholder="e.g. 3 100")
        
        self.add_item(self.p1)
        self.add_item(self.p2)
        self.add_item(self.p3)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Parse inputs
        try:
            details = []
            total_stars = 0
            total_perc = 0.0
            
            for field in [self.p1, self.p2, self.p3]:
                val = field.value.strip()
                parts = val.split()
                if len(parts) != 2:
                    raise ValueError(f"Invalid format: '{val}'. Use 'Stars %'")
                stars = int(parts[0])
                perc = float(parts[1])
                details.append({"stars": stars, "perc": perc})
                total_stars += stars
                total_perc += perc
                
        except ValueError as e:
            await interaction.followup.send(f"❌ Error parsing stats: {e}", ephemeral=True)
            return

        # Fetch latest match data to avoid race conditions
        matches = await mongo_manager.get_bsn_matches()
        match = next((m for m in matches if m["id"] == self.match_data["id"]), None)
        if not match:
            await interaction.followup.send("❌ Match not found.", ephemeral=True)
            return
            
        # Update match data
        match[f"{self.team_key}_details"] = details
        match[f"{self.team_key}_total_stars"] = total_stars
        match[f"{self.team_key}_total_perc"] = total_perc
        
        await mongo_manager.save_bsn_match(match)
        
        # Check if both teams have data
        t1_details = match.get("team1_details")
        t2_details = match.get("team2_details")
        
        if t1_details and t2_details:
            # Calculate Winner
            s1 = match.get("team1_total_stars", 0)
            p1 = match.get("team1_total_perc", 0)
            s2 = match.get("team2_total_stars", 0)
            p2 = match.get("team2_total_perc", 0)
            
            winner = None
            if s1 > s2: winner = match["team1"]
            elif s2 > s1: winner = match["team2"]
            else:
                if p1 > p2: winner = match["team1"]
                elif p2 > p1: winner = match["team2"]
                else: winner = "Draw" # Should handle draw logic or manual override
            
            match["winner"] = winner
            match["completed"] = True
            match["score1"] = f"{s1}★ ({p1}%)"
            match["score2"] = f"{s2}★ ({p2}%)"
            
            await mongo_manager.save_bsn_match(match)
            
            # Post Result Embed
            embed = discord.Embed(title=f"🏆 Match Result: {match['team1']} vs {match['team2']}", color=discord.Color.green())
            embed.add_field(name=f"{match['team1']}", value=f"**{s1}★** {p1}%", inline=True)
            embed.add_field(name=f"{match['team2']}", value=f"**{s2}★** {p2}%", inline=True)
            embed.add_field(name="Winner", value=f"🎉 **{winner}**", inline=False)
            
            # Detailed breakdown
            d1 = "\n".join([f"P{i+1}: {d['stars']}★ {d['perc']}%" for i, d in enumerate(t1_details)])
            d2 = "\n".join([f"P{i+1}: {d['stars']}★ {d['perc']}%" for i, d in enumerate(t2_details)])
            embed.add_field(name=f"{match['team1']} Details", value=d1, inline=True)
            embed.add_field(name=f"{match['team2']} Details", value=d2, inline=True)
            
            # Send to channel if possible, else just followup
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Trigger updates
            cog = interaction.client.get_cog("BSNCupSystem")
            if cog:
                await cog.update_team_stats()
                await cog.update_player_stats() # NEW: Update player stats
                await cog.update_bracket()
                if match.get("bracket") == "page_playoff":
                    await cog.handle_page_playoff_progression(match)
                # Check for next round generation
                await cog.check_and_generate_next_round(match["round"])
                
        else:
            await interaction.followup.send(f"✅ Stats for **{match[self.team_key]}** saved! Waiting for other team...", ephemeral=True)

    async def handle_page_playoff_progression(self, match):
        matches = await mongo_manager.get_bsn_matches()
        
        if match["id"] == "PP_Q1":
            # Winner -> Grand Final
            # Loser -> Semi Final
            winner = match["winner"]
            loser = match["team1"] if match["winner"] == match["team2"] else match["team2"]
            
            # Check if E1 is done to create SF
            e1 = next((m for m in matches if m["id"] == "PP_E1"), None)
            if e1 and e1["completed"]:
                sf = {
                    "id": "PP_SF",
                    "label": "Semi-Final",
                    "team1": loser, # Loser of Q1
                    "team2": e1["winner"], # Winner of E1
                    "round": match["round"],
                    "bracket": "page_playoff",
                    "completed": False,
                    "winner": None
                }
                await mongo_manager.save_bsn_match(sf)
                await self.create_match_thread(sf)

        elif match["id"] == "PP_E1":
            # Winner -> Semi Final
            # Loser -> Eliminated
            winner = match["winner"]
            
            # Check if Q1 is done to create SF
            q1 = next((m for m in matches if m["id"] == "PP_Q1"), None)
            if q1 and q1["completed"]:
                q1_loser = q1["team1"] if q1["winner"] == q1["team2"] else q1["team2"]
                sf = {
                    "id": "PP_SF",
                    "label": "Semi-Final",
                    "team1": q1_loser,
                    "team2": winner,
                    "round": match["round"],
                    "bracket": "page_playoff",
                    "completed": False,
                    "winner": None
                }
                await mongo_manager.save_bsn_match(sf)
                await self.create_match_thread(sf)

        elif match["id"] == "PP_SF":
            # Winner -> Grand Final
            winner = match["winner"]
            
            q1 = next((m for m in matches if m["id"] == "PP_Q1"), None)
            if q1:
                gf = {
                    "id": "PP_GF",
                    "label": "Grand Final",
                    "team1": q1["winner"], # Winner of Q1
                    "team2": winner, # Winner of SF
                    "round": match["round"],
                    "bracket": "page_playoff",
                    "completed": False,
                    "winner": None
                }
                await mongo_manager.save_bsn_match(gf)
                await self.create_match_thread(gf)

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
            date_info = f"\n📅 {m['date_str']}" if m.get("date_str") else ""
            desc += f"**{m['team1']}** vs **{m['team2']}**\n{status} {winner}{date_info}\n\n"
            
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
            await interaction.response.defer()
            return
            
        matches = await mongo_manager.get_bsn_matches()
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

# --- Main Cog ---

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
        # embed.set_image(url="https://i.imgur.com/placeholder.png") # Removed as requested
        view = BSNRegistrationView()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="bsn_dashboard", description="Admin Dashboard for BSN Cup")
    @is_admin()
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
        
        select = [x for x in view.children if isinstance(x, discord.ui.Select)][0]
        select.options = options[:25]
        
        embed = discord.Embed(title="🛡️ Registered Teams", description=f"Total Teams: {len(teams)}\nSelect a team below to view full roster.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="bsn_setup_approvals", description="Set the channel for team approvals")
    @is_owner()
    async def bsn_setup_approvals(self, interaction: discord.Interaction, channel: discord.TextChannel):
        settings = await mongo_manager.get_bsn_settings() or {}
        settings["approval_channel_id"] = channel.id
        await mongo_manager.save_bsn_settings(settings)
        await interaction.response.send_message(f"✅ Approval channel set to {channel.mention}", ephemeral=True)

    @app_commands.command(name="bsn_setup_negotiation", description="Set Negotiation Channel and Staff Role/User")
    @is_owner()
    async def bsn_setup_negotiation(self, interaction: discord.Interaction, channel: discord.TextChannel, staff: discord.Role = None, user: discord.User = None):
        settings = await mongo_manager.get_bsn_settings() or {}
        settings["negotiation_channel_id"] = channel.id
        
        ping_id = None
        if staff: ping_id = f"&{staff.id}" # Role ping
        elif user: ping_id = f"@{user.id}" # User ping
        
        settings["negotiation_ping_id"] = ping_id
        
        await mongo_manager.save_bsn_settings(settings)
        ping_str = f"<@{ping_id[1:]}>" if ping_id and ping_id.startswith("@") else f"<@&{ping_id[1:]}>" if ping_id else "None"
        await interaction.response.send_message(f"✅ Negotiation channel set to {channel.mention}. Staff Ping: {ping_str}", ephemeral=True)

    @app_commands.command(name="bsn_team_stats", description="Post Auto-Updating Team Stats (Leaderboard)")
    @is_owner()
    async def bsn_team_stats(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📊 BSN Cup Team Stats", description="Initializing...", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        settings = await mongo_manager.get_bsn_settings() or {}
        settings["team_stats_channel_id"] = msg.channel.id
        settings["team_stats_message_id"] = msg.id
        await mongo_manager.save_bsn_settings(settings)
        await self.update_team_stats()

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

    @app_commands.command(name="bsn_matchups", description="View Matchups (Current Round)")
    async def bsn_matchups(self, interaction: discord.Interaction):
        matches = await mongo_manager.get_bsn_matches()
        if not matches:
            await interaction.response.send_message("No matches found.", ephemeral=True)
            return
            
        # Filter for Current Round (Max Round)
        max_round = max([m["round"] for m in matches])
        current_matches = [m for m in matches if m["round"] == max_round]
        
        if not current_matches:
             await interaction.response.send_message("No matches found for current round.", ephemeral=True)
             return

        # Group by bracket if needed (e.g. Page Playoff has different brackets in same round)
        # But user just wants "matches of current round".
        # We can just show them all in one page or paginated if too many.
        
        # Let's paginate 10 per page
        pages = []
        chunk_size = 10
        for i in range(0, len(current_matches), chunk_size):
            pages.append(current_matches[i:i+chunk_size])
            
        view = BSNMatchupsView()
        # We need to adapt get_embed to handle just a list of pages, not a dict of groups
        # Actually BSNMatchupsView.get_embed expects `pages` (list of lists) and `sorted_days` (labels).
        # We can reuse it by passing dummy labels.
        
        labels = [f"Round {max_round} (Page {i+1})" for i in range(len(pages))]
        embed = await view.get_embed(pages, labels, 0)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="bsn_setup_player_stats", description="Setup Auto-Updating Player Stats Leaderboard")
    @is_owner()
    async def bsn_setup_player_stats(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🌟 BSN Cup Player Stats", description="Initializing...", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        settings = await mongo_manager.get_bsn_settings() or {}
        settings["player_stats_channel_id"] = msg.channel.id
        settings["player_stats_message_id"] = msg.id
        await mongo_manager.save_bsn_settings(settings)
        await self.update_player_stats()

    @app_commands.command(name="bsn_player_stats", description="View Player Statistics (Ephemeral)")
    async def bsn_player_stats(self, interaction: discord.Interaction):
        # Just call the update function to refresh the main board, and send a temp one here
        await interaction.response.defer(ephemeral=True)
        await self.update_player_stats()
        
        # We can also just show the same embed here
        matches = await mongo_manager.get_bsn_matches()
        teams = await mongo_manager.get_bsn_teams()
        embed = await self._generate_player_stats_embed(matches, teams)
        if embed:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("No stats available.", ephemeral=True)

    async def _generate_player_stats_embed(self, matches, teams):
        player_stats = {} # tag -> {name, stars, perc, played}
        
        for m in matches:
            if not m.get("completed"): continue
            
            for side in ["team1", "team2"]:
                team_name = m[side]
                details = m.get(f"{side}_details")
                if not details: continue
                
                team = next((t for t in teams if t["name"] == team_name), None)
                if not team: continue
                
                # Assume fixed order: 0=TH18, 1=TH17, 2=TH16
                for i, d in enumerate(details):
                    if i >= len(team["players"]): break
                    p_info = team["players"][i]
                    tag = p_info["tag"]
                    name = p_info["name"]
                    
                    if tag not in player_stats:
                        player_stats[tag] = {"name": name, "stars": 0, "perc": 0.0, "played": 0}
                    
                    player_stats[tag]["stars"] += d["stars"]
                    player_stats[tag]["perc"] += d["perc"]
                    player_stats[tag]["played"] += 1
                    
        if not player_stats:
            return None
            
        # Sort by Stars -> Perc
        sorted_stats = sorted(player_stats.values(), key=lambda x: (x["stars"], x["perc"]), reverse=True)
        
        embed = discord.Embed(title="🌟 BSN Cup Player Stats", color=discord.Color.purple())
        
        desc = "`Rank | Player Name         | Stars |   %   | M `\n"
        desc += "`-----------------------------------------------`\n"
        
        for i, s in enumerate(sorted_stats[:25]): # Top 25
            p_name = (s['name'][:18] + '..') if len(s['name']) > 18 else s['name'].ljust(20)
            desc += f"`{str(i+1).rjust(4)} | {p_name} | {str(s['stars']).center(5)} | {str(int(s['perc'])).center(5)} | {str(s['played']).center(2)}`\n"
            
        embed.description = desc
        embed.set_footer(text="Auto-Updating Leaderboard • Top 25 Players")
        embed.timestamp = datetime.datetime.now()
        return embed

    async def update_player_stats(self):
        settings = await mongo_manager.get_bsn_settings()
        if not settings or "player_stats_channel_id" not in settings: return
        
        channel = self.bot.get_channel(settings["player_stats_channel_id"])
        if not channel: return
        try:
            message = await channel.fetch_message(settings["player_stats_message_id"])
        except: return

        matches = await mongo_manager.get_bsn_matches()
        teams = await mongo_manager.get_bsn_teams()
        
        embed = await self._generate_player_stats_embed(matches, teams)
        if embed:
            await message.edit(embed=embed)

    # --- Auto-Progression Helper ---
    async def check_and_generate_next_round(self, current_round):
        matches = await mongo_manager.get_bsn_matches()
        current_round_matches = [m for m in matches if m["round"] == current_round]
        
        if not all(m["completed"] for m in current_round_matches):
            return # Round not finished
            
        # Notify that round is complete, but DO NOT auto-generate
        settings = await mongo_manager.get_bsn_settings()
        if settings and "bracket_channel_id" in settings:
            ch = self.bot.get_channel(settings["bracket_channel_id"])
            if ch: await ch.send(f"🚨 **Round {current_round} Complete!** Use the dashboard to generate the next round.")

    async def create_match_thread(self, match_data):
        settings = await mongo_manager.get_bsn_settings()
        if not settings or "negotiation_channel_id" not in settings: return False
        
        channel = self.bot.get_channel(settings["negotiation_channel_id"])
        if not channel: return False
        
        # Abbreviation Logic
        def abbreviate(name):
            if " " in name:
                return "".join([word[0] for word in name.split() if word]).upper()
            else:
                return name[:2].upper()
                
        abbr1 = abbreviate(match_data["team1"])
        abbr2 = abbreviate(match_data["team2"])
        thread_name = f"{abbr1} vs {abbr2}"
        
        # Staff Ping
        ping_id = settings.get("negotiation_ping_id")
        ping_str = ""
        if ping_id:
            if ping_id.startswith("&"): ping_str = f"<@&{ping_id[1:]}>"
            elif ping_id.startswith("@"): ping_str = f"<@{ping_id[1:]}>"
            
        # Captain Pings (Need to fetch teams)
        teams = await mongo_manager.get_bsn_teams()
        t1 = next((t for t in teams if t["name"] == match_data["team1"]), None)
        t2 = next((t for t in teams if t["name"] == match_data["team2"]), None)
        
        cap1_ping = f"<@{t1['captain_discord_id']}>" if t1 and "captain_discord_id" in t1 else ""
        cap2_ping = f"<@{t2['captain_discord_id']}>" if t2 and "captain_discord_id" in t2 else ""
        
        content = f"🏆 **Match Created: {match_data['label']}**\n**{match_data['team1']}** vs **{match_data['team2']}**\n\n{ping_str} {cap1_ping} {cap2_ping}\nPlease arrange your match here."
        
        try:
            # Create Private Thread (type=12 is private thread, but needs Guild Premium tier 2 or something? 
            # Actually standard private threads are type 12. 
            # channel.create_thread(name=..., type=discord.ChannelType.private_thread)
            # Note: create_thread on TextChannel with type=private requires 'USE_PRIVATE_THREADS' permission.
            # If not possible, maybe public thread? User asked for private.
            
            thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.private_thread, auto_archive_duration=1440)
            await thread.send(content)
            
            # Save thread ID to match
            match_data["thread_id"] = thread.id
            await mongo_manager.save_bsn_match(match_data)
            return True
        except Exception as e:
            print(f"Failed to create thread for {match_data['id']}: {e}")
            return False

    # --- Helpers ---

    async def update_team_stats(self):
        settings = await mongo_manager.get_bsn_settings()
        if not settings or "team_stats_channel_id" not in settings: return
        
        channel = self.bot.get_channel(settings["team_stats_channel_id"])
        if not channel: return
        try:
            message = await channel.fetch_message(settings["team_stats_message_id"])
        except: return

        teams = await mongo_manager.get_bsn_teams()
        matches = await mongo_manager.get_bsn_matches()
        
        sorted_teams = sorted(
            stats.items(), 
            key=lambda x: (
                x[1]["wins"], 
                x[1].get("total_stars", 0), 
                x[1].get("total_perc", 0.0)
            ), 
            reverse=True
        )
        
        embed = discord.Embed(title="📊 BSN Cup Team Stats", color=discord.Color.gold())
        
        # Table Header
        desc = "`Rank | Team Name         |  W  |  L  | Stars |   %   `\n"
        desc += "`-------------------------------------------------------`\n"
        
        rank = 1
        for name, s in sorted_teams:
            # Filter eliminated teams if they are not active?
            # User said: "remove them from leaderboard automatically when next round is generated"
            # We will mark teams as "eliminated": True in DB when generating next round.
            # So here we just check that flag.
            team = next((t for t in teams if t["name"] == name), None)
            if team and team.get("eliminated"): continue
            
            # Truncate name
            t_name = (name[:17] + '..') if len(name) > 17 else name.ljust(19)
            
            # Calculate totals if not present (backward compatibility or fresh calc)
            # Actually we should calculate totals from matches here to be safe
            # But wait, we are iterating stats which we just built from matches?
            # No, the loop above `for m in matches` only counted wins/losses.
            # We need to sum stars/perc there too.
            pass # See below for re-implementation of the loop
            
        # Re-implementing the stats calculation loop properly
        stats = {t["name"]: {"wins": 0, "losses": 0, "draws": 0, "played": 0, "total_stars": 0, "total_perc": 0.0} for t in teams}
        
        for m in matches:
            if not m["completed"]: continue
            
            # Sum stats for both teams regardless of winner
            t1 = m["team1"]
            t2 = m["team2"]
            
            if t1 in stats:
                stats[t1]["total_stars"] += m.get("team1_total_stars", 0)
                stats[t1]["total_perc"] += m.get("team1_total_perc", 0.0)
                
            if t2 in stats:
                stats[t2]["total_stars"] += m.get("team2_total_stars", 0)
                stats[t2]["total_perc"] += m.get("team2_total_perc", 0.0)
            
            w = m["winner"]
            if w == "Draw":
                if t1 in stats: stats[t1]["draws"] += 1
                if t2 in stats: stats[t2]["draws"] += 1
                continue

            l = t1 if w == t2 else t2
            
            if w in stats:
                stats[w]["wins"] += 1
                stats[w]["played"] += 1
            if l in stats:
                stats[l]["losses"] += 1
                stats[l]["played"] += 1
                
        sorted_teams = sorted(
            stats.items(), 
            key=lambda x: (
                x[1]["wins"], 
                x[1]["total_stars"], 
                x[1]["total_perc"]
            ), 
            reverse=True
        )

        rank = 1
        for name, s in sorted_teams:
            team = next((t for t in teams if t["name"] == name), None)
            if team and team.get("eliminated"): continue
            
            t_name = (name[:17] + '..') if len(name) > 17 else name.ljust(19)
            stars = str(s['total_stars']).center(5)
            perc = str(int(s['total_perc'])).center(5)
            
            desc += f"`{str(rank).rjust(4)} | {t_name} | {str(s['wins']).center(3)} | {str(s['losses']).center(3)} | {stars} | {perc} `\n"
            rank += 1
            
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
        
        embed = discord.Embed(title="⚔️ Tournament Bracket", color=discord.Color.blue())
        
        r1 = sorted([m for m in matches if m["round"] == 1], key=lambda x: x["id"])
        r2 = sorted([m for m in matches if m["round"] == 2], key=lambda x: x["id"])
        r3 = sorted([m for m in matches if m["round"] == 3], key=lambda x: x["id"])
        
        def format_match_line(m):
            w = m.get("winner")
            t1 = m["team1"]
            t2 = m["team2"]
            
            # Icons
            status_icon = "⏳"
            if m["completed"]:
                status_icon = "✅"
                
            # Winner Highlighting
            t1_str = t1
            t2_str = t2
            
            if m["completed"]:
                if w == t1: 
                    t1_str = f"👑 **{t1}**"
                    t2_str = f"💀 {t2}"
                elif w == t2:
                    t1_str = f"💀 {t1}"
                    t2_str = f"👑 **{t2}**"
            
            return f"{status_icon} {t1_str} 🆚 {t2_str}"

        if r1:
            lines = [format_match_line(m) for m in r1]
            embed.add_field(name="🔹 Round 1", value="\n".join(lines), inline=False)
            
        if r2:
            lines = [format_match_line(m) for m in r2]
            embed.add_field(name="🔹 Round 2", value="\n".join(lines), inline=False)
            
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
                if q1: pp_text += f"**Qualifier 1** (Winner ➔ GF)\n{format_match_line(q1)}\n\n"
                if e1: pp_text += f"**Eliminator 1** (Loser ➔ Out)\n{format_match_line(e1)}\n\n"
                if sf: pp_text += f"**Semi-Final**\n{format_match_line(sf)}\n\n"
                if gf: pp_text += f"🏆 **GRAND FINAL** 🏆\n{format_match_line(gf)}\n"
                
                embed.add_field(name="🔥 Page Playoff (Final 4)", value=pp_text, inline=False)
            else:
                lines = [format_match_line(m) for m in r3]
                embed.add_field(name="🔹 Round 3 (Double Elim)", value="\n".join(lines), inline=False)
            
        embed.timestamp = datetime.datetime.now()
        await message.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(BSNCupSystem(bot))
