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

class CleanVidGUIApp(ctk.CTk): # Inherit from TkinterDnD.Tk instead of ctk.CTk
    """
    Main application class for the CleanVid GUI.
    Sets up the main window and manages the application lifecycle.
    """
    def __init__(self):
        super().__init__()
        self.tkdnd = TkinterDnD.DnDWrapper(self)

        # --- Configuration Management ---
        self.config_manager = ConfigManager()
        self._app_config = self.config_manager.load_config() # Renamed self.config to self._app_config

        # --- Window Setup ---
        self.title(APP_NAME)
        # Set window geometry from config, fallback to default
        self.geometry(self._app_config.get("window_geometry", DEFAULT_CONFIG["window_geometry"])) # Use _app_config
        ctk.set_appearance_mode("System") # Modes: "System" (default), "Dark", "Light"
        ctk.set_default_color_theme("blue") # Themes: "blue" (default), "green", "dark-blue"

        # --- Thread-safe Queue for Subprocess Output ---
        self.output_queue = queue.Queue()

        # --- Main Frame ---
        # Instantiate the main frame, passing necessary objects
        from gui.cleanvidgui_main_frame import CleanVidMainFrame # Import here to avoid circular dependency if needed later
        self.main_frame = CleanVidMainFrame(self, config_manager=self.config_manager, output_queue=self.output_queue)
        self.main_frame.pack(fill="both", expand=True, padx=1, pady=1)
        # Placeholder for now until main_frame is implemented
        # ctk.CTkLabel(self, text="Main GUI content will go here.").pack(pady=20)


        # --- Bindings ---
        # Save configuration when the window is closed
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Start the periodic check for the output queue (even if main_frame isn't fully built yet)
        # This ensures the queue processing is running once the action/output frame is added
        self.after(100, self.process_output_queue)


    def on_closing(self):
        """Handles the window closing event, saves config, and destroys the window."""
        # Gather the current state from all relevant UI components and the live config
        try:
            # Get state from UI frames
            options_state = self.main_frame.advanced_options_frame.get_state()
            input_output_state = self.main_frame.input_output_frame.get_state()

            # Start building the final state dictionary
            current_state_to_save = {
                "window_geometry": self.geometry()
            }

            # Merge states from frames
            current_state_to_save.update(options_state)
            current_state_to_save.update(input_output_state)

            # Explicitly add the 'last used directory' values from the live config,
            # as these are updated directly by the browse/drop methods.
            # Use .get() to avoid errors if a key is somehow missing.
            # Ensure all 'last used directory' keys are included
            for key in ["last_input_dir", "last_output_dir", "last_swears_dir", "last_subs_dir"]:
                 current_state_to_save[key] = self.config_manager.config.get(key, DEFAULT_CONFIG.get(key, str(Path.home())))

            # Save the combined state
            self.config_manager.save_config(current_state_to_save)
            print("Configuration saved.") # Optional: Add confirmation print

        except Exception as e:
            # Log or show an error if saving fails
            print(f"Error saving configuration on closing: {e}")
            # Optionally show a messagebox to the user
            # messagebox.showerror("Config Save Error", f"Could not save settings: {e}")

        # Destroy the window (only call once)
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