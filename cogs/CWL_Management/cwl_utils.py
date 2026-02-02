import datetime

class CWLUtils:
    @staticmethod
    def get_current_season():
        # Returns "Month Year", e.g. "January 2026"
        # Since CWL is usually the first week of the month, we generally refer to the current month.
        now = datetime.datetime.utcnow()
        return now.strftime("%B %Y")

    @staticmethod
    def sort_assignments_by_th(assignments):
        # Sorts by Town Hall DESC
        # assignments is a list of dicts with 'town_hall' key
        return sorted(assignments, key=lambda x: int(x.get('town_hall', 0)), reverse=True)

    @staticmethod
    def format_overview(assignments_by_source):
        # assignments_by_source: { source_clan_name: [assignments...] }
        # Output: Plain text blocks.
        output = ""
        for source, players in assignments_by_source.items():
            output += f"**{source}**\n"
            # Group by dest? No, the prompt says: "Count-based (TH x count -> destination clan)"
            # Example: 3x TH16 -> Clan A
            
            # Need to group players by Dest + TH
            grouped = {} # (DetClan, TH) -> count
            for p in players:
                key = (p['dest_clan'], p['town_hall'])
                grouped[key] = grouped.get(key, 0) + 1
            
            # Sort keys by TH desc
            sorted_keys = sorted(grouped.keys(), key=lambda k: k[1], reverse=True)
            
            for dest, th in sorted_keys:
                count = grouped[(dest, th)]
                output += f"{count}x TH{th} -> {dest}\n"
            output += "\n"
        return output

    @staticmethod
    def format_clan_details(dest_clan_name, assignments, clan_link=None):
        # Create detailed list
        # Header: MONTH CWL TRANSACTION LIST :
        # Grouped by Dest Client (Only one here)
        # Player-level list
        
        output = f"**{dest_clan_name.upper()} CWL TRANSACTION LIST** :\n\n"
        
        # Sort by TH Desc
        sorted_players = CWLUtils.sort_assignments_by_th(assignments)
        
        for p in sorted_players:
            output += f"{p['player_name']} (TH{p['town_hall']})\n"
            
        if clan_link:
            output += f"\nLink: {clan_link}\n"
            
        return output

cwl_utils = CWLUtils()

async def setup(bot):
    pass
