from utils.mongo_manager import mongo_manager
import datetime

class CWLModels:
    """
    Handles all database interactions for the Advanced CWL Management System.
    """
    
    # --- SEASONS ---
    @staticmethod
    async def get_active_season():
        db = await mongo_manager.get_collection("cwl_seasons")
        return await db.find_one({"status": "active"})

    @staticmethod
    async def set_active_season(season_name):
        db = await mongo_manager.get_collection("cwl_seasons")
        await db.update_many({"status": "active"}, {"$set": {"status": "archived"}})
        await db.update_one(
            {"season": season_name},
            {"$set": {"status": "active", "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )

    # --- MANAGERS ---
    @staticmethod
    async def add_manager(user_id=None, role_id=None):
        db = await mongo_manager.get_collection("cwl_managers")
        data = {"created_at": datetime.datetime.utcnow()}
        if user_id: data["user_id"] = user_id
        if role_id: data["role_id"] = role_id
        await db.insert_one(data)

    @staticmethod
    async def remove_manager(user_id=None, role_id=None):
        db = await mongo_manager.get_collection("cwl_managers")
        query = {}
        if user_id: query["user_id"] = user_id
        if role_id: query["role_id"] = role_id
        if query: await db.delete_one(query)

    @staticmethod
    async def get_managers():
        db = await mongo_manager.get_collection("cwl_managers")
        cursor = db.find({})
        return [doc async for doc in cursor]

    # --- REPRESENTATIVES ---
    @staticmethod
    async def add_rep(season, clan_tag, user_id):
        db = await mongo_manager.get_collection("cwl_representatives")
        await db.update_one(
            {"season": season, "clan_tag": clan_tag},
            {"$addToSet": {"user_ids": user_id}},
            upsert=True
        )

    @staticmethod
    async def remove_rep(season, clan_tag, user_id):
        db = await mongo_manager.get_collection("cwl_representatives")
        await db.update_one(
            {"season": season, "clan_tag": clan_tag},
            {"$pull": {"user_ids": user_id}}
        )

    @staticmethod
    async def get_reps(season, clan_tag):
        db = await mongo_manager.get_collection("cwl_representatives")
        doc = await db.find_one({"season": season, "clan_tag": clan_tag})
        return doc["user_ids"] if doc else []

    # --- WIZARD STATE ---
    @staticmethod
    async def save_state(channel_id, state_data):
        db = await mongo_manager.get_collection("cwl_state")
        await db.update_one(
            {"channel_id": channel_id},
            {"$set": state_data},
            upsert=True
        )

    @staticmethod
    async def get_state(channel_id):
        db = await mongo_manager.get_collection("cwl_state")
        return await db.find_one({"channel_id": channel_id})

    @staticmethod
    async def delete_state(channel_id):
        db = await mongo_manager.get_collection("cwl_state")
        await db.delete_one({"channel_id": channel_id})

    # --- FORUM DATA (Metadata) ---
    @staticmethod
    async def save_forum_metadata(season, clan_tag, data):
        db = await mongo_manager.get_collection("cwl_forums")
        update_data = {
            "season": season,
            "clan_tag": clan_tag,
            "updated_at": datetime.datetime.utcnow(),
            **data
        }
        await db.update_one(
            {"season": season, "clan_tag": clan_tag},
            {"$set": update_data},
            upsert=True
        )

    @staticmethod
    async def get_forum_metadata(season, clan_tag):
        db = await mongo_manager.get_collection("cwl_forums")
        return await db.find_one({"season": season, "clan_tag": clan_tag})

    @staticmethod
    async def get_forum_by_channel(season, channel_id):
        db = await mongo_manager.get_collection("cwl_forums")
        # Ensure channel_id is stored as int or match how it was saved
        return await db.find_one({"season": season, "channel_id": channel_id})

    # --- OVERFLOWS (Players Available) ---
    @staticmethod
    async def add_overflow(season, source_clan_tag, player_tag, name, th):
        db = await mongo_manager.get_collection("cwl_overflows")
        await db.update_one(
            {"season": season, "player_tag": player_tag},
            {"$set": {
                "source_clan": source_clan_tag,
                "player_name": name,
                "player_th": th,
                "status": "available", # or 'allotted'
                "allotted_to_tag": None,
                "allotted_to_name": None,
                "updated_at": datetime.datetime.utcnow()
            }},
            upsert=True
        )

    @staticmethod
    async def get_overflows(season, source_clan=None, min_th=None, status=None):
        db = await mongo_manager.get_collection("cwl_overflows")
        query = {"season": season}
        if source_clan: query["source_clan"] = source_clan
        if status: query["status"] = status
        if min_th: query["player_th"] = {"$gte": min_th}
        
        cursor = db.find(query)
        return [doc async for doc in cursor]

    @staticmethod
    async def update_overflow_status(season, player_tag, status, allotted_to_tag=None, allotted_to_name=None):
        db = await mongo_manager.get_collection("cwl_overflows")
        update = {"status": status}
        if allotted_to_tag is not None: update["allotted_to_tag"] = allotted_to_tag
        if allotted_to_name is not None: update["allotted_to_name"] = allotted_to_name
        
        await db.update_one(
            {"season": season, "player_tag": player_tag},
            {"$set": update}
        )
        
    @staticmethod
    async def clear_clan_overflows(season, clan_tag):
        # Used when resetting forum wizard 
        db = await mongo_manager.get_collection("cwl_overflows")
        await db.delete_many({"season": season, "source_clan": clan_tag})

    # --- REQUIREMENTS (Help Needed) ---
    @staticmethod
    async def set_requirement(season, clan_tag, th, count):
        db = await mongo_manager.get_collection("cwl_requirements")
        await db.update_one(
            {"season": season, "clan_tag": clan_tag, "th_level": th},
            {"$set": {"count_needed": count, "count_allotted": 0}}, # Reset allotted on new req? Maybe.
            upsert=True
        )

    @staticmethod
    async def get_requirements(season, clan_tag=None):
        db = await mongo_manager.get_collection("cwl_requirements")
        query = {"season": season}
        if clan_tag: query["clan_tag"] = clan_tag
        cursor = db.find(query)
        return [doc async for doc in cursor]
        
    @staticmethod
    async def increment_allotted_count(season, clan_tag, th, amount=1):
        db = await mongo_manager.get_collection("cwl_requirements")
        await db.update_one(
            {"season": season, "clan_tag": clan_tag, "th_level": th},
            {"$inc": {"count_allotted": amount}}
        )

    @staticmethod
    async def clear_clan_requirements(season, clan_tag):
        db = await mongo_manager.get_collection("cwl_requirements")
        await db.delete_many({"season": season, "clan_tag": clan_tag})

    # --- SHELL CLANS ---
    @staticmethod
    async def add_shell_clan(name, tag):
        db = await mongo_manager.get_collection("cwl_shell_clans")
        await db.update_one(
            {"tag": tag},
            {"$set": {"name": name}},
            upsert=True
        )

    @staticmethod
    async def get_shell_clans():
        db = await mongo_manager.get_collection("cwl_shell_clans")
        cursor = db.find({})
        return [doc async for doc in cursor]

    # --- DISTRIBUTED ALLOCATIONS (Slot Based) ---
    @staticmethod
    async def add_pending_allocation(season, source_clan, target_clan, th, count):
        db = await mongo_manager.get_collection("cwl_pending_allocations")
        await db.update_one(
            {"season": season, "source_clan": source_clan, "target_clan": target_clan, "th_level": th},
            {"$set": {
                "count_assigned": count, 
                "count_filled": 0,
                "status": "pending", # pending -> filled -> approved
                "players": [] # List of tags selected by leader
            }},
            upsert=True
        )

    @staticmethod
    async def get_pending_allocations(season, source_clan=None, target_clan=None):
        db = await mongo_manager.get_collection("cwl_pending_allocations")
        q = {"season": season}
        if source_clan: q["source_clan"] = source_clan
        if target_clan: q["target_clan"] = target_clan
        cursor = db.find(q)
        return [doc async for doc in cursor]

    @staticmethod
    async def update_pending_players(season, source_clan, target_clan, th, player_tags):
        db = await mongo_manager.get_collection("cwl_pending_allocations")
        await db.update_one(
            {"season": season, "source_clan": source_clan, "target_clan": target_clan, "th_level": th},
            {"$set": {
                "players": player_tags,
                "count_filled": len(player_tags),
                "status": "filled"
            }}
        )

    @staticmethod
    async def approve_allocation(season, source_clan, target_clan, th):
        db = await mongo_manager.get_collection("cwl_pending_allocations")
        await db.update_one(
            {"season": season, "source_clan": source_clan, "target_clan": target_clan, "th_level": th},
            {"$set": {"status": "approved"}}
        )

cwl_models = CWLModels()

async def setup(bot):
    pass
