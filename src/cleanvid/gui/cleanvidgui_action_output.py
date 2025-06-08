import os
from pathlib import Path
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import queue
import sys
import os
from pathlib import Path
import shlex # To properly split command strings for subprocess
import time # Import the time module

from .cleanvidgui_tooltip import Tooltip
from .cleanvidgui_config import ConfigManager # Import ConfigManager for default paths if needed

# Need references to other frames to get input values and options
# from .cleanvidgui_input_output import InputOutputFrame # Imported via type hinting or passed reference
# from .cleanvidgui_options import OptionsFrame # Imported via type hinting or passed reference

class ActionOutputFrame(ctk.CTkFrame):
    """
    Frame containing the Clean Video button, output console, and copy button.
    Manages subprocess execution and output display.
    """
    def __init__(self, master, config_manager, output_queue):
        super().__init__(master)
        self.config_manager = config_manager
        self.output_queue = output_queue

        # References to other frames (set by the main frame after instantiation)
        self.input_output_frame = None
        self.options_frame = None
        self.queue_frame = None # Will be set by MainFrame

        self.is_processing_queue = False
        self.is_paused = False # For pause/resume state
        self.pause_requested = False # To signal a desire to pause
        self.process = None
        self.stop_thread = threading.Event()

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- UI Elements ---
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="ew")
        buttons_frame.grid_columnconfigure(0, weight=0) # Clean button
        buttons_frame.grid_columnconfigure(1, weight=0) # Pause button
        buttons_frame.grid_columnconfigure(2, weight=1) # Pushes copy button to the right

        self.clean_button = ctk.CTkButton(buttons_frame, text="Clean Video", command=self.initiate_processing, height=35)
        self.clean_button.grid(row=0, column=0, padx=(5,2), pady=5, sticky="w")
        Tooltip(self.clean_button, "Start the video cleaning process or process the current queue.")

        self.pause_button = ctk.CTkButton(buttons_frame, text="Pause", command=self.toggle_pause_resume, state="disabled", height=35)
        self.pause_button.grid(row=0, column=1, padx=2, pady=5, sticky="w")
        Tooltip(self.pause_button, "Pause or resume queue processing after the current file.")

        self.copy_button = ctk.CTkButton(buttons_frame, text="Copy Output", command=self.copy_output, height=35)
        self.copy_button.grid(row=0, column=2, padx=(5,5), pady=5, sticky="e")
        Tooltip(self.copy_button, "Copy the entire content of the output console below to the clipboard.")

        # Output Console
        self.output_console = ctk.CTkTextbox(self, wrap=tk.WORD, state="disabled", font=("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10))
        self.output_console.grid(row=1, column=0, padx=5, pady=(5, 5), sticky="nsew")
        Tooltip(self.output_console, "Displays the output and errors from the cleanvid process.")

        # Start periodic check for output queue
        self.after(100, self.process_output_queue)
        self.update_pause_button_state() # Initial state for pause button
        # self.update_clean_button_state() will be called by MainFrame or when queue_frame is set


    def log_output(self, message, main_log=True): # Added main_log for future flexibility
        """Appends a message to the output console in a thread-safe manner."""
        if main_log:
            self.output_queue.put(message)
        else: # For item-specific status, could go to a different log or be handled differently
            print(message)


    def process_output_queue(self):
        """Checks the queue for messages from subprocess threads and appends them to the console."""
        try:
            while True:
                # Get messages from the queue without blocking
                line = self.output_queue.get_nowait()
                # Append the message to the textbox on the main thread
                self.output_console.configure(state="normal")
                self.output_console.insert(tk.END, line)
                self.output_console.see(tk.END) # Scroll to the end
                self.output_console.configure(state="disabled")
        except queue.Empty:
            pass # No items in the queue
        except Exception as e:
            # Log errors related to processing the queue itself
            print(f"Error processing output queue: {e}")
        finally:
            # Reschedule the check after a short delay
            self.after(100, self.process_output_queue)

    def read_subprocess_output(self, pipe, stream_name):
        """Reads output from a subprocess pipe line by line and puts it in the queue."""
        try:
            # Use iter to read line by line until the pipe is closed
            for line in iter(pipe.readline, ''):
                if self.stop_thread.is_set():
                    break # Stop reading if the stop event is set
                self.log_output(line) # Put the line in the queue
            pipe.close()
        except Exception as e:
            # Log errors related to reading the pipe
            self.log_output(f"--- Error reading {stream_name}: {e} ---\n")


    def update_clean_button_state(self):
        """Updates the text and state of the main action button based on queue and processing state."""
        # Placeholder - will be implemented fully later
        if not self.queue_frame:
            self.clean_button.configure(text="Clean Video", state="normal", fg_color="green", hover_color="darkgreen")
            # self.update_pause_button_state() # Pause button should also be updated
            return

        if self.is_processing_queue and not self.is_paused:
            self.clean_button.configure(text="Processing Queue...", state="disabled", fg_color="gray50", hover_color="gray40")
        elif self.is_paused:
            self.clean_button.configure(text="Queue Paused", state="disabled", fg_color="gray50", hover_color="gray40")
        elif self.queue_frame.get_item_count() > 0:
            self.clean_button.configure(text="Run Queue", state="normal", fg_color="blue", hover_color="darkblue")
        else: # Not processing, not paused, queue is empty
            self.clean_button.configure(text="Clean Video", state="normal", fg_color="green", hover_color="darkgreen")

        self.update_pause_button_state() # Ensure pause button is also updated


    def initiate_processing(self):
        """Initiates processing for the queue or a single item if the queue is empty."""
        self.log_output("Initiating processing...\n")
        if self.is_processing_queue and not self.is_paused: # If processing and not paused, don't restart
            self.log_output("Queue processing is already active.\n")
            return

        if self.is_paused: # If paused, this action means to effectively stop/reset and start fresh
            self.log_output("Queue was paused. Resetting and starting fresh...\n")
            self.is_paused = False
            self.pause_requested = False
            # self.is_processing_queue will be set to true below or handled by single job logic

        if self.queue_frame and self.queue_frame.get_item_count() > 0:
            self.is_processing_queue = True
            self.is_paused = False
            self.pause_requested = False
            self.update_clean_button_state() # This will also call update_pause_button_state
            self.log_output("--- Starting queue processing... ---\n")
            self.process_next_queue_item()
        else:
            # No items in queue, try to run as a single job if input_output_frame has a file
            if self.input_output_frame and self.input_output_frame.input_video_var.get():
                self.log_output("Queue is empty. Processing as a single job from Input/Output panel.\n")

                input_video = self.input_output_frame.input_video_var.get()
                if not input_video or not os.path.isfile(input_video):
                    messagebox.showerror("Error", "Please select a valid input video file for single processing.")
                    self.log_output("Error: No valid input video selected for single processing.\n")
                    self.update_clean_button_state() # Ensure button resets
                    return

                if not self.options_frame:
                    messagebox.showerror("Internal Error", "Options Frame not available for single processing.")
                    self.log_output("Error: Options Frame not available for single processing.\n")
                    self.update_clean_button_state()
                    return

                current_settings = self.options_frame.get_state()

                # Validate swears file for single run (similar to old start_clean_process)
                # This validation should ideally be part of get_state or a dedicated validation method in OptionsFrame
                swears_file_path = current_settings.get('swears_file', '')
                if current_settings.get('enable_swears_file', False) and (not swears_file_path or not os.path.isfile(swears_file_path)):
                    # Path to the gui directory, then up to src, then to cleanvid/swears.txt
                    # This assumes a certain directory structure.
                    # A better way would be to use a path relative to the main script or a config setting.
                    # For now, constructing path relative to this file's parent's parent.
                    # __file__ -> action_output.py -> gui -> src -> cleanvid -> swears.txt
                    # This is fragile. Consider making swears_file path resolution more robust.
                    project_root = Path(__file__).parent.parent.parent
                    default_swears = project_root / 'cleanvid' / 'swears.txt'
                    if os.path.isfile(default_swears):
                        # self.options_frame.swears_file_var.set(str(default_swears)) # Update UI if OptionsFrame allows
                        current_settings['swears_file'] = str(default_swears)
                        self.log_output(f"Using default swears file for single job: {default_swears}\n")
                    else:
                        messagebox.showerror("Error", f"Swears file not found for single job.\nDefault not found: {default_swears}")
                        self.log_output(f"Error: Swears file not found for single job or default not found.\n")
                        self.update_clean_button_state()
                        return

                single_item = {
                    "id": "single_job_0",
                    "file_path": input_video,
                    "settings": current_settings
                }

                self.is_processing_queue = True # Treat as a queue of one
                self.update_clean_button_state()

                output_info = self.input_output_frame.get_state()
                input_video_path = output_info.get("input_video")
                save_to_same_dir = output_info.get("save_to_same_dir", True) # Default to True for safety
                output_dir = output_info.get("output_dir")
                output_filename = output_info.get("output_filename")

                suggested_output_path = ""
                if input_video_path:
                    input_path_obj = Path(input_video_path)
                    if save_to_same_dir:
                        suggested_output_path = str(input_path_obj.parent / f"{input_path_obj.stem}_clean{input_path_obj.suffix}")
                    elif output_dir and output_filename:
                        suggested_output_path = str(Path(output_dir) / output_filename)
                    elif output_dir: # Fallback if filename is empty but dir is set
                         suggested_output_path = str(Path(output_dir) / f"{input_path_obj.stem}_clean{input_path_obj.suffix}")


                self._execute_cleanvid_task(
                    single_item['file_path'],
                    suggested_output_path,
                    single_item['settings'],
                    single_item['id'],
                    is_single_job=True
                )
            else:
                self.log_output("Queue is empty. Add files to the queue or select an input file to start processing.\n")
                messagebox.showinfo("Queue Empty", "The queue is empty. Please add files to the queue or select an input file in the Input/Output panel.")
                self.update_clean_button_state()


    def process_next_queue_item(self):
        """Processes the next item from the queue, handling pause requests."""
        if self.pause_requested:
            self.is_paused = True
            self.pause_requested = False # Reset request as it's now handled
            self.log_output("--- Queue processing paused. ---\n")
            self.update_clean_button_state() # Updates both buttons via its call to update_pause_button_state
            return

        if not self.is_processing_queue: # If processing was stopped (e.g. by finishing queue while pause was requested)
            self.log_output("Processing was stopped or finished.\n")
            self.on_queue_finished() # Ensure clean state
            return

        if not self.queue_frame:
            self.log_output("Error: Queue Frame not available.\n")
            self.on_queue_finished()
            return

        item_to_process = self.queue_frame.get_next_item_for_processing()

        if item_to_process is None: # Queue is now empty
            self.on_queue_finished()
            return

        file_path = item_to_process['file_path']
        settings_dict = item_to_process['settings']
        item_id = item_to_process['id']

        self.log_output(f"--- Starting processing for: {os.path.basename(file_path)} (ID: {item_id}) ---\n")
        if self.queue_frame:
            self.queue_frame.update_item_status(item_id, "Processing...")

        input_p = Path(file_path)
        # Default output path suggestion (cleanvid.py handles actual output path based on its logic and -o)
        output_path_suggestion = str(input_p.parent / f"{input_p.stem}_clean{input_p.suffix}")

        # If 'output_dir' and 'output_filename' are in settings_dict, they will be used by _execute_cleanvid_task to form the -o argument.
        # The output_path_suggestion here is mainly for post-process checks or if -o isn't used.
        if 'output_dir' in settings_dict and 'output_filename' in settings_dict:
            output_path_suggestion = os.path.join(settings_dict['output_dir'], settings_dict['output_filename'])


        self._execute_cleanvid_task(file_path, output_path_suggestion, settings_dict, item_id, is_single_job=False)


    def _execute_cleanvid_task(self, input_video_path, output_path_suggestion, settings_dict, item_id, is_single_job=False):
        """Constructs and executes the cleanvid command for a given item."""
        # Determine script path relative to this file
        # __file__ (action_output.py) -> parent (gui) -> parent (src) -> cleanvid -> cleanvid.py
        script_dir = Path(__file__).parent.parent.parent / "cleanvid"
        python_exe = sys.executable # Use the same python interpreter
        script_to_run = script_dir / "cleanvid.py"

        if not script_to_run.exists():
             messagebox.showerror("Error", f"Core script not found: {script_to_run}")
             self.log_output(f"Error: Required script not found at {script_to_run}.\n")
             if not is_single_job:
                 self.after(0, self.process_next_queue_item)
             else:
                 self.on_queue_finished()
             return

        cmd = [python_exe, str(script_to_run)]
        cmd.extend(["-i", input_video_path])

        # Apply settings from settings_dict
        if settings_dict.get('input_subs') and os.path.isfile(settings_dict['input_subs']):
            cmd.extend(["-s", settings_dict['input_subs']])

        final_output_path_for_checking = output_path_suggestion
        # Logic for -o argument:
        # If 'save_to_same_dir' is explicitly False in settings_dict (meaning custom path is intended)
        # AND 'output_dir' and 'output_filename' are provided in settings_dict.
        if settings_dict.get('save_to_same_dir') is False:
            custom_output_dir = settings_dict.get('output_dir')
            custom_output_filename = settings_dict.get('output_filename')
            if custom_output_dir and custom_output_filename and os.path.isdir(custom_output_dir):
                specific_output_for_o_arg = os.path.join(custom_output_dir, custom_output_filename)
                cmd.extend(["-o", specific_output_for_o_arg])
                final_output_path_for_checking = specific_output_for_o_arg # This is what we'll check for
            elif not is_single_job : # If part of queue and custom path invalid, log warning
                self.log_output(f"Warning: Item {item_id} intended custom output path, but dir/filename invalid. Defaulting.\n")


        # Boolean flags and optional args from settings_dict
        if settings_dict.get('win_mode'): cmd.append("--win")
        if settings_dict.get('alass_mode'): cmd.append("--alass")
        if settings_dict.get('enable_swears_file', False) and settings_dict.get('swears_file') and os.path.isfile(settings_dict.get('swears_file')):
             cmd.extend(["-w", settings_dict['swears_file']])
        if settings_dict.get('enable_subtitle_lang', False) and settings_dict.get('subtitle_lang'):
             cmd.extend(["-l", settings_dict['subtitle_lang']])
        padding_val = settings_dict.get('padding', 0.0)
        if settings_dict.get('enable_padding', False) and isinstance(padding_val, (int, float)) and padding_val > 0:
             cmd.extend(["-p", str(padding_val)])
        if settings_dict.get('embed_subs'): cmd.append("--embed-subs")
        if settings_dict.get('full_subs'): cmd.append("-f") # Ensure this is the correct flag (often --full-subs)
        if settings_dict.get('subs_only'): cmd.append("--subs-only")
        if settings_dict.get('offline'): cmd.append("--offline")
        if settings_dict.get('edl'): cmd.append("--edl")
        if settings_dict.get('json'): cmd.append("--json") # Assuming --json, not --json-dump
        if settings_dict.get('subs_output'): cmd.extend(["--subs-output", settings_dict['subs_output']])
        if settings_dict.get('plex_auto_skip_json'): cmd.extend(["--plex-auto-skip-json", settings_dict['plex_auto_skip_json']])
        if settings_dict.get('plex_id'): cmd.extend(["--plex-auto-skip-id", settings_dict['plex_id']])
        if settings_dict.get('re_encode_video'): cmd.append("--re-encode-video")
        if settings_dict.get('re_encode_audio'): cmd.append("--re-encode-audio")
        if settings_dict.get('burn_subs'): cmd.append("-b") # Ensure this is the correct flag (often --burn-subs)
        if settings_dict.get('downmix'): cmd.append("-d") # Ensure this is the correct flag (often --downmix-audio)
        if settings_dict.get('enable_video_params', False) and settings_dict.get('video_params'):
             cmd.extend(["-v", settings_dict['video_params']])
        if settings_dict.get('enable_audio_params', False) and settings_dict.get('audio_params'):
             cmd.extend(["-a", settings_dict['audio_params']])
        audio_idx = settings_dict.get('audio_stream_index')
        if settings_dict.get('enable_audio_stream_index', False) and audio_idx is not None and str(audio_idx).strip() != "":
            cmd.extend(["--audio-stream-index", str(audio_idx)])
        threads_val = settings_dict.get('threads')
        if settings_dict.get('enable_threads', False) and threads_val is not None and str(threads_val).strip() != "":
            cmd.extend(["--threads", str(threads_val)])
        if settings_dict.get('chapter_markers'): cmd.append("--chapter")
        if settings_dict.get('fast_index'): cmd.append("--fast-index")

        self.output_console.configure(state="normal")
        # Clear console only if it's a new queue item or single job, not for subsequent messages of the same item
        if not hasattr(self, '_last_processed_item_id') or self._last_processed_item_id != item_id:
            self.output_console.delete("1.0", tk.END)
        self._last_processed_item_id = item_id # Store last item ID

        cmd_display = shlex.join(cmd)
        self.log_output(f"Executing for Item ID {item_id}: {cmd_display}\n------\n")
        self.output_console.configure(state="disabled")

        self.stop_thread.clear()
        # Pass settings_dict to run_cleanvid_thread for output checking logic
        thread = threading.Thread(target=self.run_cleanvid_thread, args=(cmd, final_output_path_for_checking, item_id, is_single_job, settings_dict), daemon=True)
        thread.start()


    def on_queue_finished(self):
        """Called when the queue processing is complete."""
        if hasattr(self, '_last_processed_item_id'):
            del self._last_processed_item_id
        self.is_processing_queue = False
        self.is_paused = False
        self.pause_requested = False
        self.update_clean_button_state() # This will also call update_pause_button_state
        self.log_output("--- Queue processing finished. ---\n")


    def toggle_pause_resume(self):
        """Toggles the pause/resume state of the queue processing."""
        if self.is_paused: # Currently paused, so resume
            self.is_paused = False
            self.pause_requested = False
            self.log_output("--- Resuming queue processing... ---\n")
            self.update_clean_button_state() # Update button states
            # Important: process_next_queue_item will handle the is_processing_queue check
            # and ensure it doesn't run if the queue became empty while paused.
            if self.is_processing_queue: # Only try to process if the queue was active
                 self.process_next_queue_item()
            else: # If queue finished while paused (e.g. last item processed before pause took effect)
                 self.on_queue_finished() # Ensure everything is reset correctly

        elif self.is_processing_queue: # Actively processing, so request pause
            self.pause_requested = True
            self.log_output("--- Pause requested. Will pause after the current file finishes. ---\n")
            # No need to change is_paused here, process_next_queue_item will handle it.
            # self.pause_button.configure(text="Pausing...", state="disabled") # Immediate feedback that request is acknowledged
            self.update_pause_button_state() # Update button to "Pausing..."
        else:
            # Not processing, so pause button shouldn't be active to begin with, but handle defensively
            self.log_output("Not processing, nothing to pause/resume.\n")
            self.is_paused = False
            self.pause_requested = False
            self.update_pause_button_state()


    def update_pause_button_state(self):
        """Manages the state and text of the pause_button."""
        if not self.is_processing_queue:
            self.pause_button.configure(text="Pause", state="disabled")
        else: # Queue is processing
            if self.is_paused:
                self.pause_button.configure(text="Resume", state="normal")
            elif self.pause_requested:
                self.pause_button.configure(text="Pausing...", state="disabled")
            else: # Actively processing, not paused or requesting pause
                self.pause_button.configure(text="Pause", state="normal")


    def run_cleanvid_thread(self, cmd, expected_output_path, item_id, is_single_job=False, settings_dict=None):
        """Runs the cleanvid command in a subprocess and handles output."""
        if settings_dict is None:
            settings_dict = {} # Ensure settings_dict is a dict

        start_time = time.monotonic()
        return_code = -1 # Default to error
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            stdout_thread = threading.Thread(target=self.read_subprocess_output, args=(self.process.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=self.read_subprocess_output, args=(self.process.stderr, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            stdout_thread.join()
            stderr_thread.join()
            return_code = self.process.wait()
        except FileNotFoundError:
            self.log_output(f"--- Error: Command not found for item {item_id}. Is '{cmd[0]}' in your PATH? ---\n")
        except Exception as e:
            self.log_output(f"--- Error running command for item {item_id}: {e} ---\n")
        finally:
            duration = time.monotonic() - start_time
            result_message = f"------\nItem {item_id} finished with exit code: {return_code} (Duration: {duration:.2f}s)\n"

            # Use the passed settings_dict for checking output conditions
            if return_code == 0 and not (settings_dict.get('subs_only') or settings_dict.get('edl') or settings_dict.get('json') or settings_dict.get('plex_json')):
                 if expected_output_path and os.path.exists(expected_output_path):
                      result_message += f"Output file for item {item_id} created: {expected_output_path}\n"
                 else:
                      result_message += f"Warning: Item {item_id} finished successfully, but expected output file not found:\n{expected_output_path}\n"
            elif return_code == 0:
                 result_message += f"Item {item_id} processing likely completed successfully (subtitle/EDL/JSON output).\n"

            self.log_output(result_message)

            self.process = None
            self.stop_thread.clear()

            if self.queue_frame: # Optional status update
                 status = "Completed" if return_code == 0 else "Failed"
                 self.queue_frame.update_item_status(item_id, status)

            if is_single_job:
                self.after(0, self.on_queue_finished)
            else:
                self.after(0, self.process_next_queue_item) # Key change: process next item

    # on_process_finished is effectively replaced by on_queue_finished or the loop in process_next_queue_item
    # def on_process_finished(self):
    #     """Callback executed on the main thread after the subprocess finishes."""
    #     self.update_clean_button_state() # Use new method

    def list_audio_streams_and_output(self, input_video_path):
        """Runs cleanvid with --audio-stream-list and outputs to the console."""
        # This method should also use update_clean_button_state before/after if it disables the main button
        if not input_video_path or not os.path.isfile(input_video_path):
            messagebox.showerror("Error", "Please select a valid input video file first to list streams.")
            self.log_output("Error: No valid input video file selected to list streams.\n")
            return

        script_dir = Path(__file__).parent.parent # Go up from gui to cleanvid dir
        python_exe = sys.executable
        # Always use cleanvid.py for listing, not cleanvidwin.py
        script_to_run = script_dir / "cleanvid.py"

        if not script_to_run.exists():
             messagebox.showerror("Error", f"Required script not found: {script_to_run}")
             self.log_output(f"Error: Required script not found at {script_to_run}.\n")
             return

        cmd = [python_exe, str(script_to_run), "-i", input_video_path, "--audio-stream-list"]

        self.output_console.configure(state="normal")
        # Use shlex.join for displaying the command safely
        cmd_display = shlex.join(cmd)
        self.log_output(f"Executing: {cmd_display}\n------\n")
        self.output_console.configure(state="disabled")

        if self.is_processing_queue: # Prevent if main queue is running
            messagebox.showwarning("Busy", "Cannot list streams while main queue is processing.")
            return

        # Store original button state to restore it after list streams is done
        self.original_clean_button_text = self.clean_button.cget("text")
        self.original_clean_button_state = self.clean_button.cget("state")
        self.original_clean_button_fg_color = self.clean_button.cget("fg_color")
        self.original_clean_button_hover_color = self.clean_button.cget("hover_color")

        self.clean_button.configure(state="disabled", text="Listing Streams...", fg_color="gray50", hover_color="gray40")
        self.stop_thread.clear()

        thread = threading.Thread(target=self.run_list_streams_thread, args=(cmd,), daemon=True)
        thread.start()

    def run_list_streams_thread(self, cmd):
         """Runs the list streams command and puts output in queue."""
         start_time = time.monotonic()
         try:
            # ... (subprocess execution as before) ...
            list_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding='utf-8', errors='replace', bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            stdout_thread = threading.Thread(target=self.read_subprocess_output, args=(list_proc.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=self.read_subprocess_output, args=(list_proc.stderr, "stderr"), daemon=True)
            stdout_thread.start(); stderr_thread.start() # Start threads
            stdout_thread.join(); stderr_thread.join() # Wait for threads
            list_proc.wait() # Wait for process
            self.log_output(f"------\nList streams finished (exit code: {list_proc.returncode}, Duration: {time.monotonic() - start_time:.2f}s)\n")
         except FileNotFoundError:
            self.log_output(f"--- Error: Command not found. Is '{cmd[0]}' in your PATH? ---\n")
         except Exception as e:
            self.log_output(f"--- Error listing streams: {e} ---\n")
         finally:
            # Restore button state using main thread, more robustly with update_clean_button_state
            self.after(0, lambda: self.clean_button.configure(
                text=self.original_clean_button_text,
                state=self.original_clean_button_state,
                fg_color=self.original_clean_button_fg_color,
                hover_color=self.original_clean_button_hover_color
            ))
            # Or even better, if button states are managed well:
            # self.after(0, self.update_clean_button_state)


    def copy_output(self):
        """Copies the content of the output console to the clipboard."""
        try:
            # Get all text from the textbox
            output_text = self.output_console.get("1.0", tk.END)
            # Remove trailing newline if present
            if output_text.endswith('\n'):
                output_text = output_text[:-1]

            if output_text: # Only copy if there's text
                self.clipboard_clear() # Clear current clipboard content
                self.clipboard_append(output_text) # Append the text
                self.update_idletasks() # Update the clipboard immediately

                # Provide feedback to the user
                self.copy_button.configure(text="Copied!")
                # Change button text back after a short delay
                self.after(1500, lambda: self.copy_button.configure(text="Copy Output"))
            # else:
            #     self.log_output("Nothing to copy.\n") # Optionally log if nothing was copied
        except Exception as e:
             messagebox.showerror("Clipboard Error", f"Could not copy to clipboard:\n{e}")
             self.log_output(f"Error copying to clipboard: {e}\n")


    def on_closing(self):
        """Method to be called by the main app when the window is closing."""
        # Check if a process is running before allowing close (covers queue processing too)
        if self.is_processing_queue or (self.process and self.process.poll() is None):
             if messagebox.askyesno("Exit Confirmation", "A cleaning process or queue is still running.\nExiting now may leave incomplete files.\n\nAre you sure you want to exit?"):
                 self.log_output("Attempting to terminate running process/queue...\n")
                 self.is_processing_queue = False # Stop further queue processing
                 self.stop_thread.set()
                 if self.process: # If a specific subprocess is active
                     try:
                         self.process.terminate()
                         self.process.wait(timeout=2)
                     except subprocess.TimeoutExpired:
                         self.log_output("Process did not terminate gracefully, killing...\n")
                         self.process.kill()
                     except Exception as e:
                         self.log_output(f"Error terminating process: {e}\n")
                 return True
             else:
                 return False
        return True


# Example Usage (for testing purposes, requires other modules)
if __name__ == "__main__":
    # This example requires the other gui modules to exist, even if empty
    # Create dummy files if they don't exist for testing
    import os
    from pathlib import Path
    dummy_files = [
        "cleanvidgui_config.py",
        "cleanvidgui_tooltip.py",
        "cleanvidgui_input_output.py", # Need a dummy for the reference
        "cleanvidgui_options.py", # Need a dummy for the reference
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
                elif "input_output" in fname:
                     f.write("class InputOutputFrame(ctk.CTkFrame): def __init__(self, master, **kwargs): super().__init__(master, **kwargs); self.input_video_var = ctk.StringVar(value='dummy_video.mp4'); self.input_subs_var = ctk.StringVar(); self.save_to_same_dir_var = ctk.BooleanVar(value=True); self.output_dir_var = ctk.StringVar(); self.output_filename_var = ctk.StringVar(); ctk.CTkLabel(self, text='InputOutputFrame Placeholder').pack()\n")
                     f.write("    def log_to_console(self, msg): print(f'DUMMY LOG (Input): {msg}', end='')\n")
                elif "options" in fname:
                     f.write("class OptionsFrame(ctk.CTkFrame): def __init__(self, master, **kwargs): super().__init__(master, **kwargs); self.win_mode_var = ctk.BooleanVar(value=False); self.alass_mode_var = ctk.BooleanVar(value=False); self.swears_file_var = ctk.StringVar(value='dummy_swears.txt'); self.subtitle_lang_var = ctk.StringVar(value='eng'); self.padding_var = ctk.DoubleVar(value=0.0); self.embed_subs_var = ctk.BooleanVar(value=False); self.full_subs_var = ctk.BooleanVar(value=False); self.subs_only_var = ctk.BooleanVar(value=False); self.offline_var = ctk.BooleanVar(value=False); self.edl_var = ctk.BooleanVar(value=False); self.json_var = ctk.BooleanVar(value=False); self.plex_json_var = ctk.StringVar(value=''); self.plex_id_var = ctk.StringVar(value=''); self.subs_output_var = ctk.StringVar(value=''); self.re_encode_video_var = ctk.BooleanVar(value=False); self.re_encode_audio_var = ctk.BooleanVar(value=False); self.burn_subs_var = ctk.BooleanVar(value=False); self.downmix_var = ctk.BooleanVar(value=False); self.video_params_var = ctk.StringVar(value=''); self.audio_params_var = ctk.StringVar(value=''); self.audio_stream_index_var = ctk.StringVar(value=''); self.threads_var = ctk.StringVar(value=''); ctk.CTkLabel(self, text='OptionsFrame Placeholder').pack()\n")
                     f.write("    def log_to_console(self, msg): print(f'DUMMY LOG (Options): {msg}', end='')\n")


    # Now import the dummy/real modules
    from .cleanvidgui_config import ConfigManager
    from .cleanvidgui_input_output import InputOutputFrame # Import dummy/real
    from .cleanvidgui_options import OptionsFrame # Import dummy/real
    import queue # Use real queue for the app

    root = ctk.CTk()
    root.title("ActionOutputFrame Demo")
    root.geometry("800x400") # Adjust size for this frame

    config_manager = ConfigManager()
    output_queue = queue.Queue()

    # Create dummy frames for the references
    dummy_input_output = InputOutputFrame(root)
    dummy_options = OptionsFrame(root, config_manager=config_manager)

    action_output_frame = ActionOutputFrame(root, config_manager=config_manager, output_queue=output_queue)
    # Manually set the references
    action_output_frame.input_output_frame = dummy_input_output
    action_output_frame.options_frame = dummy_options

    action_output_frame.pack(fill="both", expand=True, padx=10, pady=10)

    # Start the queue processing for this demo
    action_output_frame.after(100, action_output_frame.process_output_queue)


    root.mainloop()