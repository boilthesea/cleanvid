import customtkinter as ctk
from .cleanvidgui_tooltip import Tooltip
import os
from tkinter import filedialog
import copy # For deepcopy
import tkinter.messagebox as messagebox # Added for help dialog
import tkinterdnd2 # For drag-and-drop
import re # For parsing DND strings

class QueueFrame(ctk.CTkFrame):
    def __init__(self, master, config_manager, options_frame, action_output_frame=None, width=200):
        super().__init__(master, width=width)
        self.config_manager = config_manager
        self.options_frame = options_frame
        self.action_output_frame = action_output_frame
        self.queue_items = []
        self.item_id_counter = 0

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.grid(row=0, column=0, padx=5, pady=(5,0), sticky="ew")

        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0)

        self.add_button = ctk.CTkButton(self.button_frame, text="+", width=100, command=self.add_files_dialog)
        self.add_button.grid(row=0, column=0, padx=(5,2), pady=5, sticky="w")

        self.help_button = ctk.CTkButton(self.button_frame, text="?", width=30, command=self.show_queue_help)
        self.help_button.grid(row=0, column=1, padx=2, pady=5, sticky="e")

        self.clear_button = ctk.CTkButton(self.button_frame, text="x", width=30, fg_color="red", command=self.clear_queue)
        self.clear_button.grid(row=0, column=2, padx=(2,5), pady=5, sticky="e")

        Tooltip(self.add_button, "Add files to queue")
        Tooltip(self.clear_button, "Clear all files from queue")
        Tooltip(self.help_button, "Show help for the queue")

        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Queue")
        self.scrollable_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        # Register scrollable_frame as a drop target
        self.scrollable_frame.drop_target_register(tkinterdnd2.DND_FILES)
        self.scrollable_frame.dnd_bind('<<Drop>>', self.handle_drop)

        self.update_queue_display() # Initial display

    def _parse_dnd_data(self, data_string):
        """Parses the string data from a DND event into a list of file paths."""
        paths = []
        current_path = ""
        in_brace = False
        # Iterate through the string, including a dummy space at the end to finalize the last path
        for char in data_string + " ":
            if char == '{':
                if not in_brace: # Start of a new braced path
                    if current_path.strip(): # Path before brace (shouldn't usually happen if well-formed)
                        paths.append(current_path.strip())
                    current_path = ""
                    in_brace = True
                else: # Nested brace, treat as part of the path
                    current_path += char
            elif char == '}':
                if in_brace:
                    in_brace = False
                    if current_path.strip():
                        paths.append(current_path.strip())
                    current_path = ""
                else: # Unmatched closing brace, treat as part of path
                    current_path += char
            elif char == ' ' and not in_brace: # Space delimiter, only if not inside braces
                if current_path.strip():
                    paths.append(current_path.strip())
                current_path = ""
            else:
                current_path += char

        # Clean up any empty strings that might have resulted
        return [p for p in paths if p]

    def handle_drop(self, event):
        """Handles files dropped onto the scrollable_frame."""
        raw_paths_data = event.data
        # print(f"Raw DND data: '{raw_paths_data}'") # For debugging DND string format

        if isinstance(raw_paths_data, str):
            file_paths = self._parse_dnd_data(raw_paths_data)
        else:
            # Fallback if data is not a string (e.g. already a list/tuple from a wrapper)
            try:
                file_paths = list(raw_paths_data)
            except TypeError:
                file_paths = []
                print("Warning: Could not interpret DND data format.")

        # print(f"Parsed DND paths: {file_paths}") # For debugging parsed paths

        valid_files = [p for p in file_paths if os.path.isfile(p)]

        if not valid_files:
            print(f"No valid files found in drop: {file_paths}")
            return

        if valid_files:
            current_settings_snapshot = copy.deepcopy(self.options_frame.get_state())
            added_count = 0
            for file_path in valid_files:
                # Basic video file extension check (can be expanded)
                if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')):
                    queue_item = {
                        "id": f"item_{self.item_id_counter}",
                        "file_path": file_path,
                        "settings": copy.deepcopy(current_settings_snapshot)
                    }
                    self.queue_items.append(queue_item)
                    self.item_id_counter += 1
                    added_count +=1
                else:
                    print(f"Skipped non-video file: {file_path}")

            if added_count > 0:
                self.update_queue_display()
                if self.action_output_frame:
                    self.action_output_frame.update_clean_button_state()
            else:
                messagebox.showwarning("No Video Files", "No valid video files were found in the dropped items.")


    def get_item_count(self):
        return len(self.queue_items)

    def peek_next_item(self):
        if self.queue_items:
            return self.queue_items[0]
        return None

    def get_next_item_for_processing(self):
        if self.queue_items:
            item = self.queue_items.pop(0)
            self.update_queue_display()
            return item
        return None

    def update_item_status(self, item_id, status_message):
        print(f"Queue Item {item_id} status: {status_message}")
        if self.action_output_frame:
            self.action_output_frame.log_output(f"Item {item_id}: {status_message}\n", main_log=False)

    def add_files_dialog(self):
        file_types = [
            ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"), # Added more common types
            ("All files", "*.*")
        ]
        selected_files = filedialog.askopenfilenames(
            title="Select video files to add to queue",
            filetypes=file_types
        )

        if selected_files:
            current_settings_snapshot = self.options_frame.get_state()
            for file_path in selected_files:
                queue_item = {
                    "id": f"item_{self.item_id_counter}",
                    "file_path": file_path,
                    "settings": copy.deepcopy(current_settings_snapshot)
                }
                self.queue_items.append(queue_item)
                self.item_id_counter += 1
            self.update_queue_display()

    def remove_item(self, item_id_to_remove):
        self.queue_items = [item for item in self.queue_items if item['id'] != item_id_to_remove]
        self.update_queue_display()

    def clear_queue(self):
        self.queue_items = []
        self.update_queue_display()

    def _format_settings_for_tooltip(self, settings_dict):
        if not settings_dict:
            return "No specific settings applied."
        lines = []
        for key, value in sorted(settings_dict.items()):
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
        return "\n".join(lines)

    def update_queue_display(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if not self.queue_items:
            self.empty_queue_label = ctk.CTkLabel(
                self.scrollable_frame,
                text="Drop video files here, or click '+' to add to the queue.\n" # Updated text
                     "Locked settings from the Options panel will apply to each batch.\n"
                     "Use '?' for more details.",
                wraplength=380,
                justify="center"
            )
            self.empty_queue_label.pack(padx=10, pady=20, expand=True, fill="both")
        else:
            for item_data in self.queue_items:
                item_frame = ctk.CTkFrame(self.scrollable_frame)
                item_frame.pack(fill='x', pady=2, padx=2)

                item_frame.grid_columnconfigure(0, weight=1)
                item_frame.grid_columnconfigure(1, weight=0)

                base_name = os.path.basename(item_data['file_path'])
                label = ctk.CTkLabel(item_frame, text=base_name, anchor="w")
                label.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

                item_id = item_data["id"]
                delete_button = ctk.CTkButton(
                    item_frame, text="🗑", width=30, fg_color="transparent",
                    hover_color="gray25", command=lambda id_val=item_id: self.remove_item(id_val)
                )
                delete_button.grid(row=0, column=1, padx=5, pady=5, sticky="e")

                tooltip_text = self._format_settings_for_tooltip(item_data['settings'])
                Tooltip(item_frame, tooltip_text)
                Tooltip(label, tooltip_text)
                Tooltip(delete_button, f"Remove {base_name} from queue")

        self.scrollable_frame.update_idletasks()

        if self.action_output_frame:
            self.action_output_frame.update_clean_button_state()

    def show_queue_help(self):
        title = "Cleanvid Queue Help"
        help_message = """Cleanvid Queue Functionality:

- Adding Files: Click the '+' button or drag and drop video files onto the queue panel to add them.
- Settings Per Batch: The settings currently selected in the 'Options' panel are locked in for each file (or batch of files) when you add them to the queue. To use different settings for other files, change the options first, then add the new files.
- Removing Files: Click the trash can icon (🗑️) next to a file to remove it individually. Click the 'x' button (top right of queue panel) to clear the entire queue.
- Running the Queue: Click 'Run Queue' in the Action panel to process all files sequentially using their locked-in settings. If the queue is empty but an input file is set in the 'Input/Output' panel, 'Clean Video' will process that single file with current options.
- Pausing: During queue processing, click 'Pause' (in the Action panel) to halt operations after the currently processing file finishes. Click 'Resume' to continue.
- Persistence: If you close the GUI with files still in the queue, they will be saved and reloaded the next time you open Cleanvid. The queue is cleared from saved state once successfully processed or manually cleared.
- Tooltips: Hover over files in the queue to see their specific locked-in settings. Hover over buttons for brief information about their function.

Note: Each file in the queue is processed as an independent job with its own set of captured settings.
"""
        messagebox.showinfo(title, help_message)

    def get_persistable_queue(self):
        return copy.deepcopy(self.queue_items)

    def repopulate_from_saved(self, saved_queue_items):
        if saved_queue_items is not None and isinstance(saved_queue_items, list):
            self.queue_items = copy.deepcopy(saved_queue_items)
            if self.queue_items:
                max_id = 0
                for item in self.queue_items:
                    try:
                        item_id_str = item.get("id", "item_0")
                        if isinstance(item_id_str, str):
                            num_part = int(item_id_str.split("_")[-1])
                            if num_part > max_id:
                                max_id = num_part
                        else:
                            print(f"Warning: Unexpected item ID type: {item_id_str} in saved queue.")
                    except ValueError:
                        print(f"Warning: Could not parse ID number from '{item.get('id')}' in saved queue.")
                    except AttributeError:
                        print(f"Warning: ID attribute error for item '{item.get('id')}' in saved queue.")
                self.item_id_counter = max_id + 1
            else:
                self.item_id_counter = 0
            self.update_queue_display()
            if self.action_output_frame:
                self.action_output_frame.update_clean_button_state()
