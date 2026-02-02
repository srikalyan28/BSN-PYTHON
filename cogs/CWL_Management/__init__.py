import discord
from discord.ext import commands

async def setup(bot):
    # Import and add cogs here
    # We will likely have a main CWL cog that manages sub-components or import them all
    # For now, let's load the main management cog
    from .cwl_management import CWLManagementCog
    from .cwl_forum import CWLForumCog
    from .cwl_posting import CWLPostingCog
    
    await bot.add_cog(CWLManagementCog(bot))
    await bot.add_cog(CWLForumCog(bot))
    await bot.add_cog(CWLPostingCog(bot))
