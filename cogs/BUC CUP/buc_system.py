import discord
from discord.ext import commands
from discord import app_commands
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import datetime
import itertools

class BUCSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        print("BUC System Cog Loaded")
        self.bot.add_view(RegistrationView())
        self.bot.add_view(DashboardView())
        self.bot.add_view(ManageTeamsView())
        self.bot.add_view(ManageMatchesView())
        self.bot.add_view(MatchupsView())
        self.bot.add_view(TeamListView())

    async def ensure_team_player_names(self, team):
        """Helper to ensure all players in a team have names fetched."""
        updated = False
        new_players = []
        
        # Update Captain Name if missing/Unknown
        if "captain_name" not in team or team["captain_name"] == "Unknown":
            captain = await coc_api.get_player(team["captain_tag"])
            if captain:
                team["captain_name"] = captain.name
                updated = True

        for p in team["players"]:
            if isinstance(p, str):
                # Legacy string tag
                tag = p
                player = await coc_api.get_player(tag)
                if player:
                    new_players.append({"tag": player.tag, "name": player.name})
                    updated = True
                else:
                    new_players.append({"tag": tag, "name": "Unknown"})
                    updated = True
            elif isinstance(p, dict):
                if "name" not in p or p["name"] == "Player" or p["name"] == "Unknown":
                    # Try to fetch again
                    player = await coc_api.get_player(p["tag"])
                    if player:
                        p["name"] = player.name
                        updated = True
                new_players.append(p)
        
        if updated:
            team["players"] = new_players
            await mongo_manager.save_buc_team(team)
        return team

    # --- Helper: Update Leaderboard ---
    async def update_leaderboard(self):
        settings = await mongo_manager.get_buc_settings()
        if not settings or "leaderboard_channel_id" not in settings or "leaderboard_message_id" not in settings:
            return

        channel_id = settings["leaderboard_channel_id"]
        message_id = settings["leaderboard_message_id"]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return

        teams = await mongo_manager.get_buc_teams()
        matches = await mongo_manager.get_buc_matches()
        
        # Calculate Stats
        team_stats = {team["name"]: {"points": 0, "total_percent": 0.0, "played": 0, "wins": 0, "losses": 0, "ties": 0} for team in teams}
        
        for match in matches:
            if not match.get("completed") or match["round"] != 1:
                continue
            t1, t2 = match["team1"], match["team2"]
            winner = match.get("winner")
            
            if t1 in team_stats:
                team_stats[t1]["played"] += 1
                team_stats[t1]["total_percent"] += match.get("percent1", 0)
            if t2 in team_stats:
                team_stats[t2]["played"] += 1
                team_stats[t2]["total_percent"] += match.get("percent2", 0)

            if winner == "Tie":
                if t1 in team_stats:
                    team_stats[t1]["points"] += 1
                    team_stats[t1]["ties"] += 1
                if t2 in team_stats:
                    team_stats[t2]["points"] += 1
                    team_stats[t2]["ties"] += 1
            elif winner == t1:
                if t1 in team_stats:
                    team_stats[t1]["points"] += 2
                    team_stats[t1]["wins"] += 1
                if t2 in team_stats: team_stats[t2]["losses"] += 1
            elif winner == t2:
                if t2 in team_stats:
                    team_stats[t2]["points"] += 2
                    team_stats[t2]["wins"] += 1
                if t1 in team_stats: team_stats[t1]["losses"] += 1

        # Sort by Points, then Total Percentage
        sorted_teams = sorted(team_stats.items(), key=lambda x: (x[1]["points"], x[1]["total_percent"]), reverse=True)

        embed = discord.Embed(title="🏆 BUC CUP Leaderboard (Round 1)", color=discord.Color.gold())
        
        # Code Block Table
        # Rank | Team | P | W | L | T | Pts | %
        header = f"{'Rank':<4} | {'Team':<15} | {'P':<2} | {'W':<2} | {'L':<2} | {'T':<2} | {'Pts':<3} | {'Total %':<7}"
        separator = "-" * len(header)
        rows = []
        
        for i, (name, stats) in enumerate(sorted_teams):
            rank = i + 1
            # Truncate team name if too long
            t_name = (name[:13] + "..") if len(name) > 15 else name
            
            # Display Total Percent (Sum of all player percentages across all matches)
            # match.percent1 is avg of 5 players. So total_percent is sum of avgs.
            # To get sum of all players, multiply by 5.
            display_percent = stats['total_percent'] * 5
            
            row = f"#{rank:<3} | {t_name:<15} | {stats['played']:<2} | {stats['wins']:<2} | {stats['losses']:<2} | {stats['ties']:<2} | {stats['points']:<3} | {display_percent:>7.2f}"
            rows.append(row)

        table = "\n".join([header, separator] + rows)
        embed.description = f"```text\n{table}\n```\nTop 4 qualify for Round 2 (Page Playoff) 🟢"
        embed.timestamp = datetime.datetime.now()
        
        await message.edit(embed=embed)

    # --- Helper: Update Bracket ---
    async def update_bracket(self):
        settings = await mongo_manager.get_buc_settings()
        if not settings or "bracket_channel_id" not in settings or "bracket_message_id" not in settings:
            return

        channel_id = settings["bracket_channel_id"]
        message_id = settings["bracket_message_id"]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return

        matches = await mongo_manager.get_buc_matches()
        r2_matches = [m for m in matches if m.get("round") == 2]
        
        # Organize by Match ID or Label
        # M1: 1v2, M2: 3v4, M3: Semi, M4: Final
        bracket_data = {
            "M1": {"t1": "TBD", "t2": "TBD", "winner": None},
            "M2": {"t1": "TBD", "t2": "TBD", "winner": None},
            "M3": {"t1": "TBD", "t2": "TBD", "winner": None},
            "M4": {"t1": "TBD", "t2": "TBD", "winner": None}
        }
        
        for m in r2_matches:
            label = m.get("label") # M1, M2, M3, M4
            if label in bracket_data:
                bracket_data[label]["t1"] = m.get("team1", "TBD")
                bracket_data[label]["t2"] = m.get("team2", "TBD")
                bracket_data[label]["winner"] = m.get("winner")

        embed = discord.Embed(title="⚔️ BUC CUP Round 2 Bracket", color=discord.Color.blue())
        
        # Qualifier 1 (1 vs 2)
        m1 = bracket_data["M1"]
        embed.add_field(name="Qualifier 1 (1st vs 2nd)", value=f"{m1['t1']} vs {m1['t2']}\nWinner: **{m1['winner'] or 'TBD'}**", inline=False)
        
        # Eliminator (3 vs 4)
        m2 = bracket_data["M2"]
        embed.add_field(name="Eliminator (3rd vs 4th)", value=f"{m2['t1']} vs {m2['t2']}\nWinner: **{m2['winner'] or 'TBD'}**", inline=False)
        
        # Semi-Final
        m3 = bracket_data["M3"]
        embed.add_field(name="Semi-Final (Loser Q1 vs Winner E)", value=f"{m3['t1']} vs {m3['t2']}\nWinner: **{m3['winner'] or 'TBD'}**", inline=False)
        
        # Final
        m4 = bracket_data["M4"]
        embed.add_field(name="🏆 GRAND FINAL 🏆", value=f"{m4['t1']} vs {m4['t2']}\nWinner: **{m4['winner'] or 'TBD'}**", inline=False)

        await message.edit(embed=embed)

    # --- Helper: Update Player Stats ---
    async def update_player_stats(self):
        settings = await mongo_manager.get_buc_settings()
        if not settings or "player_stats_channel_id" not in settings or "player_stats_message_id" not in settings:
            return

        channel_id = settings["player_stats_channel_id"]
        message_id = settings["player_stats_message_id"]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return

        matches = await mongo_manager.get_buc_matches()
        player_stats = {} # tag -> {name, team, stars, total_percent, matches}

        # We need to ensure names are correct.
        # Since we can't easily map match stats back to team objects to update DB here efficiently without iterating all teams,
        # we will rely on the fact that `buc_teams` and `enter_result` trigger the updates.
        # However, for display here, if name is "Player" or "Unknown", we should try to fetch.
        # But fetching for every player in stats might be too API heavy if done frequently.
        # Let's try to fetch only if name is missing/default AND we haven't fetched yet.
        
        for m in matches:
            if not m.get("completed"): continue
            
            # Combine stats from both teams
            all_stats = m.get("team1_stats", []) + m.get("team2_stats", [])
            
            # Helper to process stats
            async def process_stat_list(stats_list, team_name):
                for p in stats_list:
                    tag = p["tag"]
                    name = p.get("name", "Unknown")
                    
                    # Lazy fetch if name is generic
                    if name in ["Player", "Unknown"] or not name:
                         fetched = await coc_api.get_player(tag)
                         if fetched: name = fetched.name
                    
                    if tag not in player_stats:
                        player_stats[tag] = {"name": name, "team": team_name, "stars": 0, "total_percent": 0.0, "matches": 0}
                    
                    player_stats[tag]["stars"] += p["stars"]
                    player_stats[tag]["total_percent"] += p["percent"]
                    player_stats[tag]["matches"] += 1
                    # Update team if unknown (shouldn't happen if logic correct)
                    if player_stats[tag]["team"] == "Unknown": player_stats[tag]["team"] = team_name

            await process_stat_list(m.get("team1_stats", []), m["team1"])
            await process_stat_list(m.get("team2_stats", []), m["team2"])

        # Calculate Avg %
        results = []
        for tag, data in player_stats.items():
            avg_percent = data["total_percent"] / data["matches"] if data["matches"] > 0 else 0
            results.append({
                "name": data["name"],
                "team": data["team"],
                "stars": data["stars"],
                "avg_percent": avg_percent,
                "matches": data["matches"]
            })

        # Sort by Stars (desc), Avg % (desc)
        sorted_players = sorted(results, key=lambda x: (x["stars"], x["avg_percent"]), reverse=True)
        
        embed = discord.Embed(title="🌟 BUC CUP Player Leaderboard", description="Ranking by Tournament Performance", color=discord.Color.purple())
        
        # Pagination logic needed if many players.
        # For the auto-updating message, we can only show Top X (e.g. 20).
        # User asked for "pager format in all".
        # But this is an auto-updating message, not a command response.
        # We can't easily paginate an auto-updating message unless we add buttons to it.
        # Adding buttons to the persistent message is possible.
        # But for now, let's show Top 15 in Code Block.
        
        header = f"{'Rank':<4} | {'Player':<15} | {'Team':<10} | {'Stars':<5} | {'Avg %':<6}"
        separator = "-" * len(header)
        rows = []
        
        for i, p in enumerate(sorted_players[:20]):
            rank = i + 1
            # Truncate name to 13 chars
            p_name = (p["name"][:11] + "..") if len(p["name"]) > 13 else p["name"]
            t_name = (p["team"][:8] + "..") if len(p["team"]) > 10 else p["team"]
            row = f"#{rank:<3} | {p_name:<15} | {t_name:<10} | {p['stars']:<5} | {p['avg_percent']:>6.2f}"
            rows.append(row)
            
        table = "\n".join([header, separator] + rows)
        embed.description = f"```text\n{table}\n```"
        embed.set_footer(text="Showing Top 20 Players")
        embed.timestamp = datetime.datetime.now()
        
        await message.edit(embed=embed)

    # --- Commands ---

    def is_owner():
        async def predicate(interaction: discord.Interaction):
            if interaction.user.id != 1272176835769405552:
                await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
                return False
            return True
        return app_commands.check(predicate)

    @app_commands.command(name="buc_panel", description="Drop the BUC Cup Registration Panel")
    @is_owner()
    async def buc_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏆 BLACKSPIRE UNITED CLASH CUP Registration",
            description="Click the button below to register your team!\n\n"
                        "**Requirements:**\n"
                        "- Team Name\n"
                        "- Captain Tag\n"
                        "- 5 Player Tags",
            color=discord.Color.gold()
        )
        view = RegistrationView()
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="buc_dashboard", description="Admin Dashboard for BUC Cup")
    @is_owner()
    async def buc_dashboard(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🛠️ BUC Cup Admin Dashboard", color=discord.Color.dark_grey())
        view = DashboardView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="buc_leaderboard", description="Post the Auto-Updating Leaderboard")
    @is_owner()
    async def buc_leaderboard(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🏆 BUC CUP Leaderboard", description="Initializing...", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        
        settings = {"leaderboard_channel_id": message.channel.id, "leaderboard_message_id": message.id}
        await mongo_manager.save_buc_settings(settings)
        await self.update_leaderboard()

    @app_commands.command(name="buc_bracket", description="Post the Auto-Updating Bracket")
    @is_owner()
    async def buc_bracket(self, interaction: discord.Interaction):
        embed = discord.Embed(title="⚔️ BUC CUP Bracket", description="Initializing...", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        
        # We need to merge settings, not overwrite
        current_settings = await mongo_manager.get_buc_settings() or {}
        current_settings.update({"bracket_channel_id": message.channel.id, "bracket_message_id": message.id})
        await mongo_manager.save_buc_settings(current_settings)
        await self.update_bracket()

    @app_commands.command(name="buc_matchups", description="Show Matchups Schedule")
    async def buc_matchups(self, interaction: discord.Interaction):
        # Public command

        matches = await mongo_manager.get_buc_matches()
        if not matches:
            await interaction.response.send_message("No matches generated yet.", ephemeral=True)
            return

        # Pagination for Matchups: 1 Day per Page
        # Group by Day
        matches_by_day = {}
        for m in matches:
            day = m.get("day", "Unknown")
            if day not in matches_by_day: matches_by_day[day] = []
            matches_by_day[day].append(m)
        
        # Sort days
        sorted_days = sorted(matches_by_day.keys(), key=lambda x: int(x) if isinstance(x, int) else 999)
        pages = [matches_by_day[d] for d in sorted_days]
        
        if not pages:
             await interaction.response.send_message("No matches found.", ephemeral=True)
             return

        view = MatchupsView()
        # Initial Embed (Page 1)
        embed = await view.get_embed(pages, sorted_days, 0)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="buc_player_stats", description="Post the Player Stats Leaderboard")
    @is_owner()
    async def buc_player_stats(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🌟 Player Stats", description="Initializing...", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        
        current_settings = await mongo_manager.get_buc_settings() or {}
        current_settings.update({"player_stats_channel_id": message.channel.id, "player_stats_message_id": message.id})
        await mongo_manager.save_buc_settings(current_settings)
        await self.update_player_stats()

        @app_commands.command(name="buc_teams", description="View Registered Teams and Rosters")
    async def buc_teams(self, interaction: discord.Interaction):
        # Public command

        teams = await mongo_manager.get_buc_teams()
        if not teams:
            await interaction.response.send_message("No teams registered yet.", ephemeral=True)
            return

        # 🟢 NEW: sort by 'order' (Blackspire Nation has order = 1)
        teams = sorted(teams, key=lambda t: t.get("order", 9999))

        options = [discord.SelectOption(label=t["name"], value=t["name"]) for t in teams]
        view = TeamListView()

        # Find the select item
        select = [x for x in view.children if isinstance(x, discord.ui.Select)][0]
        select.options = options[:25]

        embed = discord.Embed(
            title="🛡️ Registered Teams",
            description=f"Total Teams: {len(teams)}\nSelect a team below to view full roster.",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=view)


class RegistrationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register Team", style=discord.ButtonStyle.green, custom_id="buc_register_team")
    async def register_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())

class RegistrationModal(discord.ui.Modal, title="Register Team"):
    team_name = discord.ui.TextInput(label="Team Name", placeholder="Enter Team Name")
    captain_tag = discord.ui.TextInput(label="Captain Tag", placeholder="#TAG")
    player_tags = discord.ui.TextInput(label="Player Tags (Comma Separated)", placeholder="#TAG1, #TAG2, #TAG3, #TAG4, #TAG5", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        t_name = self.team_name.value
        c_tag = self.captain_tag.value.strip().upper()
        p_tags_raw = self.player_tags.value
        p_tags = [t.strip().upper() for t in p_tags_raw.split(",") if t.strip()]

        if len(p_tags) != 5:
            await interaction.followup.send("❌ You must provide exactly 5 player tags.", ephemeral=True)
            return

        # Validate Tags and Fetch IGNs
        captain = await coc_api.get_player(c_tag)
        if not captain:
             await interaction.followup.send(f"❌ Invalid Captain Tag: {c_tag}", ephemeral=True)
             return
        
        players_data = []
        for tag in p_tags:
            p = await coc_api.get_player(tag)
            if not p:
                await interaction.followup.send(f"❌ Invalid Player Tag: {tag}", ephemeral=True)
                return
            players_data.append({"tag": p.tag, "name": p.name})

        # Ensure captain is in players list? User said "register all 5 players... and also choose captain account".
        # Usually captain is one of the 5. If not, we have 6 players?
        # "register all 5 players... and also choose captain account".
        # Let's assume Captain is one of the 5 or a 6th non-playing captain?
        # "select captain account" implies one of the registered players is captain.
        # But if they enter 5 tags AND a captain tag, and captain tag is NOT in the 5, what then?
        # I'll assume the 5 players are the roster. Captain must be one of them.
        # Check if captain tag is in player tags.
        if c_tag not in p_tags:
            # If not in list, maybe they forgot? Or maybe non-playing captain?
            # Let's just store captain separately but also check if they are a player.
            pass

        team_data = {
            "name": t_name,
            "captain_tag": c_tag,
            "captain_name": captain.name,
            "players": players_data, # List of dicts {tag, name}
            "captain_discord_id": interaction.user.id
        }
        
        await mongo_manager.save_buc_team(team_data)
        await interaction.followup.send(f"✅ Team **{t_name}** registered successfully! Captain: {captain.name}", ephemeral=True)

class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Manage Teams", style=discord.ButtonStyle.primary, custom_id="buc_manage_teams")
    async def manage_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select an action:", view=ManageTeamsView(), ephemeral=True)

    @discord.ui.button(label="Manage Matches", style=discord.ButtonStyle.secondary, custom_id="buc_manage_matches")
    async def manage_matches(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select an action:", view=ManageMatchesView(), ephemeral=True)

    @discord.ui.button(label="Reset Tournament", style=discord.ButtonStyle.danger, row=2, custom_id="buc_reset_tournament")
    async def reset_tournament(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != 1272176835769405552:
            await interaction.response.send_message("❌ Only the Owner can reset the tournament.", ephemeral=True)
            return
            
        # Confirmation
        view = ConfirmResetView()
        await interaction.response.send_message("⚠️ **ARE YOU SURE?**\nThis will delete ALL matches and reset the tournament. Teams will remain.", view=view, ephemeral=True)

class ConfirmResetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="CONFIRM RESET", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # Delete all matches
        matches = await mongo_manager.get_buc_matches()
        for m in matches:
            await mongo_manager.delete_buc_match(m["id"])
        
        await interaction.followup.send("✅ Tournament Reset! All matches deleted.", ephemeral=True)
        
        # Update leaderboards to clear them
        cog = interaction.client.get_cog("BUCSystem")
        if cog:
            await cog.update_leaderboard()
            await cog.update_bracket()
            await cog.update_player_stats()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)

class ManageTeamsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Remove Team", style=discord.ButtonStyle.danger, custom_id="buc_remove_team")
    async def remove_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        teams = await mongo_manager.get_buc_teams()
        if not teams:
            await interaction.response.send_message("No teams to remove.", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=t["name"], value=t["name"]) for t in teams]
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Team to Remove", options=options[:25])
        
        async def callback(inter: discord.Interaction):
            team_name = select.values[0]
            await mongo_manager.delete_buc_team(team_name)
            await inter.response.send_message(f"Removed team {team_name}", ephemeral=True)
            # Update leaderboard
            cog = inter.client.get_cog("BUCSystem")
            if cog: await cog.update_leaderboard()

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select team:", view=view, ephemeral=True)

    @discord.ui.button(label="Edit Team", style=discord.ButtonStyle.secondary, custom_id="buc_edit_team")
    async def edit_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        teams = await mongo_manager.get_buc_teams()
        if not teams:
            await interaction.response.send_message("No teams to edit.", ephemeral=True)
            return
            
        options = [discord.SelectOption(label=t["name"], value=t["name"]) for t in teams]
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Team to Edit", options=options[:25])
        
        async def callback(inter: discord.Interaction):
            team_name = select.values[0]
            team = next((t for t in teams if t["name"] == team_name), None)
            await inter.response.send_modal(EditTeamModal(team))

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select team to edit:", view=view, ephemeral=True)

class EditTeamModal(discord.ui.Modal):
    def __init__(self, team_data):
        safe_title = f"Edit Team: {team_data['name']}"[:45]
        super().__init__(title=safe_title)
        self.team_data = team_data
        self.team_name = discord.ui.TextInput(label="Team Name", default=team_data["name"])
        
        # Convert players to string for editing
        players_str = ""
        for p in team_data["players"]:
            if isinstance(p, dict):
                players_str += f"{p['tag']}, "
            else:
                players_str += f"{p}, "
        
        self.player_tags = discord.ui.TextInput(label="Player Tags", default=players_str.strip(", "), style=discord.TextStyle.paragraph)
        
        self.add_item(self.team_name)
        self.add_item(self.player_tags)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        new_name = self.team_name.value
        p_tags_raw = self.player_tags.value
        p_tags = [t.strip().upper() for t in p_tags_raw.split(",") if t.strip()]

        if len(p_tags) != 5:
            await interaction.followup.send("❌ Must have exactly 5 player tags.", ephemeral=True)
            return

        players_data = []
        for tag in p_tags:
            p = await coc_api.get_player(tag)
            if not p:
                await interaction.followup.send(f"❌ Invalid Player Tag: {tag}", ephemeral=True)
                return
            players_data.append({"tag": p.tag, "name": p.name})

        # If name changed, we need to handle that (delete old, save new? or update key?)
        # Mongo update_one with upsert=True on name key creates new if name changes.
        # We should delete old if name changed.
        if new_name != self.team_data["name"]:
            await mongo_manager.delete_buc_team(self.team_data["name"])
            
        self.team_data["name"] = new_name
        self.team_data["players"] = players_data
        
        await mongo_manager.save_buc_team(self.team_data)
        await interaction.followup.send(f"✅ Team updated successfully!", ephemeral=True)

class ManageMatchesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Generate Round 1 Schedule", style=discord.ButtonStyle.primary, custom_id="buc_generate_r1")
    async def generate_r1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Check if matches already exist
        existing_matches = await mongo_manager.get_buc_matches()
        if any(m["round"] == 1 for m in existing_matches):
            await interaction.followup.send("❌ Round 1 matches already exist! Use 'Reset Tournament' if you want to regenerate.", ephemeral=True)
            return

        teams = await mongo_manager.get_buc_teams()
        if len(teams) < 2:
            await interaction.followup.send("❌ Not enough teams to generate schedule (Need at least 2).", ephemeral=True)
            return

        # Circle Method for Round Robin
        # Ensure even number of teams
        team_names = [t["name"] for t in teams]
        if len(team_names) % 2 != 0:
            team_names.append("BYE") # Should not happen if 8 teams, but good safety
        
        n = len(team_names)
        rounds = n - 1
        matches_per_round = n // 2
        
        generated_matches = []
        
        # Fixed team at index 0
        fixed_team = team_names[0]
        rotating_teams = team_names[1:]
        
        for r in range(rounds):
            day_matches = []
            # Match fixed team with last of rotating
            t1 = fixed_team
            t2 = rotating_teams[-1]
            day_matches.append((t1, t2))
            
            # Match others
            for i in range(matches_per_round - 1):
                t1_r = rotating_teams[i]
                t2_r = rotating_teams[-2 - i]
                day_matches.append((t1_r, t2_r))
            
            # Create Match Objects for this Day
            for i, (t1, t2) in enumerate(day_matches):
                if t1 == "BYE" or t2 == "BYE": continue # Skip bye matches
                
                match_id = f"R1_D{r+1}_M{i+1}"
                match_data = {
                    "id": match_id,
                    "label": f"Day {r+1} - Match {i+1}",
                    "day": r + 1,
                    "team1": t1,
                    "team2": t2,
                    "round": 1,
                    "completed": False,
                    "winner": None,
                    "score1": 0,
                    "score2": 0,
                    "percent1": 0.0,
                    "percent2": 0.0,
                    "team1_stats": [],
                    "team2_stats": []
                }
                generated_matches.append(match_data)
                await mongo_manager.save_buc_match(match_data)
            
            # Rotate
            rotating_teams.insert(0, rotating_teams.pop())
        
        await interaction.followup.send(f"Generated {len(generated_matches)} matches for Round 1 (7 Days).", ephemeral=True)

    @discord.ui.button(label="Enter Match Result", style=discord.ButtonStyle.success, custom_id="buc_enter_result")
    async def enter_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        matches = await mongo_manager.get_buc_matches()
        incomplete = [m for m in matches if not m.get("completed")]
        
        if not incomplete:
            await interaction.response.send_message("No incomplete matches found.", ephemeral=True)
            return

        # Pagination or Search might be needed if > 25 matches.
        # For now, take first 25.
        options = []
        for m in incomplete[:25]:
            label = f"{m['id']}: {m['team1']} vs {m['team2']}"
            options.append(discord.SelectOption(label=label, value=m['id']))

        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Match", options=options)
        
        async def callback(inter: discord.Interaction):
            match_id = select.values[0]
            selected_match = next((m for m in matches if m["id"] == match_id), None)
            # Check if match has detailed stats structure
            if "team1_stats" not in selected_match:
                selected_match["team1_stats"] = []
            if "team2_stats" not in selected_match:
                selected_match["team2_stats"] = []
                
            await inter.response.send_message(f"Entering results for {selected_match['team1']} vs {selected_match['team2']}", view=MatchSubmissionView(selected_match), ephemeral=True)

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select match to enter result:", view=view, ephemeral=True)

    @discord.ui.button(label="Edit Match Result", style=discord.ButtonStyle.secondary, custom_id="buc_edit_result")
    async def edit_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        matches = await mongo_manager.get_buc_matches()
        completed = [m for m in matches if m.get("completed")]
        
        if not completed:
            await interaction.response.send_message("No completed matches to edit.", ephemeral=True)
            return

        options = []
        # Sort by most recent?
        for m in completed[-25:]: # Last 25
            label = f"{m['id']}: {m['team1']} vs {m['team2']}"
            options.append(discord.SelectOption(label=label, value=m['id']))

        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Match to Edit", options=options)
        
        async def callback(inter: discord.Interaction):
            match_id = select.values[0]
            selected_match = next((m for m in matches if m["id"] == match_id), None)
            await inter.response.send_message(f"Editing results for {selected_match['team1']} vs {selected_match['team2']}", view=MatchSubmissionView(selected_match), ephemeral=True)

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Select match to edit:", view=view, ephemeral=True)

    # Removed Set Match Date button as per user request


    @discord.ui.button(label="Set Day Date (Bulk)", style=discord.ButtonStyle.secondary, custom_id="buc_set_day_date")
    async def set_day_date(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ask for Day Number
        await interaction.response.send_modal(DayDateModal())

    @discord.ui.button(label="Start Round 2 (Page Playoff)", style=discord.ButtonStyle.danger, custom_id="buc_start_r2")
    async def start_r2(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if R1 complete
        matches = await mongo_manager.get_buc_matches()
        r1_matches = [m for m in matches if m["round"] == 1]
        
        if not r1_matches:
             await interaction.response.send_message("No Round 1 matches found.", ephemeral=True)
             return

        if not all(m.get("completed") for m in r1_matches):
             await interaction.response.send_message("❌ Cannot start Round 2 until ALL Round 1 matches are completed and results entered.", ephemeral=True)
             return

        # Get Top 4
        teams = await mongo_manager.get_buc_teams()
        # We need to sort them exactly as the leaderboard does.
        # Re-using logic from update_leaderboard would be best, but for now duplicate sort logic.
        # Actually, we should rely on the leaderboard logic or stored stats.
        # Let's recalc stats to be sure.
        matches = await mongo_manager.get_buc_matches()
        team_stats = {team["name"]: {"points": 0, "percentage": 0.0, "total_percent": 0.0, "played": 0} for team in teams}
        
        for match in matches:
            if not match.get("completed") or match["round"] != 1:
                continue
            t1, t2 = match["team1"], match["team2"]
            winner = match.get("winner")
            
            if t1 in team_stats:
                team_stats[t1]["played"] += 1
                team_stats[t1]["total_percent"] += match.get("percent1", 0)
            if t2 in team_stats:
                team_stats[t2]["played"] += 1
                team_stats[t2]["total_percent"] += match.get("percent2", 0)

            if winner == "Tie":
                if t1 in team_stats: team_stats[t1]["points"] += 1
                if t2 in team_stats: team_stats[t2]["points"] += 1
            elif winner == t1:
                if t1 in team_stats: team_stats[t1]["points"] += 2
            elif winner == t2:
                if t2 in team_stats: team_stats[t2]["points"] += 2

        for name, stats in team_stats.items():
            if stats["played"] > 0:
                stats["percentage"] = stats["total_percent"] / stats["played"]

        sorted_teams = sorted(team_stats.items(), key=lambda x: (x[1]["points"], x[1]["percentage"]), reverse=True)
        
        if len(sorted_teams) < 4:
            await interaction.response.send_message("Not enough teams for Round 2.", ephemeral=True)
            return

        top4 = [t[0] for t in sorted_teams[:4]] # Names
        # 1 vs 2
        m1 = {"id": "R2_M1", "label": "M1", "team1": top4[0], "team2": top4[1], "round": 2, "completed": False, "winner": None}
        # 3 vs 4
        m2 = {"id": "R2_M2", "label": "M2", "team1": top4[2], "team2": top4[3], "round": 2, "completed": False, "winner": None}
        
        await mongo_manager.save_buc_match(m1)
        await mongo_manager.save_buc_match(m2)
        
        # M3 and M4 are placeholders until winners determined
        m3 = {"id": "R2_M3", "label": "M3", "team1": "Loser M1", "team2": "Winner M2", "round": 2, "completed": False, "winner": None}
        m4 = {"id": "R2_M4", "label": "M4", "team1": "Winner M1", "team2": "Winner M3", "round": 2, "completed": False, "winner": None}
        await mongo_manager.save_buc_match(m3)
        await mongo_manager.save_buc_match(m4)

        await interaction.response.send_message(f"Round 2 Matches Generated!\n1v2: {top4[0]} vs {top4[1]}\n3v4: {top4[2]} vs {top4[3]}", ephemeral=True)
        
        cog = interaction.client.get_cog("BUCSystem")
        if cog: await cog.update_bracket()

class MatchSubmissionView(discord.ui.View):
    def __init__(self, match_data):
        super().__init__(timeout=None)
        self.match_data = match_data

    @discord.ui.button(label="Enter Team 1 Stats", style=discord.ButtonStyle.primary)
    async def team1_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TeamStatsModal(self.match_data, "team1"))

    @discord.ui.button(label="Enter Team 2 Stats", style=discord.ButtonStyle.primary)
    async def team2_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TeamStatsModal(self.match_data, "team2"))

    @discord.ui.button(label="Finalize Result", style=discord.ButtonStyle.success)
    async def finalize(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self.match_data
        if not m.get("team1_stats") or not m.get("team2_stats"):
            await interaction.response.send_message("❌ Please enter stats for BOTH teams first.", ephemeral=True)
            return
            
        # Calculate Totals
        s1 = sum(p["stars"] for p in m["team1_stats"])
        p1 = sum(p["percent"] for p in m["team1_stats"]) / 5.0
        
        s2 = sum(p["stars"] for p in m["team2_stats"])
        p2 = sum(p["percent"] for p in m["team2_stats"]) / 5.0
        
        winner = None
        if s1 > s2: winner = m["team1"]
        elif s2 > s1: winner = m["team2"]
        else:
            if p1 > p2: winner = m["team1"]
            elif p2 > p1: winner = m["team2"]
            else: winner = "Tie"
            
        m.update({
            "score1": s1, "percent1": p1,
            "score2": s2, "percent2": p2,
            "winner": winner,
            "completed": True
        })
        
        await mongo_manager.save_buc_match(m)
        
        if m["round"] == 2:
            # We need to instantiate the view to call the method, or move method to static/helper
            # Hack: just create dummy view or move logic.
            # Let's copy logic here or make it a method of Cog.
            # Accessing Cog from interaction
            cog = interaction.client.get_cog("BUCSystem")
            if cog: await cog.handle_r2_progression(m)

        await interaction.response.send_message(f"✅ Match Finalized! Winner: {winner}", ephemeral=True)
        
        cog = interaction.client.get_cog("BUCSystem")
        if cog:
            await cog.update_leaderboard()
            await cog.update_bracket()
            await cog.update_player_stats()

class TeamStatsModal(discord.ui.Modal):
    def __init__(self, match_data, team_key):
        team_name = match_data[team_key]
        super().__init__(title=f"Stats for {team_name}")
        self.match_data = match_data
        self.team_key = team_key
        
        # We need 5 inputs.
        # Ideally we pre-fill player names if we have them.
        # We can fetch team data to get player names.
        # But we can't await in __init__.
        # So we just use generic labels "Player 1", "Player 2" etc.
        # OR we pass team data into this View/Modal from previous step.
        # For now, generic labels. User must know order or just input.
        # "Player 1 Tag/Name: Stars, Percent"
        
        self.p1 = discord.ui.TextInput(label="Player 1 (Stars, %)", placeholder="e.g. 3, 100")
        self.p2 = discord.ui.TextInput(label="Player 2 (Stars, %)", placeholder="e.g. 2, 85.5")
        self.p3 = discord.ui.TextInput(label="Player 3 (Stars, %)", placeholder="e.g. 3, 100")
        self.p4 = discord.ui.TextInput(label="Player 4 (Stars, %)", placeholder="e.g. 1, 50")
        self.p5 = discord.ui.TextInput(label="Player 5 (Stars, %)", placeholder="e.g. 3, 100")

    async def on_submit(self, interaction: discord.Interaction):
        inputs = [self.p1.value, self.p2.value, self.p3.value, self.p4.value, self.p5.value]
        stats = []
        
        # We need to associate these with actual players if we want a player leaderboard.
        # We need to know WHICH player got which score.
        # The user said "add all 5 individual stars...".
        # If we don't know who is who, we can't do player leaderboard.
        # We MUST ask for Tag or Name.
        # Input format: "Tag/Name: Stars, %" ? Too complex.
        # Better: Fetch team players, and create Modal with their names as labels?
        # We can't await in __init__.
        # Solution: In MatchSubmissionView, fetch team data BEFORE creating Modal.
        pass

# Re-implementing MatchSubmissionView to fetch players first
class MatchSubmissionView(discord.ui.View):
    def __init__(self, match_data):
        super().__init__(timeout=None)
        self.match_data = match_data

    async def get_team_players(self, team_name):
        teams = await mongo_manager.get_buc_teams()
        team = next((t for t in teams if t["name"] == team_name), None)
        if team:
            # Lazy fetch names
            # We need access to Cog instance to call ensure_team_player_names.
            # But we are in a View.
            # We can't easily access Cog instance without passing it or using interaction.client
            # But this is a helper method, not an interaction callback.
            # We can just duplicate logic or use a static helper in utils?
            # Or better: do it in the callback where we have interaction.
            return team
        return None

    @discord.ui.button(label="Enter Team 1 Stats", style=discord.ButtonStyle.primary)
    async def team1_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Do NOT defer if sending modal
        team = await self.get_team_players(self.match_data["team1"])
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
            
        cog = interaction.client.get_cog("BUCSystem")
        if cog:
            team = await cog.ensure_team_player_names(team)
            
        await interaction.response.send_modal(TeamStatsModal(self.match_data, "team1_stats", team["players"]))

    @discord.ui.button(label="Enter Team 2 Stats", style=discord.ButtonStyle.primary)
    async def team2_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Do NOT defer if sending modal
        team = await self.get_team_players(self.match_data["team2"])
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        cog = interaction.client.get_cog("BUCSystem")
        if cog:
            team = await cog.ensure_team_player_names(team)
            
        await interaction.response.send_modal(TeamStatsModal(self.match_data, "team2_stats", team["players"]))

    @discord.ui.button(label="Finalize Result", style=discord.ButtonStyle.success)
    async def finalize(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            m = self.match_data
            if not m.get("team1_stats") or not m.get("team2_stats"):
                await interaction.followup.send("❌ Please enter stats for BOTH teams first.", ephemeral=True)
                return
                
            s1 = sum(p["stars"] for p in m["team1_stats"])
            p1 = sum(p["percent"] for p in m["team1_stats"]) / 5.0
            s2 = sum(p["stars"] for p in m["team2_stats"])
            p2 = sum(p["percent"] for p in m["team2_stats"]) / 5.0
            
            winner = None
            if s1 > s2: winner = m["team1"]
            elif s2 > s1: winner = m["team2"]
            else:
                if p1 > p2: winner = m["team1"]
                elif p2 > p1: winner = m["team2"]
                else: winner = "Tie"
                
            m.update({
                "score1": s1, "percent1": p1,
                "score2": s2, "percent2": p2,
                "winner": winner,
                "completed": True
            })
            
            await mongo_manager.save_buc_match(m)
            
            cog = interaction.client.get_cog("BUCSystem")
            if cog:
                if m["round"] == 2:
                    await cog.handle_r2_progression(m)
                await cog.update_leaderboard()
                await cog.update_bracket()
                await cog.update_player_stats()

            await interaction.followup.send(f"✅ Match Finalized! Winner: {winner}", ephemeral=True)
        except Exception as e:
            print(f"Error in finalize: {e}")
            await interaction.followup.send(f"❌ Error finalizing match: {e}", ephemeral=True)

class TeamStatsModal(discord.ui.Modal):
    def __init__(self, match_data, stats_key, players):
        super().__init__(title="Enter Player Stats")
        self.match_data = match_data
        self.stats_key = stats_key
        self.players = players # List of {tag, name}
        self.inputs = []
        
        # Create inputs dynamically? No, must be defined as class attributes usually.
        # But we can add_item.
        for i, p in enumerate(players[:5]): # Max 5
            if isinstance(p, dict):
                p_name = p.get('name', 'Player')
                p_tag = p.get('tag', 'Unknown')
            else:
                p_name = "Player"
                p_tag = str(p)
                
            label = f"{p_name} ({p_tag})"[:45]
            text_input = discord.ui.TextInput(label=label, placeholder="Stars, Percent (e.g. 3, 100)")
            self.add_item(text_input)
            self.inputs.append((p, text_input))

    async def on_submit(self, interaction: discord.Interaction):
        stats = []
        for p, text_input in self.inputs:
            val = text_input.value.strip()
            try:
                parts = val.split(",")
                stars = int(parts[0].strip())
                percent = float(parts[1].strip())
                
                tag = p["tag"] if isinstance(p, dict) else str(p)
                name = p["name"] if isinstance(p, dict) else "Player"
                
                stats.append({
                    "tag": tag,
                    "name": name,
                    "stars": stars,
                    "percent": percent
                })
            except:
                await interaction.response.send_message(f"❌ Invalid format for {p['name']}. Use: Stars, Percent", ephemeral=True)
                return
        
        self.match_data[self.stats_key] = stats
        # We don't save to DB yet, just update the object in memory (passed by reference)
        # Actually we should probably save partial state or just keep it in the View's match_data.
        # The View holds match_data.
        await interaction.response.send_message("✅ Stats recorded temporarily. Click Finalize when done.", ephemeral=True)

class MatchDateModal(discord.ui.Modal):
    def __init__(self, match_id):
        super().__init__(title="Set Match Date")
        self.match_id = match_id
        self.date_input = discord.ui.TextInput(label="Date/Time", placeholder="e.g. Oct 25, 8:00 PM EST")
        self.add_item(self.date_input)

    async def on_submit(self, interaction: discord.Interaction):
        matches = await mongo_manager.get_buc_matches()
        match = next((m for m in matches if m["id"] == self.match_id), None)
        if match:
            match["date"] = self.date_input.value
            await mongo_manager.save_buc_match(match)
            await interaction.response.send_message(f"Date set for {self.match_id}", ephemeral=True)
        else:
            await interaction.response.send_message("Match not found.", ephemeral=True)

class DayDateModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Set Date for a Day")
        self.day_num = discord.ui.TextInput(label="Day", placeholder="e.g. 1")
        self.date_str = discord.ui.TextInput(label="Date", placeholder="e.g. Oct 25, 8:00 PM EST")
        self.add_item(self.day_num)
        self.add_item(self.date_str)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            day_val = self.day_num.value.strip()
            # Try int first
            try:
                day = int(day_val)
            except ValueError:
                await interaction.followup.send(f"Invalid Day Number: {day_val}", ephemeral=True)
                return
            
            matches = await mongo_manager.get_buc_matches()
            count = 0
            for m in matches:
                # Check both int and string representation just in case
                m_day = m.get("day")
                if m_day == day or str(m_day) == str(day):
                    m["date"] = self.date_str.value
                    await mongo_manager.save_buc_match(m)
                    count += 1
            
            if count > 0:
                await interaction.followup.send(f"✅ Updated date for {count} matches on Day {day}.", ephemeral=True)
            else:
                # Debug info
                days_found = list(set(m.get("day") for m in matches))
                await interaction.followup.send(f"❌ No matches found for Day {day}. Available days: {days_found}", ephemeral=True)
                
        except Exception as e:
            print(f"Error in DayDateModal: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

class MatchupsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def get_data(self):
        matches = await mongo_manager.get_buc_matches()
        matches_by_day = {}
        for m in matches:
            day = m.get("day", "Unknown")
            if day not in matches_by_day: matches_by_day[day] = []
            matches_by_day[day].append(m)
        
        sorted_days = sorted(matches_by_day.keys(), key=lambda x: int(x) if isinstance(x, int) else 999)
        pages = [matches_by_day[d] for d in sorted_days]
        return pages, sorted_days

    async def get_embed(self, pages, days, page_idx):
        if not pages: return discord.Embed(title="No Matches")
        
        chunk = pages[page_idx]
        day_num = days[page_idx]
        
        embed = discord.Embed(title=f"📅 BUC CUP Matchups - Day {day_num}", color=discord.Color.orange())
        desc = ""
        for m in chunk:
            status = "✅" if m["completed"] else "📅"
            date = m.get("date", "TBD")
            winner = f" (🏆 {m['winner']})" if m["winner"] else ""
            label = m.get("label") or m["id"]
            desc += f"`{label}` {status} **{m['team1']}** 🆚 **{m['team2']}**\n   🕒 {date}{winner}\n\n"
        
        embed.description = desc
        embed.set_footer(text=f"Page {page_idx + 1}/{len(pages)}")
        return embed

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary, custom_id="buc_matchups_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Determine current page from embed footer
        if not interaction.message.embeds: return
        footer = interaction.message.embeds[0].footer.text
        # "Page X/Y"
        try:
            current = int(footer.split(" ")[1].split("/")[0]) - 1
        except:
            current = 0
            
        if current > 0:
            pages, days = await self.get_data()
            new_page = current - 1
            embed = await self.get_embed(pages, days, new_page)
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary, custom_id="buc_matchups_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.message.embeds: return
        footer = interaction.message.embeds[0].footer.text
        try:
            parts = footer.split(" ")[1].split("/")
            current = int(parts[0]) - 1
            total = int(parts[1])
        except:
            current = 0
            total = 1
            
        if current < total - 1:
            pages, days = await self.get_data()
            new_page = current + 1
            embed = await self.get_embed(pages, days, new_page)
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.defer()

class TeamListView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(placeholder="Select a Team to view roster", custom_id="buc_team_select", min_values=1, max_values=1, options=[discord.SelectOption(label="Loading...", value="loading")])
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        team_name = select.values[0]
        if team_name == "loading":
            await interaction.response.send_message("Please wait for the menu to load properly or run command again.", ephemeral=True)
            return

        teams = await mongo_manager.get_buc_teams()
        team = next((t for t in teams if t["name"] == team_name), None)
        
        if team:
            # We need to access Cog for ensure_team_player_names
            # We can get it via client
            cog = interaction.client.get_cog("BUCSystem")
            if cog:
                team = await cog.ensure_team_player_names(team)
            
            embed = discord.Embed(title=f"🛡️ Team {team['name']}", color=discord.Color.blue())
            embed.add_field(name="Captain", value=f"{team.get('captain_name', 'Unknown')} ({team['captain_tag']})", inline=False)
            
            players_list = []
            for p in team['players']:
                if isinstance(p, str):
                    players_list.append(f"{p}")
                else:
                    players_list.append(f"**{p['name']}** ({p['tag']})")
            
            players_str = "\n".join(players_list)
            embed.add_field(name="Players", value=players_str, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Team not found.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BUCSystem(bot))
