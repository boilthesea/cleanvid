import json
import os
import sys
from pathlib import Path

# --- Constants ---
CONFIG_FILE_NAME = "cleanvid_gui_config.json"
DEFAULT_CONFIG = {
    "win_mode": sys.platform.startswith("win"), # Default based on OS
    "alass_mode": False,
    "swears_file": "", # Default swears file relative to gui dir
    "default_media_dir": "",
    "last_input_dir": str(Path.home()), # Start at home dir initially
    "last_output_dir": str(Path.home()),
    "last_swears_dir": os.path.join(os.path.dirname(__file__), '..'), # Default swears dir relative to gui dir
    "last_subs_dir": str(Path.home()),
    "window_geometry": "1250x750", # Default window size - Increased width
    "chapter_markers": False,
    "fast_index": False, # Add this
    "pending_queue": [], # For persisting the queue items
}

class ConfigManager:
    """
    Handles loading and saving application settings to a JSON file.
    """
    def __init__(self):
        # Determine config file path relative to the script location
        script_dir = Path(__file__).parent
        self.config_path = script_dir / CONFIG_FILE_NAME
        self.config = {} # Initialize config dictionary

    def load_config(self):
        """Loads configuration from the JSON file, merging with defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Start with defaults and update with loaded values
                    self.config = DEFAULT_CONFIG.copy()
                    self.config.update(loaded_config)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config file '{self.config_path}': {e}. Using defaults.")
                self.config = DEFAULT_CONFIG.copy()
        else:
            print(f"Config file not found at '{self.config_path}'. Using defaults.")
            self.config = DEFAULT_CONFIG.copy()

        # Ensure all default keys are present in case the loaded file was incomplete
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in self.config:
                self.config[key] = default_value

        return self.config

    def save_config(self, current_config_state):
        """Saves the current configuration state to the JSON file."""
        # Use the provided state, don't rely on self.config directly
        # This allows the main app to manage the live state
        try:
            # Ensure the directory exists before writing
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(current_config_state, f, indent=4)
        except IOError as e:
            print(f"Error saving config file '{self.config_path}': {e}")

# Example Usage (for testing purposes, can be removed later)
if __name__ == "__main__":
    config_manager = ConfigManager()
    print("Loading config...")
    config = config_manager.load_config()
    print("Loaded config:", config)

    # Modify a setting
    config['alass_mode'] = True
    config['default_media_dir'] = str(Path.home() / "Videos")

    print("\nSaving modified config...")
    config_manager.save_config(config)
    print("Config saved.")

    # Load again to verify
    print("\nLoading config again...")
    new_config_manager = ConfigManager()
    reloaded_config = new_config_manager.load_config()
    print("Reloaded config:", reloaded_config)