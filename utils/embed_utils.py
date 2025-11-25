import discord

def create_invite_embed(clan_name, leader_id, leadership_role_id, logo_url, inviter_mention):
    leader_mention = f"<@{leader_id}>" if leader_id else "Leader"
    leadership_mention = f"<@&{leadership_role_id}>" if leadership_role_id else "Leadership"
    
    embed = discord.Embed(
        title=f"🌟 Invitation to {clan_name} 🌟",
        description=f"🎉 **Congratulations!** You have been accepted into **{clan_name}**!\n\n"
                    f"👑 **Clan Leader:** {leader_mention}\n"
                    f"🛡️ **Leadership Team:** {leadership_mention}\n\n"
                    "We are thrilled to have you join our family! Please review the information below.",
        color=discord.Color.gold()
    )
    
    if logo_url:
        embed.set_image(url=logo_url)

    rules_text = (
        "**1. Communication is Key**\n"
        "Please keep player acceptance and rejection messages in the designated channels, not DMs.\n\n"
        "**2. Flexibility & Growth**\n"
        "• **Reapply Anytime:** If this clan isn't the perfect fit, you are welcome to apply to other clans in our family.\n"
        "• **CWL Flexibility:** We allow shifting between clans to ensure everyone gets the best CWL match.\n\n"
        "**3. Community Spirit**\n"
        "• **One Big Family:** All BSN clans support each other. We win together!\n"
        "• **Request Message:** Please use **'BSN FAM'** in your in-game join request so we know you're from Discord."
    )
    
    embed.add_field(name="📜 Important Guidelines", value=rules_text, inline=False)
    embed.add_field(name="🤝 Invited By", value=inviter_mention, inline=False)
    embed.set_footer(text="Welcome to the Blackspire Nation!", icon_url=logo_url if logo_url else None)
        
    return embed

def create_rejection_embed(clan_name, user_id):
    embed = discord.Embed(
        title="Application Status Update",
        description=f"Hello <@{user_id}>,\n\n"
                    f"Thank you for your interest in joining **{clan_name}**. \n\n"
                    "At this moment, we unfortunately **do not have any open spots** available that match your current profile. "
                    "However, spots open up regularly, and we would love to see you **apply again** in the future!\n\n"
                    "Please don't be discouraged. We appreciate your time and wish you the very best in your Clash of Clans journey! ⚔️",
        color=discord.Color.red()
    )
    embed.set_footer(text="Blackspire Nation Recruitment")
    return embed
