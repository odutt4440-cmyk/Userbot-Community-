import importlib
import logging

log = logging.getLogger(__name__)

# --- MODULES MASTER MAP ---
MODULE_MAP = {
    # Games Category
    "wordly": "modules.games.wordly.wordly",
    "wordseek": "modules.games.wordseek.wordseek",
    "wordchain": "modules.games.wordchain.wordchain",
    "octopus": "modules.games.octopus.octopus",
    "wordle_pro": "modules.games.wordle_pro.wordle_pro",
    #"wordgrid": "modules.games.wordgrid.wordgrid",
    # Fun Category
    "clone": "modules.fun.clone",
    "afk": "modules.fun.afk",
    "stickers": "modules.fun.stickers",
    "reaction": "modules.fun.reaction",
    "extra_fun": "modules.fun.extra",
    "raid": "modules.fun.raid",
    "auto_greet": "modules.fun.auto_greet",
    "vc_stream": "modules.fun.vc_stream",
    # Management Category
    "tagger": "modules.management.tagger",
    "stealth": "modules.management.stealth",
    "approver": "modules.management.approver",
    "info_tools": "modules.management.info_tools",
    "group_tools": "modules.management.group_tools"
}

async def load_all_modules(client, target_module=None):
    """
    SaaS Optimized Loader:
    - Purges previous handlers (One Unit at a Time).
    - Supports Category Loading for Empire Users.
    - Keeps Essentials online.
    """
    # 🔥 STEP 1: PURGE OLD HANDLERS (Hard Reset)
    # Jaise hi naya module/folder load hoga, pichla wala 100% stop ho jayega
    client._event_builders.clear()
    log.info("🧹 Handlers Purged: Starting fresh load.")

    to_load = []
    target = str(target_module).strip().lower()

    # Prefix Cleaning (mod_fun_pack -> fun_pack)
    for prefix in ["activate_", "mod_", "force_start_", "start_ub_", "stop_"]:
        target = target.replace(prefix, "")

    # 🔥 STEP 2: CATEGORY SELECTION (Empire Logic)
    # Check if user wants a whole folder
    is_category = False
    if "pack" in target or target in ["games", "fun", "management"]:
        category_name = target.replace("_pack", "")
        # Find all modules that belong to this folder
        for key, path in MODULE_MAP.items():
            if f"modules.{category_name}" in path:
                to_load.append(path)
        
        if to_load:
            is_category = True
            log.info(f"👑 Empire Category Loaded: [{category_name.upper()}]")

    # 🔥 STEP 3: SINGLE MODULE SELECTION (Standard Logic)
    if not is_category:
        main_path = MODULE_MAP.get(target)
        if main_path:
            to_load.append(main_path)
            log.info(f"🎯 Standard Module Loaded: [{target}]")
        else:
            log.error(f"❌ Module/Category '{target}' not found in Map!")

    # 🔥 STEP 4: LOAD ESSENTIALS (Hamesha Online)
    # Ye tools hamesha load honge taaki userbot basic commands (.id, .info) de sake
    to_load.append(MODULE_MAP["info_tools"])
    to_load.append(MODULE_MAP["group_tools"])

    # 🔥 STEP 5: REGISTRATION
    # set(to_load) ensures no duplicates
    for module_path in set(to_load):
        try:
            module = importlib.import_module(module_path)
            importlib.reload(module) # Refresh logic
            if hasattr(module, 'register'):
                module.register(client)
                log.info(f"✅ Active: {module_path}")
        except Exception as e:
            log.error(f"❌ Failed to load {module_path}: {e}")
