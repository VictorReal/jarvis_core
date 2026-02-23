def check_status(memory):
    if memory.get("systems_online"):
        return "All systems online."
    return "Systems failure detected."