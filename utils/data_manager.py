# This file can be used for non-DB data management or helper functions for data processing.
# For now, we will keep it simple and expandable.

import json
import os

class DataManager:
    @staticmethod
    def load_json(filepath):
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r') as f:
            return json.load(f)

    @staticmethod
    def save_json(filepath, data):
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)

data_manager = DataManager()
