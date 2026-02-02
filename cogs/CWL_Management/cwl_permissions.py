import discord
import os
from .cwl_models import cwl_models

class CWLPermissions:
    @staticmethod
    def is_owner(interaction: discord.Interaction):
        return interaction.user.id == int(os.getenv("OWNER_ID"))

    @staticmethod
    async def is_manager(interaction: discord.Interaction):
        # Check Owner
        if CWLPermissions.is_owner(interaction): return True
        
        # Check Database
        managers = await cwl_models.get_managers()
        user_ids = [m.get("user_id") for m in managers if m.get("user_id")]
        role_ids = [m.get("role_id") for m in managers if m.get("role_id")]
        
        if interaction.user.id in user_ids: return True
        
        # Check Roles
        if hasattr(interaction.user, 'roles'):
            for role in interaction.user.roles:
                if role.id in role_ids: return True
        
        return False

    @staticmethod
    async def is_rep(interaction: discord.Interaction, season, clan_tag=None):
        # Check Owner or Manager
        if await CWLPermissions.is_manager(interaction): return True
        
        # If clan_tag is specific, check for that clan
        if clan_tag:
            reps = await cwl_models.get_reps(season, clan_tag)
            return interaction.user.id in reps
        
        # If no clan_tag specified, check if they are rep for ANY clan (less common, usually specific)
        all_reps = await cwl_models.get_all_reps(season)
        for doc in all_reps:
            if interaction.user.id in doc.get("user_ids", []):
                return True
        return False

    @staticmethod
    def is_leader_or_co(interaction: discord.Interaction):
        # This is tricky without a direct "Clan Leader" role mapping in DB.
        # We generally check for specific Discord roles 'Leader' or 'Co-Leader'.
        # Since this is a custom bot for BSN, we can assume standard role names or IDs.
        # For now, we will check for roles named "Leader", "Co-Leader", "Clan Leader" (case insensitive).
        # OR we can assume if they have write access into clan channels?
        # Let's stick to Role Names for now as a safe default for "Family CWL Forum".
        # The prompt says "Access: Clan Leader, Clan Co-Leader".
        
        if CWLPermissions.is_owner(interaction): return True
        
        allowed_role_names = ["leader", "co-leader", "clan leader", "clan co-leader", "grand warden"]
        if hasattr(interaction.user, 'roles'):
            return any(r.name.lower() in allowed_role_names for r in interaction.user.roles)
        return False

cwl_permissions = CWLPermissions()

async def setup(bot):
    pass
