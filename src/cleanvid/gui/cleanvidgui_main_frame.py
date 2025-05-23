import customtkinter as ctk
import tkinter as tk # Needed for sticky constants like "nsew"

# Import the frame modules (will be implemented next)
# from .cleanvidgui_input_output import InputOutputFrame
# from .cleanvidgui_options import OptionsFrame
# from .cleanvidgui_action_output import ActionOutputFrame

class CleanVidMainFrame(ctk.CTkFrame):
    """
    Main frame for the CleanVid GUI.
    Holds and arranges the Input/Output, Options, and Action/Output frames.
    """
    def __init__(self, master, config_manager, output_queue):
        super().__init__(master)
        self.config_manager = config_manager
        self.output_queue = output_queue

        # Configure grid layout for the main frame
        self.grid_columnconfigure(0, weight=1)
        # Rows for Input/Output, Options, and Action/Output frames
        self.grid_rowconfigure(0, weight=0) # Input/Output frame (doesn't expand vertically)
        self.grid_rowconfigure(1, weight=0) # Core Options frame (doesn't expand vertically)
        self.grid_rowconfigure(2, weight=0) # Advanced Options (Tabs) frame (doesn't expand vertically)
        self.grid_rowconfigure(3, weight=1) # Action/Output frame (expands vertically)


        # --- Instantiate Sub-Frames ---
        # Import here to avoid potential circular dependencies during development
        from .cleanvidgui_input_output import InputOutputFrame
        from .cleanvidgui_options import OptionsFrame
        from .cleanvidgui_action_output import ActionOutputFrame

        # Create the frames
        # Create OptionsFrame first so it can be passed to InputOutputFrame
        self.advanced_options_frame = OptionsFrame(self, config_manager=self.config_manager) # OptionsFrame will handle tabs
        self.input_output_frame = InputOutputFrame(self, config_manager=self.config_manager, options_frame=self.advanced_options_frame)
        # self.core_options_frame = ctk.CTkFrame(self) # Placeholder removed
        self.action_output_frame = ActionOutputFrame(self, config_manager=self.config_manager, output_queue=self.output_queue)

        # Pass references for inter-frame communication
        # Action/Output frame needs access to input/option variables
        self.action_output_frame.input_output_frame = self.input_output_frame
        self.action_output_frame.options_frame = self.advanced_options_frame # Pass the OptionsFrame instance

        # Options frame might need to trigger actions in Action/Output frame (e.g., List Streams)
        self.advanced_options_frame.action_output_frame = self.action_output_frame
        # Input/Output frame might need to trigger auto-filename update or log
        self.input_output_frame.action_output_frame = self.action_output_frame


        # --- Place Sub-Frames in Grid ---
        self.input_output_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        # Place core options directly in main frame for now, or create a dedicated frame if needed - Removed placeholder logic

        # Revised grid layout:
        # Row 0: Input/Output Frame
        # Row 1: Options Frame (containing core and advanced tabs)
        # Row 2: Action/Output Frame

        self.grid_rowconfigure(0, weight=0) # Input/Output
        self.grid_rowconfigure(1, weight=0) # Options (Tabs)
        self.grid_rowconfigure(2, weight=1) # Action/Output (expands)


        self.input_output_frame.grid(row=0, column=0, padx=1, pady=(1, 0), sticky="ew")
        self.advanced_options_frame.grid(row=1, column=0, padx=1, pady=0, sticky="ew") # Use the actual OptionsFrame instance
        self.action_output_frame.grid(row=2, column=0, padx=1, pady=(0, 1), sticky="nsew") # Action/Output expands


# Example Usage (for testing purposes, requires other modules)
if __name__ == "__main__":
    # This example requires the other gui modules to exist, even if empty
    # Create dummy files if they don't exist for testing the main frame layout
    import os
    from pathlib import Path
    dummy_files = [
        "cleanvidgui_input_output.py",
        "cleanvidgui_options.py",
        "cleanvidgui_action_output.py",
        "cleanvidgui_config.py",
        "cleanvidgui_tooltip.py",
    ]
    gui_dir = Path(__file__).parent
    for fname in dummy_files:
        if not (gui_dir / fname).exists():
            with open(gui_dir / fname, 'w') as f:
                f.write("# Dummy file for testing\n")
                f.write("import customtkinter as ctk\n")
                f.write("class DummyFrame(ctk.CTkFrame):\n")
                f.write("    def __init__(self, master, **kwargs):\n")
                f.write("        super().__init__(master, **kwargs)\n")
                f.write("        ctk.CTkLabel(self, text=f'{self.__class__.__name__} Placeholder').pack()\n")
                f.write("class InputOutputFrame(DummyFrame): pass\n")
                f.write("class OptionsFrame(DummyFrame): pass\n")
                f.write("class ActionOutputFrame(DummyFrame): pass\n")
                f.write("class ConfigManager: def load_config(self): return {}; def save_config(self, c): pass\n")
                f.write("class Tooltip: def __init__(self, w, t): pass\n")
                f.write("import queue; queue.Queue = lambda: [] # Mock queue\n") # Mock queue for dummy frames

    # Now import the dummy/real modules
    from .cleanvidgui_config import ConfigManager
    import queue # Use real queue for the app

    root = ctk.CTk()
    root.title("Main Frame Demo")
    root.geometry("800x750") # Use a size similar to the planned default

    config_manager = ConfigManager()
    output_queue = queue.Queue()

    main_frame = CleanVidMainFrame(root, config_manager=config_manager, output_queue=output_queue)
    main_frame.pack(fill="both", expand=True, padx=10, pady=10) # Use pack for the main frame in the root window

    root.mainloop()