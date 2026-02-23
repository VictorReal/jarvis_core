from brain.memory import Memory
from brain.command_router import route

class Brain:
    def __init__(self):
        self.memory = Memory()

    def process(self, command: str):
        command = command.lower()
        response = route(command, self.memory)
        return response