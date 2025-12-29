import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
from pathlib import Path

from .cleanvidgui_tooltip import Tooltip
from .cleanvidgui_config import DEFAULT_CONFIG # Import DEFAULT_CONFIG for initial values

class InputOutputFrame(ctk.CTkFrame):
    """
    Frame for handling input video, subtitle, and output path selection.
    Includes browse buttons, drag-and-drop support, and output path logic.
    """
    def __init__(self, master, config_manager, options_frame=None, action_output_frame=None):
        super().__init__(master)
        self.config_manager = config_manager
        self.options_frame = options_frame # Reference to the options frame for live settings
        self.action_output_frame = action_output_frame # Reference to the action/output frame for logging/updates

        # Configure grid layout
        self.grid_columnconfigure(1, weight=1) # Allow the entry fields to expand

        # --- Variables ---
        self.input_video_var = ctk.StringVar()
        self.input_subs_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar()
        # Load last output directory from config
        self.output_dir_var.set(self.config_manager.config.get("last_output_dir", DEFAULT_CONFIG["last_output_dir"]))
        self.output_filename_var = ctk.StringVar()
        # Initialize checkbox state from config, default to True if not in config
        self.save_to_same_dir_var = ctk.BooleanVar(value=self.config_manager.config.get("save_to_same_dir", True))

        # --- UI Elements ---
        # Video Input
        ctk.CTkLabel(self, text="Source Video:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.video_entry = ctk.CTkEntry(self, textvariable=self.input_video_var, state="readonly")
        self.video_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        browse_video_btn = ctk.CTkButton(self, text="Browse...", command=self.browse_video)
        browse_video_btn.grid(row=0, column=2, padx=5, pady=5)
        Tooltip(browse_video_btn, "Select the video file to clean.")
        Tooltip(self.video_entry, "Path to the source video file.") # Tooltip for entry

        # Subtitle Input
        ctk.CTkLabel(self, text="Subtitles (.srt):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.subs_entry = ctk.CTkEntry(self, textvariable=self.input_subs_var, state="readonly")
        self.subs_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        browse_subs_btn = ctk.CTkButton(self, text="Browse...", command=self.browse_subs)
        browse_subs_btn.grid(row=1, column=2, padx=5, pady=5)
        Tooltip(browse_subs_btn, "Select the subtitle file.\nIf empty, cleanvid will attempt to use\nembedded subtitles or download them.")
        Tooltip(self.subs_entry, "Path to the .srt subtitle file (optional).") # Tooltip for entry

        # Output Options Checkbox
        self.output_checkbox = ctk.CTkCheckBox(self, text="Save output to same directory with `_clean` suffix", variable=self.save_to_same_dir_var)
        self.output_checkbox.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        Tooltip(self.output_checkbox, "Check to automatically save the cleaned video in the same folder\nas the input, adding '_clean' to the filename.\nUncheck to specify a different output location and filename.")

        # Conditional Output Path Frame
        self.output_path_frame = ctk.CTkFrame(self)
        # Grid placement is handled by update_output_path_frame
        self.output_path_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.output_path_frame, text="Output Directory:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.output_dir_entry = ctk.CTkEntry(self.output_path_frame, textvariable=self.output_dir_var, state="readonly")
        self.output_dir_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(self.output_path_frame, text="Browse...", command=self.browse_output_dir).grid(row=0, column=2, padx=5, pady=5)
        Tooltip(self.output_dir_entry, "Directory where the cleaned video will be saved.") # Tooltip for entry

        ctk.CTkLabel(self.output_path_frame, text="Output Filename:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.output_filename_entry = ctk.CTkEntry(self.output_path_frame, textvariable=self.output_filename_var)
        self.output_filename_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        Tooltip(self.output_filename_entry, "Filename for the cleaned video.") # Tooltip for entry


        # --- Bindings ---
        # Trace the checkbox variable to update the output path frame visibility
        self.save_to_same_dir_var.trace_add("write", self.update_output_path_frame)

        # --- Drag and Drop Bindings ---
        # Bind drag and drop events to the entry widgets
        self.video_entry.bind("<ButtonPress-1>", lambda e: self.start_drag(e, "video"))
        self.video_entry.bind("<B1-Motion>", lambda e: self.do_drag(e, "video"))
        self.video_entry.bind("<ButtonRelease-1>", lambda e: self.stop_drag(e, "video"))

        self.subs_entry.bind("<ButtonPress-1>", lambda e: self.start_drag(e, "subs"))
        self.subs_entry.bind("<B1-Motion>", lambda e: self.do_drag(e, "subs"))
        self.subs_entry.bind("<ButtonRelease-1>", lambda e: self.stop_drag(e, "subs"))

        # Bind drop events to the entry widgets and the frame itself
        # Register drop targets and bind using tkinterdnd2
        self.video_entry.drop_target_register('DND_Files')
        self.video_entry.dnd_bind('<<Drop>>', lambda e: self.drop(e, "video"))

        self.subs_entry.drop_target_register('DND_Files')
        self.subs_entry.dnd_bind('<<Drop>>', lambda e: self.drop(e, "subs"))

        self.drop_target_register('DND_Files') # Register the frame itself
        self.dnd_bind('<<Drop>>', lambda e: self.drop(e, "frame")) # Allow dropping anywhere on the frame

        # --- Initial State ---
        self.update_output_path_frame() # Set initial visibility of output path frame


    def update_output_path_frame(self, *args):
        """Shows or hides the custom output path frame based on the checkbox state."""
        if self.save_to_same_dir_var.get():
            self.output_path_frame.grid_forget() # Hide the frame
        else:
            # Show the frame below the checkbox
            self.output_path_frame.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
            # Attempt to auto-set filename if input video exists and output directory is set
            self.auto_set_output_filename()

    def get_initial_dir(self, dir_type):
        """Gets the initial directory for file dialogs based on config and live settings."""
        # Prioritize live default_media_dir from OptionsFrame if available
        default_dir = ""
        if self.options_frame and hasattr(self.options_frame, 'default_media_dir_var'):
            default_dir = self.options_frame.default_media_dir_var.get()

        # Use default media dir if set and valid for relevant types
        if default_dir and os.path.isdir(default_dir) and dir_type in ["video", "subs", "output"]:
             return default_dir
        # Fallback to last used directory for that specific type
        last_dir_key = f"last_{dir_type}_dir"
        # Use .get() with a default from DEFAULT_CONFIG to handle missing keys gracefully
        last_dir = self.config_manager.config.get(last_dir_key, DEFAULT_CONFIG.get(last_dir_key, str(Path.home())))
        # Final fallback to home if last_dir is invalid
        return last_dir if os.path.isdir(last_dir) else str(Path.home())

    def update_last_dir(self, dir_type, selected_path):
        """Updates the last used directory in the config for the session."""
        if selected_path:
            # Get directory from file path or use directory path directly
            directory = os.path.dirname(selected_path) if os.path.isfile(selected_path) else selected_path
            if os.path.isdir(directory):
                last_dir_key = f"last_{dir_type}_dir"
                self.config_manager.config[last_dir_key] = directory # Update the live config dict

    def browse_video(self):
        """Opens a file dialog to select the input video file."""
        initial_dir = self.get_initial_dir("video")
        filepath = filedialog.askopenfilename(
            title="Select Video File",
            initialdir=initial_dir,
            filetypes=(("Video Files", "*.mp4 *.mkv *.avi *.mov *.wmv"), ("All Files", "*.*"))
        )
        if filepath:
            self.input_video_var.set(filepath)
            self.update_last_dir("video", filepath)
            # Auto-populate output filename if custom path is used
            if not self.save_to_same_dir_var.get():
                 self.auto_set_output_filename()
            self.log_to_console(f"Selected video: {filepath}\n")


    def browse_subs(self):
        """Opens a file dialog to select the input subtitle file."""
        initial_dir = self.get_initial_dir("subs")
        filepath = filedialog.askopenfilename(
            title="Select Subtitle File",
            initialdir=initial_dir,
            filetypes=(("SRT Subtitles", "*.srt"), ("All Files", "*.*"))
        )
        if filepath:
            self.input_subs_var.set(filepath)
            self.update_last_dir("subs", filepath)
            self.log_to_console(f"Selected subtitles: {filepath}\n")


    def browse_output_dir(self):
        """Opens a directory dialog to select the output directory."""
        initial_dir = self.get_initial_dir("output")
        dirpath = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=initial_dir
        )
        if dirpath:
            self.output_dir_var.set(dirpath)
            self.update_last_dir("output", dirpath)
            # Auto-populate output filename if not already set
            self.auto_set_output_filename() # Call even if filename exists, might base on new dir
            self.log_to_console(f"Selected output directory: {dirpath}\n")


    def browse_subs_output(self):
        """Opens a save file dialog for the clean subtitle output file."""
        initial_dir = self.get_initial_dir("output") # Use output dir logic
        # Suggest filename based on input video if possible
        suggested_name = ""
        if input_video := self.input_video_var.get():
            suggested_name = f"{Path(input_video).stem}_clean.srt"

        filepath = filedialog.asksaveasfilename(
            title="Save Clean Subtitle File As",
            initialdir=initial_dir,
            initialfile=suggested_name,
            defaultextension=".srt",
            filetypes=(("SRT Subtitles", "*.srt"), ("All Files", "*.*"))
        )
        if filepath:
            self.subs_output_var.set(filepath) # Assuming subs_output_var is defined elsewhere (e.g., OptionsFrame)
            self.update_last_dir("output", filepath) # Update last output dir
            self.log_to_console(f"Selected clean subtitle output: {filepath}\n")


    def browse_plex_json(self):
        """Opens a save file dialog for the PlexAutoSkip JSON file."""
        initial_dir = self.get_initial_dir("output") # Use output dir logic
        # Suggest filename based on input video if possible
        suggested_name = ""
        if input_video := self.input_video_var.get():
            suggested_name = f"{Path(input_video).stem}_PlexAutoSkip.json"

        filepath = filedialog.asksaveasfilename(
            title="Save PlexAutoSkip JSON As",
            initialdir=initial_dir,
            initialfile=suggested_name,
            defaultextension=".json",
            filetypes=(("JSON Files", "*.json"), ("All Files", "*.*"))
        )
        if filepath:
            self.plex_json_var.set(filepath) # Assuming plex_json_var is defined elsewhere (e.g., OptionsFrame)
            self.update_last_dir("output", filepath) # Update last output dir
            self.log_to_console(f"Selected PlexAutoSkip JSON output: {filepath}\n")


    def auto_set_output_filename(self):
        """Sets the default output filename based on input video and output directory."""
        input_video = self.input_video_var.get()
        output_dir = self.output_dir_var.get()
        # Only set if custom output is chosen, input video is selected, and output directory is set
        if input_video and output_dir and not self.save_to_same_dir_var.get():
            in_path = Path(input_video)
            out_filename = f"{in_path.stem}_clean{in_path.suffix}"
            # Only set the filename if the current filename is empty or matches the default pattern
            # This prevents overwriting a filename the user manually entered
            current_filename = self.output_filename_var.get()
            if not current_filename or current_filename == f"{Path(current_filename).stem}{Path(current_filename).suffix}":
                 self.output_filename_var.set(out_filename)


    # --- Drag and Drop Implementation ---
    # Basic implementation, may need refinement for different OS or complex scenarios
    def start_drag(self, event, field_type):
        """Starts the drag operation."""
        # Store the starting position and the type of field being dragged from
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._drag_field_type = field_type

    def do_drag(self, event, field_type):
        """Handles the drag motion."""
        # Check if the drag has moved significantly from the start point
        if abs(event.x - self._drag_start_x) > 5 or abs(event.y - self._drag_start_y) > 5:
            # This is where you might initiate a native drag-and-drop operation
            # For simplicity here, we'll just rely on the <Drop> binding on the target
            pass # No action needed during drag motion for this basic implementation

    def stop_drag(self, event, field_type):
        """Cleans up after the drag operation."""
        self._drag_start_x = None
        self._drag_start_y = None
        self._drag_field_type = None

    def drop(self, event, target_type):
        """Handles the drop event using tkinterdnd2."""
        # tkinterdnd2 passes the dropped file paths as a stringified Tcl list
        # Use tk.splitlist to correctly parse it, handling spaces in paths
        try:
            # Ensure event.data is treated as a string before splitting
            data_str = str(event.data)
            paths = self.tk.splitlist(data_str)
        except (tk.TclError, AttributeError) as e:
            # Handle potential errors if event.data is not a valid Tcl list or not present
            self.log_to_console(f"Error parsing dropped data ('{event.data}'): {e}\n")
            messagebox.showwarning("Drop Error", "Could not parse dropped file information.")
            return

        if not paths:
            self.log_to_console("Drop event received with no paths.\n")
            return

        # Take the first dropped file path
        filepath = paths[0]
        self.log_to_console(f"Attempting to process dropped file: {filepath}\n") # Log the path being processed

        # Ensure the path uses correct OS separators (important on Windows)
        filepath = os.path.normpath(filepath)

        if target_type == "video":
            if os.path.isfile(filepath):
                self.input_video_var.set(filepath)
                self.update_last_dir("video", filepath)
                if not self.save_to_same_dir_var.get():
                     self.auto_set_output_filename()
                self.log_to_console(f"Dropped video: {filepath}\n")
            else:
                 messagebox.showwarning("Invalid Drop", "Please drop a valid video file.")
                 self.log_to_console(f"Invalid drop (not a file): {filepath}\n")

        elif target_type == "subs":
            if os.path.isfile(filepath) and filepath.lower().endswith(".srt"):
                self.input_subs_var.set(filepath)
                self.update_last_dir("subs", filepath)
                self.log_to_console(f"Dropped subtitles: {filepath}\n")
            else:
                 messagebox.showwarning("Invalid Drop", "Please drop a valid .srt subtitle file.")
                 self.log_to_console(f"Invalid drop (not a .srt file): {filepath}\n")

        elif target_type == "frame":
             # If dropped on the frame, try to guess based on extension
             if os.path.isfile(filepath):
                 if filepath.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".wmv")):
                     self.input_video_var.set(filepath)
                     self.update_last_dir("video", filepath)
                     if not self.save_to_same_dir_var.get():
                          self.auto_set_output_filename()
                     self.log_to_console(f"Dropped video (on frame): {filepath}\n")
                 elif filepath.lower().endswith(".srt"):
                     self.input_subs_var.set(filepath)
                     self.update_last_dir("subs", filepath)
                     self.log_to_console(f"Dropped subtitles (on frame): {filepath}\n")
                 else:
                     messagebox.showwarning("Invalid Drop", "Unsupported file type dropped.")
                     self.log_to_console(f"Invalid drop (unsupported type): {filepath}\n")
             else:
                 messagebox.showwarning("Invalid Drop", "Please drop a valid file.")
                 self.log_to_console(f"Invalid drop (not a file): {filepath}\n")


    def get_state(self):
        """Returns a dictionary containing the current state of input/output variables."""
        return {
            "input_video": self.input_video_var.get(),
            "input_subs": self.input_subs_var.get(),
            "save_to_same_dir": self.save_to_same_dir_var.get(),
            "output_dir": self.output_dir_var.get(),
            "output_filename": self.output_filename_var.get(),
            # last_dirs are updated directly in config_manager.config by browse methods
        }

    def log_to_console(self, message):
        """Logs a message to the output console via the action_output_frame."""
        if self.action_output_frame:
            self.action_output_frame.log_output(message)
        else:
            print(f"LOG (InputOutputFrame): {message}", end='') # Fallback print


# Example Usage (for testing purposes, requires other modules)
if __name__ == "__main__":
    # This example requires the other gui modules to exist, even if empty
    # Create dummy files if they don't exist for testing
    import os
    from pathlib import Path
    dummy_files = [
        "cleanvidgui_config.py",
        "cleanvidgui_tooltip.py",
        "cleanvidgui_action_output.py", # Need a dummy for the reference
    ]
    gui_dir = Path(__file__).parent
    for fname in dummy_files:
        if not (gui_dir / fname).exists():
            with open(gui_dir / fname, 'w') as f:
                f.write("# Dummy file for testing\n")
                f.write("import customtkinter as ctk\n")
                if "config" in fname:
                     f.write("DEFAULT_CONFIG = {}\n")
                     f.write("class ConfigManager: def load_config(self): return {}; def save_config(self, c): pass\n")
                elif "tooltip" in fname:
                     f.write("class Tooltip: def __init__(self, w, t): pass\n")
                elif "action_output" in fname:
                     f.write("class ActionOutputFrame(ctk.CTkFrame): def __init__(self, master, **kwargs): super().__init__(master, **kwargs); ctk.CTkLabel(self, text='ActionOutputFrame Placeholder').pack()\n")
                     f.write("    def log_output(self, msg): print(f'DUMMY LOG: {msg}', end='')\n")


    # Now import the dummy/real modules
    from .cleanvidgui_config import ConfigManager
    from .cleanvidgui_action_output import ActionOutputFrame # Import dummy/real

    root = ctk.CTk()
    root.title("InputOutputFrame Demo")
    root.geometry("800x300") # Adjust size for this frame

    config_manager = ConfigManager()
    # Create a dummy action_output_frame for the reference
    dummy_action_output = ActionOutputFrame(root) # Master doesn't matter much for dummy

    input_output_frame = InputOutputFrame(root, config_manager=config_manager, action_output_frame=dummy_action_output)
    input_output_frame.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()