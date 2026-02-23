def open_mask(memory):
    memory.set("armor_open", True)
    return "Mask opened."

def close_mask(memory):
    memory.set("armor_open", False)
    return "Mask closed."