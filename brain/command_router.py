from modules.system_module import check_status
from modules.armor_module import open_mask, close_mask
from modules.ai_module import ask_ai

def route(command, memory):
    command = command.lower()
    
    if "status" in command:
        return check_status(memory)

    elif "open armor" in command:
        return open_mask(memory)

    elif "close armor" in command:
        return close_mask(memory)
    else:
        return ask_ai(command)