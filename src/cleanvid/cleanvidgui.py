import customtkinter as ctk
import tkinter as tk # Keep tkinter import for messagebox or other base features if needed
from tkinterdnd2 import TkinterDnD # Import TkinterDnD
import queue # For thread-safe communication
import sys # For sys.exit
import os # For os.path.join
from pathlib import Path # Import Path

# Import the decentralized modules
from gui.cleanvidgui_config import ConfigManager, DEFAULT_CONFIG
from gui.cleanvidgui_main_frame import CleanVidMainFrame # Will import this once created

APP_NAME = "CleanVid GUI"

class CleanVidGUIApp(TkinterDnD.Tk): # Inherit from TkinterDnD.Tk instead of ctk.CTk
    """
    Main application class for the CleanVid GUI.
    Sets up the main window and manages the application lifecycle.
    """
    def __init__(self):
        super().__init__()

        # --- Configuration Management ---
        self.config_manager = ConfigManager()
        self._app_config = self.config_manager.load_config() # Renamed self.config to self._app_config

        # --- Window Setup ---
        self.title(APP_NAME)
        # Set window geometry from config, fallback to default
        self.geometry(self._app_config.get("window_geometry", DEFAULT_CONFIG["window_geometry"])) # Use _app_config
        ctk.set_appearance_mode("System") # Modes: "System" (default), "Dark", "Light"
        # Set root window background to match customtkinter theme
        # This helps theme the border area when not using ctk.CTk as root
        bg_color_tuple = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
        current_mode = ctk.get_appearance_mode()
        if current_mode == "Dark":
            self.configure(bg=bg_color_tuple[1])
        else: # Light mode
            self.configure(bg=bg_color_tuple[0])
        ctk.set_default_color_theme("blue") # Themes: "blue" (default), "green", "dark-blue"

        # --- Thread-safe Queue for Subprocess Output ---
        self.output_queue = queue.Queue()

        # --- Main Frame ---
        # Instantiate the main frame, passing necessary objects
        from gui.cleanvidgui_main_frame import CleanVidMainFrame # Import here to avoid circular dependency if needed later
        self.main_frame = CleanVidMainFrame(self, config_manager=self.config_manager, output_queue=self.output_queue)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Load Pending Queue ---
        if hasattr(self.main_frame, 'queue_frame') and self.main_frame.queue_frame:
            loaded_queue_items = self._app_config.get("pending_queue", [])
            if loaded_queue_items: # Only repopulate if there's something to load
                self.main_frame.queue_frame.repopulate_from_saved(loaded_queue_items)
                self.main_frame.queue_frame.action_output_frame.update_clean_button_state() # Ensure button reflects loaded queue
            # Clear from live config immediately after attempting to load
            self._app_config["pending_queue"] = []
        else:
            print("Warning: QueueFrame not available on main_frame during init for queue loading.")


        # --- Bindings ---
        # Save configuration when the window is closed
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Start the periodic check for the output queue (even if main_frame isn't fully built yet)
        # This ensures the queue processing is running once the action/output frame is added
        self.after(100, self.process_output_queue)


    def on_closing(self):
        """Handles the window closing event, saves config, and destroys the window."""
        # First, check with ActionOutputFrame if it's okay to close (e.g., process running)
        if hasattr(self.main_frame, 'action_output_frame') and self.main_frame.action_output_frame:
            if not self.main_frame.action_output_frame.on_closing():
                return # Don't proceed with closing if ActionOutputFrame vetoes

        # Gather the current state from all relevant UI components and the live config
        try:
            current_state_to_save = {
                "window_geometry": self.geometry()
            }

            # Get state from UI frames if they exist
            if hasattr(self.main_frame, 'advanced_options_frame') and self.main_frame.advanced_options_frame:
                options_state = self.main_frame.advanced_options_frame.get_state()
                current_state_to_save.update(options_state)

            if hasattr(self.main_frame, 'input_output_frame') and self.main_frame.input_output_frame:
                input_output_state = self.main_frame.input_output_frame.get_state()
                current_state_to_save.update(input_output_state)

            # Save pending queue
            if hasattr(self.main_frame, 'queue_frame') and self.main_frame.queue_frame:
                persistable_queue = self.main_frame.queue_frame.get_persistable_queue()
                current_state_to_save["pending_queue"] = persistable_queue
            else: # Ensure pending_queue is at least an empty list if queue_frame wasn't available
                current_state_to_save["pending_queue"] = []


            # Add last used directory values from the live config manager's config
            # This ensures these are preserved even if other parts fail to load/save
            for key in ["last_input_dir", "last_output_dir", "last_swears_dir", "last_subs_dir"]:
                 current_state_to_save[key] = self.config_manager.config.get(key, DEFAULT_CONFIG.get(key, str(Path.home())))

            # Note: self.config_manager.config might have been self._app_config.
            # Using self.config_manager.config as it's used in load_config for updates.
            # Ensure consistency. The original code used self._app_config for loading and
            # self.config_manager.config for saving the last_dirs.
            # For saving, we should save the most current live state, which is self.config_manager.config.
            # However, other parts of current_state_to_save come from UI.
            # The safest is to update self.config_manager.config with UI states before saving.

            # Update the live config with the current UI states before saving
            self.config_manager.config.update(current_state_to_save)

            # Save the entire updated live config
            self.config_manager.save_config(self.config_manager.config) # Save the live, updated config
            print("Configuration saved.")

        except Exception as e:
            print(f"Error saving configuration on closing: {e}")
            # messagebox.showerror("Config Save Error", f"Could not save settings: {e}") # Consider if this is too intrusive

        self.destroy()


    def process_output_queue(self):
        """
        Periodically checks the output queue for messages from subprocess threads
        and appends them to the output console in the action frame.
        """
        try:
            while True:
                # Get messages from the queue without blocking
                line = self.output_queue.get_nowait()
                # Append the line to the output console in the action frame
                if hasattr(self, 'main_frame') and hasattr(self.main_frame, 'action_output_frame'):
                    self.main_frame.action_output_frame.log_output(line)
                else:
                    # Fallback print if action frame is not available
                    print(f"GUI Output: {line}", end='')
        except queue.Empty:
            pass # No items in the queue
        except Exception as e:
            # Log errors related to processing the queue itself
            print(f"Error processing output queue: {e}")
        finally:
            # Reschedule the check after a short delay
            self.after(100, self.process_output_queue)


# --- Main Execution ---
if __name__ == "__main__":
    # Add the src directory to the Python path so modules can be imported
    script_dir = Path(__file__).parent.resolve()
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    app = CleanVidGUIApp()
    app.mainloop()