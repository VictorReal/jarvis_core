class Memory:
    def __init__(self):
        self.state = {
            "armor_open": False,
            "systems_online": True
        }

    def get(self, key):
        return self.state.get(key)

    def set(self, key, value):
        self.state[key] = value