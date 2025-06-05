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
        self.output_queue = output_queue # Queue for thread-safe output logging

        # References to other frames (set by the main frame after instantiation)
        self.input_output_frame = None # type: InputOutputFrame
        self.options_frame = None # type: OptionsFrame

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1) # Allow output console to expand horizontally
        self.grid_rowconfigure(1, weight=1) # Allow output console to expand vertically

        # --- Process Management ---
        self.process = None # To hold the subprocess object
        self.stop_thread = threading.Event() # Event to signal reader threads to stop

        # --- UI Elements ---
        # Buttons Frame (to hold Clean and Copy buttons)
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="ew")
        buttons_frame.grid_columnconfigure(0, weight=1) # Push clean button left

        self.clean_button = ctk.CTkButton(buttons_frame, text="Clean Video", command=self.start_clean_process, height=35, text_color="white", fg_color="green", hover_color="darkgreen")
        self.clean_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        Tooltip(self.clean_button, "Start the video cleaning process based on the selected options.")

        self.copy_button = ctk.CTkButton(buttons_frame, text="Copy Output", command=self.copy_output)
        self.copy_button.grid(row=0, column=1, padx=5, pady=5, sticky="e")
        Tooltip(self.copy_button, "Copy the entire content of the output console below to the clipboard.")

        # Output Console
        self.output_console = ctk.CTkTextbox(self, wrap=tk.WORD, state="disabled", font=("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10))
        self.output_console.grid(row=1, column=0, padx=5, pady=(5, 5), sticky="nsew")
        Tooltip(self.output_console, "Displays the output and errors from the cleanvid process.")

        # Start periodic check for output queue
        self.after(100, self.process_output_queue)


    def log_output(self, message):
        """Appends a message to the output console in a thread-safe manner."""
        # Put the message in the queue to be processed by the main thread
        self.output_queue.put(message)

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


    def start_clean_process(self):
        """Validates inputs, constructs the command, and starts the cleanvid process."""
        # Ensure references to other frames are set
        if not self.input_output_frame or not self.options_frame:
             messagebox.showerror("Internal Error", "GUI components not fully initialized.")
             self.log_output("Internal Error: GUI components not fully initialized.\n")
             return

        # --- Get values from other frames ---
        input_video = self.input_output_frame.input_video_var.get()
        input_subs = self.input_output_frame.input_subs_var.get()
        save_to_same_dir = self.input_output_frame.save_to_same_dir_var.get()
        output_dir = self.input_output_frame.output_dir_var.get()
        output_filename = self.input_output_frame.output_filename_var.get()

        win_mode = self.options_frame.win_mode_var.get()
        alass_mode = self.options_frame.alass_mode_var.get()
        swears_file = self.options_frame.swears_file_var.get()
        subtitle_lang = self.options_frame.subtitle_lang_var.get()
        padding = self.options_frame.padding_var.get()
        embed_subs = self.options_frame.embed_subs_var.get()
        full_subs = self.options_frame.full_subs_var.get()
        subs_only = self.options_frame.subs_only_var.get()
        offline = self.options_frame.offline_var.get()
        edl = self.options_frame.edl_var.get()
        json_dump = self.options_frame.json_var.get()
        plex_json = self.options_frame.plex_json_var.get()
        plex_id = self.options_frame.plex_id_var.get()
        subs_output = self.options_frame.subs_output_var.get()
        re_encode_video = self.options_frame.re_encode_video_var.get()
        re_encode_audio = self.options_frame.re_encode_audio_var.get()
        burn_subs = self.options_frame.burn_subs_var.get()
        downmix = self.options_frame.downmix_var.get()
        video_params = self.options_frame.video_params_var.get()
        audio_params = self.options_frame.audio_params_var.get()
        audio_stream_index = self.options_frame.audio_stream_index_var.get()
        threads = self.options_frame.threads_var.get()
        chapter_markers = self.options_frame.chapter_markers_var.get() # Get chapter markers state
        fast_index = self.options_frame.fast_index_var.get() # Add this


        # --- Input Validation ---
        if not input_video or not os.path.isfile(input_video):
            messagebox.showerror("Error", "Please select a valid input video file.")
            self.log_output("Error: No valid input video file selected.\n")
            return

        if not swears_file or not os.path.isfile(swears_file):
             # Try default location one more time if field is empty/invalid
             default_swears = os.path.join(os.path.dirname(__file__), '..', 'swears.txt')
             if os.path.isfile(default_swears):
                 self.options_frame.swears_file_var.set(default_swears) # Update the UI
                 swears_file = default_swears
                 self.log_output(f"Using default swears file: {swears_file}\n")
             else:
                 messagebox.showerror("Error", f"Please select a valid swears file.\nDefault not found at: {default_swears}")
                 self.log_output(f"Error: No valid swears file selected or default not found at {default_swears}.\n")
                 return

        # Validate output path if not saving to same directory
        output_path = "" # To store the final output path for logging/checking
        if not save_to_same_dir:
            if not output_dir or not os.path.isdir(output_dir):
                messagebox.showerror("Error", "Please select a valid output directory.")
                self.log_output("Error: No valid output directory selected for custom path.\n")
                return
            if not output_filename:
                messagebox.showerror("Error", "Please enter a valid output filename.")
                self.log_output("Error: No output filename entered for custom path.\n")
                return
            output_path = os.path.join(output_dir, output_filename)
        else:
             # If saving to same dir, construct the expected output path for checking later
             in_path = Path(input_video)
             output_path = os.path.join(in_path.parent, f"{in_path.stem}_clean{in_path.suffix}")


        # --- Construct Command ---
        script_dir = Path(__file__).parent.parent # Go up from gui to cleanvid dir
        python_exe = sys.executable # Use the same python interpreter

        # Always use cleanvid.py; pass --win argument if needed
        script_to_run = script_dir / "cleanvid.py"

        if not script_to_run.exists():
             messagebox.showerror("Error", f"Core script not found: {script_to_run}")
             self.log_output(f"Error: Required script not found at {script_to_run}.\n")
             return

        cmd = [python_exe, str(script_to_run)]

        # Add arguments based on UI selections
        cmd.extend(["-i", input_video])
        if input_subs and os.path.isfile(input_subs):
            cmd.extend(["-s", input_subs])
        elif input_subs and not os.path.isfile(input_subs):
             messagebox.showwarning("Warning", f"Specified subtitle file not found:\n{input_subs}\nCleanvid will attempt auto-download/extraction.")
             self.log_output(f"Warning: Specified subtitle file not found: {input_subs}. Cleanvid will attempt auto-download/extraction.\n")

        if not save_to_same_dir:
            cmd.extend(["-o", output_path])

        if win_mode: cmd.append("--win") # Add --win argument if checked
        if alass_mode: cmd.append("--alass")
        # Check enable flags before adding optional arguments
        if self.options_frame.enable_swears_file_var.get() and swears_file:
             cmd.extend(["-w", swears_file])
        if self.options_frame.enable_subtitle_lang_var.get() and subtitle_lang:
             cmd.extend(["-l", subtitle_lang])
        # Padding needs special check for > 0 even if enabled
        if self.options_frame.enable_padding_var.get() and padding > 0:
             cmd.extend(["-p", str(padding)])
        if embed_subs: cmd.append("--embed-subs")
        if full_subs: cmd.append("-f")
        if subs_only: cmd.append("--subs-only")
        if offline: cmd.append("--offline")
        if edl: cmd.append("--edl")
        if json_dump: cmd.append("--json")
        if subs_output: cmd.extend(["--subs-output", subs_output])
        if plex_json: cmd.extend(["--plex-auto-skip-json", plex_json])
        if plex_id: cmd.extend(["--plex-auto-skip-id", plex_id])
        if re_encode_video: cmd.append("--re-encode-video")
        if re_encode_audio: cmd.append("--re-encode-audio")
        if burn_subs: cmd.append("-b")
        if downmix: cmd.append("-d")
        if self.options_frame.enable_video_params_var.get() and video_params:
             cmd.extend(["-v", video_params])
        if self.options_frame.enable_audio_params_var.get() and audio_params:
             cmd.extend(["-a", audio_params])
        if self.options_frame.enable_audio_stream_index_var.get() and audio_stream_index:
            try:
                int(audio_stream_index) # Validate it's an integer
                cmd.extend(["--audio-stream-index", audio_stream_index])
            except ValueError:
                 messagebox.showwarning("Warning", f"Invalid Audio Stream Index '{audio_stream_index}'. Ignoring.")
                 self.log_output(f"Warning: Invalid Audio Stream Index '{audio_stream_index}'. Ignoring.\n")
        if self.options_frame.enable_threads_var.get() and threads:
            try:
                int(threads) # Validate it's an integer
                cmd.extend(["--threads", threads])
            except ValueError:
                 messagebox.showwarning("Warning", f"Invalid Threads value '{threads}'. Ignoring.")
                 self.log_output(f"Warning: Invalid Threads value '{threads}'. Ignoring.\n")

        if chapter_markers:
            cmd.append("--chapter")

        if fast_index: # Add this block
            cmd.append("--fast-index")

        # --- Execute in Thread ---
        self.output_console.configure(state="normal")
        self.output_console.delete("1.0", tk.END) # Clear previous output
        # Use shlex.join for displaying the command safely
        cmd_display = shlex.join(cmd)
        self.log_output(f"Executing: {cmd_display}\n------\n")
        self.output_console.configure(state="disabled")

        self.clean_button.configure(state="disabled", text="Cleaning...")
        self.stop_thread.clear() # Clear the stop event for a new run

        # Start the subprocess in a new thread
        thread = threading.Thread(target=self.run_cleanvid_thread, args=(cmd, output_path), daemon=True)
        thread.start()

    def run_cleanvid_thread(self, cmd, expected_output_path):
        """Runs the cleanvid command in a subprocess and handles output."""
        start_time = time.monotonic() # Use time.monotonic() for duration
        try:
            # Use Popen for non-blocking execution and stream reading
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, # Decode stdout/stderr as text
                encoding='utf-8', # Be explicit about encoding
                errors='replace', # Handle potential decoding errors gracefully
                bufsize=1, # Line buffered output
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0 # Hide console window on Windows
            )

            # Start threads to read stdout and stderr
            stdout_thread = threading.Thread(target=self.read_subprocess_output, args=(self.process.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=self.read_subprocess_output, args=(self.process.stderr, "stderr"), daemon=True)

            stdout_thread.start()
            stderr_thread.start()

            # Wait for the reader threads to finish (which happens when the subprocess closes the pipes)
            stdout_thread.join()
            stderr_thread.join()

            # Wait for the subprocess to finish and get its return code
            return_code = self.process.wait()

            end_time = time.monotonic() # Use time.monotonic()
            duration = end_time - start_time # Calculate duration

            result_message = f"------\nProcess finished with exit code: {return_code} (Duration: {duration:.2f}s)\n"

            # Check for expected output file if not in subs_only or edl mode
            if return_code == 0 and not (self.options_frame.subs_only_var.get() or self.options_frame.edl_var.get() or self.options_frame.json_var.get() or self.options_frame.plex_json_var.get()):
                 if expected_output_path and os.path.exists(expected_output_path):
                      result_message += f"Output file created: {expected_output_path}\n"
                 else:
                      result_message += f"Warning: Process finished successfully, but expected output file not found:\n{expected_output_path}\n"
            elif return_code == 0:
                 result_message += f"Processing likely completed successfully (subtitle/EDL/JSON output).\n" # Assume success for these modes

            self.log_output(result_message) # Log the final result message

        except FileNotFoundError:
            self.log_output(f"--- Error: Command not found. Is '{cmd[0]}' in your PATH? ---\n")
            messagebox.showerror("Execution Error", f"Command not found. Is '{cmd[0]}' in your PATH?")
        except Exception as e:
            self.log_output(f"--- Error running command: {e} ---\n")
            messagebox.showerror("Execution Error", f"An error occurred during execution:\n{e}")
        finally:
            self.process = None # Clear the process reference
            self.stop_thread.clear() # Ensure stop event is clear for the next run
            # Re-enable button on the main thread using after()
            self.after(0, self.on_process_finished)

    def on_process_finished(self):
        """Callback executed on the main thread after the subprocess finishes."""
        self.clean_button.configure(state="normal", text="Clean Video")

    def list_audio_streams_and_output(self, input_video_path):
        """Runs cleanvid with --audio-stream-list and outputs to the console."""
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

        self.clean_button.configure(state="disabled") # Disable main button during list
        self.stop_thread.clear() # Clear the stop event

        # Run this in a thread to keep the GUI responsive
        thread = threading.Thread(target=self.run_list_streams_thread, args=(cmd,), daemon=True)
        thread.start()

    def run_list_streams_thread(self, cmd):
         """Runs the list streams command and puts output in queue."""
         start_time = time.monotonic() # Use time.monotonic()
         try:
            list_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            stdout_thread = threading.Thread(target=self.read_subprocess_output, args=(list_proc.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=self.read_subprocess_output, args=(list_proc.stderr, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            stdout_thread.join()
            stderr_thread.join()

            list_proc.wait()
            return_code = list_proc.returncode

            end_time = time.monotonic() # Use time.monotonic()
            duration = end_time - start_time

            self.log_output(f"------\nList streams finished (exit code: {return_code}, Duration: {duration:.2f}s)\n")

         except FileNotFoundError:
            self.log_output(f"--- Error: Command not found. Is '{cmd[0]}' in your PATH? ---\n")
            messagebox.showerror("Execution Error", f"Command not found. Is '{cmd[0]}' in your PATH?")
         except Exception as e:
            self.log_output(f"--- Error listing streams: {e} ---\n")
            messagebox.showerror("Execution Error", f"An error occurred while listing streams:\n{e}")
         finally:
            # Re-enable button on the main thread
            self.after(0, self.on_process_finished)


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
        # Check if a process is running before allowing close
        if self.process and self.process.poll() is None: # poll() returns None if process is still running
             if messagebox.askyesno("Exit Confirmation", "A cleaning process is still running.\nExiting now may leave incomplete files.\n\nAre you sure you want to exit?"):
                 self.log_output("Attempting to terminate running process...\n")
                 self.stop_thread.set() # Signal reader threads to stop
                 if self.process:
                     try:
                         self.process.terminate() # Ask nicely first
                         self.process.wait(timeout=2) # Wait briefly
                     except subprocess.TimeoutExpired:
                         self.log_output("Process did not terminate gracefully, killing...\n")
                         self.process.kill() # Force kill
                     except Exception as e:
                         self.log_output(f"Error terminating process: {e}\n")
                 return True # Allow closing
             else:
                 return False # Do not allow closing
        else:
            return True # Allow closing if no process is running


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