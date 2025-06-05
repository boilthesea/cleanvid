import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
from pathlib import Path

from .cleanvidgui_tooltip import Tooltip
from .cleanvidgui_config import DEFAULT_CONFIG # Import DEFAULT_CONFIG for initial values

class OptionsFrame(ctk.CTkFrame):
    """
    Frame for handling all cleanvid options (core and advanced).
    Organizes advanced options into tabs.
    """
    def __init__(self, master, config_manager, action_output_frame=None):
        super().__init__(master)
        self.config_manager = config_manager
        self.action_output_frame = action_output_frame # Reference to the action/output frame for triggering actions

        # Configure grid layout for this frame (which will hold core options and the tabview)
        self.grid_columnconfigure(0, weight=1) # Allow the tabview to expand

        # --- Variables ---
        # Initialize variables from config, falling back to defaults
        self.win_mode_var = ctk.BooleanVar(value=self.config_manager.config.get("win_mode", DEFAULT_CONFIG["win_mode"]))
        self.alass_mode_var = ctk.BooleanVar(value=self.config_manager.config.get("alass_mode", DEFAULT_CONFIG["alass_mode"]))
        self.swears_file_var = ctk.StringVar(value=self.config_manager.config.get("swears_file", DEFAULT_CONFIG["swears_file"]))
        self.default_media_dir_var = ctk.StringVar(value=self.config_manager.config.get("default_media_dir", DEFAULT_CONFIG["default_media_dir"]))

        # Variables for Advanced Options (initialize with defaults or empty)
        self.subtitle_lang_var = ctk.StringVar(value=self.config_manager.config.get("subtitle_lang", DEFAULT_CONFIG.get("subtitle_lang", "eng")))
        self.padding_var = ctk.DoubleVar(value=self.config_manager.config.get("padding", DEFAULT_CONFIG.get("padding", 0.0)))
        self.embed_subs_var = ctk.BooleanVar(value=self.config_manager.config.get("embed_subs", DEFAULT_CONFIG.get("embed_subs", False)))
        self.full_subs_var = ctk.BooleanVar(value=self.config_manager.config.get("full_subs", DEFAULT_CONFIG.get("full_subs", False)))
        self.subs_only_var = ctk.BooleanVar(value=self.config_manager.config.get("subs_only", DEFAULT_CONFIG.get("subs_only", False)))
        self.offline_var = ctk.BooleanVar(value=self.config_manager.config.get("offline", DEFAULT_CONFIG.get("offline", False)))
        self.edl_var = ctk.BooleanVar(value=self.config_manager.config.get("edl", DEFAULT_CONFIG.get("edl", False)))
        self.json_var = ctk.BooleanVar(value=self.config_manager.config.get("json", DEFAULT_CONFIG.get("json", False)))
        self.plex_json_var = ctk.StringVar(value=self.config_manager.config.get("plex_json", DEFAULT_CONFIG.get("plex_json", "")))
        self.plex_id_var = ctk.StringVar(value=self.config_manager.config.get("plex_id", DEFAULT_CONFIG.get("plex_id", "")))
        self.subs_output_var = ctk.StringVar(value=self.config_manager.config.get("subs_output", DEFAULT_CONFIG.get("subs_output", "")))
        self.re_encode_video_var = ctk.BooleanVar(value=self.config_manager.config.get("re_encode_video", DEFAULT_CONFIG.get("re_encode_video", False)))
        self.re_encode_audio_var = ctk.BooleanVar(value=self.config_manager.config.get("re_encode_audio", DEFAULT_CONFIG.get("re_encode_audio", False)))
        self.burn_subs_var = ctk.BooleanVar(value=self.config_manager.config.get("burn_subs", DEFAULT_CONFIG.get("burn_subs", False)))
        self.downmix_var = ctk.BooleanVar(value=self.config_manager.config.get("downmix", DEFAULT_CONFIG.get("downmix", False)))
        self.video_params_var = ctk.StringVar(value=self.config_manager.config.get("video_params", DEFAULT_CONFIG.get("video_params", "-c:v libx264 -preset slow -crf 22")))
        self.audio_params_var = ctk.StringVar(value=self.config_manager.config.get("audio_params", DEFAULT_CONFIG.get("audio_params", "-c:a aac -ab 224k -ar 44100")))
        self.audio_stream_index_var = ctk.StringVar(value=self.config_manager.config.get("audio_stream_index", DEFAULT_CONFIG.get("audio_stream_index", ""))) # Use string for optional input
        self.threads_var = ctk.StringVar(value=self.config_manager.config.get("threads", DEFAULT_CONFIG.get("threads", ""))) # Use string for optional input
        self.chapter_markers_var = ctk.BooleanVar(value=self.config_manager.config.get("chapter_markers", DEFAULT_CONFIG.get("chapter_markers", False)))


        # --- Enable/Disable Variables for Optional Args ---
        # Initialize based on whether the value exists in config (or has a non-empty/non-default value)
        # Defaulting to True if value exists, False otherwise. Adjust logic if needed.
        swears_file_path = self.config_manager.config.get("swears_file", "")
        self.enable_swears_file_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_swears_file", bool(swears_file_path)))
        self.enable_subtitle_lang_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_subtitle_lang", "subtitle_lang" in self.config_manager.config))
        self.enable_padding_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_padding", "padding" in self.config_manager.config))
        self.enable_video_params_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_video_params", "video_params" in self.config_manager.config))
        self.enable_audio_params_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_audio_params", "audio_params" in self.config_manager.config))
        self.enable_audio_stream_index_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_audio_stream_index", "audio_stream_index" in self.config_manager.config and self.config_manager.config["audio_stream_index"] != ""))
        self.enable_threads_var = ctk.BooleanVar(value=self.config_manager.config.get("enable_threads", "threads" in self.config_manager.config and self.config_manager.config["threads"] != ""))


        # --- UI Elements ---
        # Core Options (placed directly in this frame)
        core_options_frame = ctk.CTkFrame(self, fg_color="transparent") # Use a transparent frame to group
        core_options_frame.grid(row=0, column=0, padx=0, pady=0, sticky="ew")
        core_options_frame.grid_columnconfigure(0, weight=1)
        core_options_frame.grid_columnconfigure(1, weight=1)

        win_check = ctk.CTkCheckBox(core_options_frame, text="Use Windows Compatibility Mode (--win)", variable=self.win_mode_var)
        win_check.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        Tooltip(win_check, "(From README) Use Windows-compatible multi-step processing (try this if you encounter errors on Windows, especially command-line length errors)")

        alass_check = ctk.CTkCheckBox(core_options_frame, text="Synchronize Subtitles (--alass, requires alass)", variable=self.alass_mode_var)
        alass_check.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        Tooltip(alass_check, "(From README) Attempt to synchronize subtitles with video using alass before cleaning (requires alass in PATH)")


        # Advanced Options (Tab View)
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=1, column=0, padx=5, pady=5, sticky="nsew") # Tabview expands within this frame

        self.tab_view.add("Settings")
        self.tab_view.add("Subtitles")
        self.tab_view.add("Swears/Pad")
        self.tab_view.add("Output Formats")
        self.tab_view.add("Encoding/Audio")
        self.tab_view.add("Chapters") # New Tab

        # --- Populate Tabs ---
        self._create_settings_tab(self.tab_view.tab("Settings"))
        self._create_subtitles_tab(self.tab_view.tab("Subtitles"))
        self._create_swears_pad_tab(self.tab_view.tab("Swears/Pad"))
        self._create_formats_tab(self.tab_view.tab("Output Formats"))
        self._create_encoding_audio_tab(self.tab_view.tab("Encoding/Audio"))
        self._create_chapters_tab(self.tab_view.tab("Chapters")) # Create the new tab


    def _create_settings_tab(self, tab):
        """Creates the content for the Settings tab."""
        tab.grid_columnconfigure(1, weight=1) # Allow entry field to expand
        ctk.CTkLabel(tab, text="Default Media Dir:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        default_media_entry = ctk.CTkEntry(tab, textvariable=self.default_media_dir_var, state="readonly")
        default_media_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(tab, text="Browse...", command=self.browse_default_media_dir).grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkButton(tab, text="Clear", command=self.clear_default_media_dir).grid(row=0, column=3, padx=5, pady=5)
        Tooltip(default_media_entry, "Set a default directory to start browsing for media files.\nClear to remove the default.")

    def _create_subtitles_tab(self, tab):
        """Creates the content for the Subtitles tab."""
        tab.grid_columnconfigure(1, weight=0) # Label column
        tab.grid_columnconfigure(2, weight=1) # Entry column
        tab.grid_columnconfigure(3, weight=0) # Browse button column

        # --- Embed Subs ---
        embed_check = ctk.CTkCheckBox(tab, text="Embed clean subtitles in output (-e)", variable=self.embed_subs_var)
        embed_check.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="w") # Span checkbox across enable/label/entry
        Tooltip(embed_check, "(From README) embed subtitles in resulting video file")

        # --- Full Subs ---
        full_check = ctk.CTkCheckBox(tab, text="Keep non-profane subtitles in output (-f)", variable=self.full_subs_var)
        full_check.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        Tooltip(full_check, "(From README) include all subtitles in output subtitle file (not just scrubbed)")

        # --- Subs Only ---
        subs_only_check = ctk.CTkCheckBox(tab, text="Only generate clean subtitle file (--subs-only)", variable=self.subs_only_var)
        subs_only_check.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        Tooltip(subs_only_check, "(From README) only operate on subtitles (do not alter audio)")

        # --- Offline ---
        offline_check = ctk.CTkCheckBox(tab, text="Do not download subtitles (--offline)", variable=self.offline_var)
        offline_check.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        Tooltip(offline_check, "(From README) don't attempt to download subtitles")

        # --- Subtitle Language ---
        lang_frame = ctk.CTkFrame(tab, fg_color="transparent")
        lang_frame.grid(row=4, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        lang_frame.grid_columnconfigure(1, weight=0) # Label
        lang_frame.grid_columnconfigure(2, weight=1) # Entry

        lang_enable_cb = ctk.CTkCheckBox(lang_frame, text="", variable=self.enable_subtitle_lang_var, width=20)
        lang_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(lang_frame, text="Subtitle Language (-l):").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        lang_entry = ctk.CTkEntry(lang_frame, textvariable=self.subtitle_lang_var)
        lang_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        Tooltip(lang_entry, "(From README) language for extracting srt from video file or srt download (default is \"eng\")")
        # Add command to toggle entry state
        lang_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_subtitle_lang_var, lang_entry))
        # Initial state update
        self._toggle_widget_state(self.enable_subtitle_lang_var, lang_entry)


    def _create_swears_pad_tab(self, tab):
        """Creates the content for the Swears/Pad tab."""
        tab.grid_columnconfigure(1, weight=0) # Label column
        tab.grid_columnconfigure(2, weight=1) # Entry column
        tab.grid_columnconfigure(3, weight=0) # Browse button column

        # --- Swears File ---
        swears_frame = ctk.CTkFrame(tab, fg_color="transparent")
        swears_frame.grid(row=0, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        swears_frame.grid_columnconfigure(1, weight=0) # Label
        swears_frame.grid_columnconfigure(2, weight=1) # Entry
        swears_frame.grid_columnconfigure(3, weight=0) # Button

        swears_enable_cb = ctk.CTkCheckBox(swears_frame, text="", variable=self.enable_swears_file_var, width=20)
        swears_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(swears_frame, text="Swears File (-w):").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        swears_entry = ctk.CTkEntry(swears_frame, textvariable=self.swears_file_var, state="readonly") # Keep readonly for browse
        swears_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        swears_browse_btn = ctk.CTkButton(swears_frame, text="Browse...", command=self.browse_swears)
        swears_browse_btn.grid(row=0, column=3, padx=5, pady=5)
        Tooltip(swears_entry, "(From README) text file containing profanity (with optional mapping)")
        # Add command to toggle entry state (readonly doesn't visually change much, but disable button)
        swears_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_swears_file_var, swears_browse_btn))
        # Initial state update
        self._toggle_widget_state(self.enable_swears_file_var, swears_browse_btn)


        # --- Padding ---
        pad_outer_frame = ctk.CTkFrame(tab, fg_color="transparent")
        pad_outer_frame.grid(row=1, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        pad_outer_frame.grid_columnconfigure(1, weight=0) # Label
        pad_outer_frame.grid_columnconfigure(2, weight=0) # Entry Frame

        pad_enable_cb = ctk.CTkCheckBox(pad_outer_frame, text="", variable=self.enable_padding_var, width=20)
        pad_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(pad_outer_frame, text="Padding (-p):").grid(row=0, column=1, padx=5, pady=5, sticky="w")

        pad_entry_frame = ctk.CTkFrame(pad_outer_frame, fg_color="transparent") # Frame to keep entry and label together
        pad_entry_frame.grid(row=0, column=2, padx=0, pady=5, sticky="w") # Use column 2, sticky w
        pad_entry = ctk.CTkEntry(pad_entry_frame, textvariable=self.padding_var, width=60)
        pad_entry.pack(side=tk.LEFT, padx=(5,0))
        ctk.CTkLabel(pad_entry_frame, text="seconds").pack(side=tk.LEFT, padx=(2,5))
        Tooltip(pad_entry, "(From README) pad (seconds) around profanity")
        # Add command to toggle entry state
        pad_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_padding_var, pad_entry))
        # Initial state update
        self._toggle_widget_state(self.enable_padding_var, pad_entry)


    def _create_formats_tab(self, tab):
        """Creates the content for the Output Formats tab."""
        tab.grid_columnconfigure(1, weight=1) # Allow entry fields to expand
        edl_check = ctk.CTkCheckBox(tab, text="Generate MPlayer EDL file (--edl)", variable=self.edl_var)
        edl_check.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        Tooltip(edl_check, "(From README) generate MPlayer EDL file with mute actions (also implies --subs-only)")
        json_check = ctk.CTkCheckBox(tab, text="Generate JSON debug file (--json)", variable=self.json_var)
        json_check.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        Tooltip(json_check, "(From README) generate JSON file with muted subtitles and their contents")
        ctk.CTkLabel(tab, text="Clean Subtitle Output (--subs-output):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        subs_out_entry = ctk.CTkEntry(tab, textvariable=self.subs_output_var, state="readonly")
        subs_out_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(tab, text="Browse...", command=self.browse_subs_output).grid(row=2, column=2, padx=5, pady=5)
        Tooltip(subs_out_entry, "(From README) output subtitle file")
        ctk.CTkLabel(tab, text="PlexAutoSkip JSON (--plex-auto-skip-json):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        plex_json_entry = ctk.CTkEntry(tab, textvariable=self.plex_json_var, state="readonly")
        plex_json_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(tab, text="Browse...", command=self.browse_plex_json).grid(row=3, column=2, padx=5, pady=5)
        Tooltip(plex_json_entry, "(From README) custom JSON file for PlexAutoSkip (also implies --subs-only)")
        ctk.CTkLabel(tab, text="PlexAutoSkip ID (--plex-auto-skip-id):").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        plex_id_entry = ctk.CTkEntry(tab, textvariable=self.plex_id_var)
        plex_id_entry.grid(row=4, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        Tooltip(plex_id_entry, "(From README) content identifier for PlexAutoSkip (also implies --subs-only)")


    def _create_encoding_audio_tab(self, tab):
        """Creates the content for the Encoding/Audio tab."""
        tab.grid_columnconfigure(1, weight=0) # Label column
        tab.grid_columnconfigure(2, weight=1) # Entry column
        tab.grid_columnconfigure(3, weight=0) # Button column

        # --- Re-encode Video ---
        re_vid_check = ctk.CTkCheckBox(tab, text="Re-encode Video (--re-encode-video)", variable=self.re_encode_video_var)
        re_vid_check.grid(row=0, column=0, columnspan=4, padx=5, pady=5, sticky="w")
        Tooltip(re_vid_check, "(From README) Re-encode video")

        # --- Re-encode Audio ---
        re_aud_check = ctk.CTkCheckBox(tab, text="Re-encode Audio (--re-encode-audio)", variable=self.re_encode_audio_var)
        re_aud_check.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky="w")
        Tooltip(re_aud_check, "(From README) Re-encode audio")

        # --- Burn Subs ---
        burn_check = ctk.CTkCheckBox(tab, text="Burn Subtitles into Video (-b)", variable=self.burn_subs_var)
        burn_check.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky="w")
        Tooltip(burn_check, "(From README) Hard-coded subtitles (implies re-encode)")

        # --- Downmix ---
        downmix_check = ctk.CTkCheckBox(tab, text="Downmix Audio to Stereo (-d)", variable=self.downmix_var)
        downmix_check.grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky="w")
        Tooltip(downmix_check, "(From README) Downmix to stereo (if not already stereo)")

        # --- Video Params ---
        vparams_frame = ctk.CTkFrame(tab, fg_color="transparent")
        vparams_frame.grid(row=4, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        vparams_frame.grid_columnconfigure(1, weight=0) # Label
        vparams_frame.grid_columnconfigure(2, weight=1) # Entry

        vparams_enable_cb = ctk.CTkCheckBox(vparams_frame, text="", variable=self.enable_video_params_var, width=20)
        vparams_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(vparams_frame, text="Video Params (-v):").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        vparams_entry = ctk.CTkEntry(vparams_frame, textvariable=self.video_params_var)
        vparams_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        Tooltip(vparams_entry, "(From README) Video parameters for ffmpeg (only if re-encoding)")
        vparams_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_video_params_var, vparams_entry))
        self._toggle_widget_state(self.enable_video_params_var, vparams_entry)

        # --- Audio Params ---
        aparams_frame = ctk.CTkFrame(tab, fg_color="transparent")
        aparams_frame.grid(row=5, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        aparams_frame.grid_columnconfigure(1, weight=0) # Label
        aparams_frame.grid_columnconfigure(2, weight=1) # Entry

        aparams_enable_cb = ctk.CTkCheckBox(aparams_frame, text="", variable=self.enable_audio_params_var, width=20)
        aparams_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(aparams_frame, text="Audio Params (-a):").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        aparams_entry = ctk.CTkEntry(aparams_frame, textvariable=self.audio_params_var)
        aparams_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        Tooltip(aparams_entry, "(From README) Audio parameters for ffmpeg")
        aparams_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_audio_params_var, aparams_entry))
        self._toggle_widget_state(self.enable_audio_params_var, aparams_entry)

        # --- Audio Stream Index ---
        idx_frame = ctk.CTkFrame(tab, fg_color="transparent")
        idx_frame.grid(row=6, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        idx_frame.grid_columnconfigure(1, weight=0) # Label
        idx_frame.grid_columnconfigure(2, weight=0) # Entry
        idx_frame.grid_columnconfigure(3, weight=0) # Button

        idx_enable_cb = ctk.CTkCheckBox(idx_frame, text="", variable=self.enable_audio_stream_index_var, width=20)
        idx_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(idx_frame, text="Audio Stream Index (--audio-stream-index):").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        idx_entry = ctk.CTkEntry(idx_frame, textvariable=self.audio_stream_index_var, width=60)
        idx_entry.grid(row=0, column=2, padx=5, pady=5, sticky="w")
        Tooltip(idx_entry, "(From README) Index of audio stream to process")
        list_streams_btn = ctk.CTkButton(idx_frame, text="List Streams", command=self.list_audio_streams)
        list_streams_btn.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        Tooltip(list_streams_btn, "(From README) Show list of audio streams (to get index for --audio-stream-index)")
        idx_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_audio_stream_index_var, [idx_entry, list_streams_btn]))
        self._toggle_widget_state(self.enable_audio_stream_index_var, [idx_entry, list_streams_btn])

        # --- FFmpeg Threads ---
        threads_frame = ctk.CTkFrame(tab, fg_color="transparent")
        threads_frame.grid(row=7, column=0, columnspan=4, padx=0, pady=0, sticky="ew")
        threads_frame.grid_columnconfigure(1, weight=0) # Label
        threads_frame.grid_columnconfigure(2, weight=0) # Entry

        threads_enable_cb = ctk.CTkCheckBox(threads_frame, text="", variable=self.enable_threads_var, width=20)
        threads_enable_cb.grid(row=0, column=0, padx=(5,0), pady=5, sticky="w")
        ctk.CTkLabel(threads_frame, text="FFmpeg Threads (--threads):").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        threads_entry = ctk.CTkEntry(threads_frame, textvariable=self.threads_var, width=60)
        threads_entry.grid(row=0, column=2, padx=5, pady=5, sticky="w")
        Tooltip(threads_entry, "(From README) ffmpeg -threads value (for both global options and encoding)")
        threads_enable_cb.configure(command=lambda: self._toggle_widget_state(self.enable_threads_var, threads_entry))
        self._toggle_widget_state(self.enable_threads_var, threads_entry)

    def _create_chapters_tab(self, tab):
        """Creates the content for the Chapters tab."""
        tab.grid_columnconfigure(0, weight=1) # Allow checkbox to expand

        self.chapter_markers_checkbox = ctk.CTkCheckBox(
            tab, # Checkboxes frame is not used here, directly in tab
            text="Add Chapter Markers at Mute Points (--chapter)",
            variable=self.chapter_markers_var
        )
        self.chapter_markers_checkbox.grid(row=0, column=0, padx=10, pady=(10, 10), sticky="w")
        Tooltip(self.chapter_markers_checkbox, "(From README) Create chapter markers for muted segments in the video metadata.")


    def _toggle_widget_state(self, enable_var, widgets):
        """Enables or disables a widget or list of widgets based on a BooleanVar."""
        state = tk.NORMAL if enable_var.get() else tk.DISABLED
        if not isinstance(widgets, list):
            widgets = [widgets]
        for widget in widgets:
            # Special handling for readonly Entry, keep it readonly but change visual state
            if isinstance(widget, ctk.CTkEntry) and widget.cget("state") == "readonly":
                 widget.configure(fg_color=widget.cget("fg_color")[:2] if state == tk.NORMAL else ("gray70", "gray30")) # Adjust colors
            else:
                 widget.configure(state=state)


    def get_state(self):
        """Returns a dictionary containing the current state of options variables."""
        state = {
            "win_mode": self.win_mode_var.get(),
            "alass_mode": self.alass_mode_var.get(),
            "swears_file": self.swears_file_var.get(),
            "default_media_dir": self.default_media_dir_var.get(),
            "subtitle_lang": self.subtitle_lang_var.get(),
            "padding": self.padding_var.get(),
            "embed_subs": self.embed_subs_var.get(),
            "full_subs": self.full_subs_var.get(),
            "subs_only": self.subs_only_var.get(),
            "offline": self.offline_var.get(),
            "edl": self.edl_var.get(),
            "json": self.json_var.get(),
            "plex_json": self.plex_json_var.get(),
            "plex_id": self.plex_id_var.get(),
            "subs_output": self.subs_output_var.get(),
            "re_encode_video": self.re_encode_video_var.get(),
            "re_encode_audio": self.re_encode_audio_var.get(),
            "burn_subs": self.burn_subs_var.get(),
            "downmix": self.downmix_var.get(),
            "video_params": self.video_params_var.get(),
            "audio_params": self.audio_params_var.get(),
            "audio_stream_index": self.audio_stream_index_var.get(),
            "threads": self.threads_var.get(),
            "chapter_markers": self.chapter_markers_var.get(),
            # Add enable states
            "enable_swears_file": self.enable_swears_file_var.get(),
            "enable_subtitle_lang": self.enable_subtitle_lang_var.get(),
            "enable_padding": self.enable_padding_var.get(),
            "enable_video_params": self.enable_video_params_var.get(),
            "enable_audio_params": self.enable_audio_params_var.get(),
            "enable_audio_stream_index": self.enable_audio_stream_index_var.get(),
            "enable_threads": self.enable_threads_var.get(),
            # last_dirs are updated directly in config_manager.config by browse methods
        }
        return state


    def get_initial_dir(self, dir_type):
        """Gets the initial directory for file dialogs based on config."""
        default_dir = self.config_manager.config.get("default_media_dir", "")
        # Use default media dir if set and valid for relevant types
        if default_dir and os.path.isdir(default_dir) and dir_type in ["video", "subs", "output", "swears"]:
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


    def browse_swears(self):
        """Opens a file dialog to select the swears file."""
        initial_dir = self.get_initial_dir("swears")
        filepath = filedialog.askopenfilename(
            title="Select Swears File",
            initialdir=initial_dir,
            filetypes=(("Text Files", "*.txt"), ("All Files", "*.*"))
        )
        if filepath:
            self.swears_file_var.set(filepath)
            self.update_last_dir("swears", filepath)
            self.log_to_console(f"Selected swears file: {filepath}\n")


    def browse_default_media_dir(self):
        """Opens a directory dialog to set the default media directory."""
        # Start browsing from current setting or home
        current_default = self.default_media_dir_var.get()
        initial_dir = current_default if current_default and os.path.isdir(current_default) else str(Path.home())
        dirpath = filedialog.askdirectory(
            title="Select Default Media Directory",
            initialdir=initial_dir
        )
        if dirpath:
            self.default_media_dir_var.set(dirpath)
            # No need to update last_dir here, as this is the default setting itself
            self.log_to_console(f"Set default media directory: {dirpath}\n")


    def clear_default_media_dir(self):
        """Clears the default media directory setting."""
        self.default_media_dir_var.set("")
        self.log_to_console("Cleared default media directory.\n")


    def browse_subs_output(self):
        """Opens a save file dialog for the clean subtitle output file."""
        # This method should ideally be in InputOutputFrame, but placed here for now
        # as the variable is defined here. This highlights a potential need for shared state
        # or methods between frames. For now, we'll keep it here and access input_video_var
        # via the action_output_frame's reference to input_output_frame.
        if not self.action_output_frame or not hasattr(self.action_output_frame, 'input_output_frame'):
             self.log_to_console("Error: Cannot browse subs output, reference to input frame missing.\n")
             messagebox.showerror("Internal Error", "Cannot access input video path for subtitle output.")
             return

        input_video = self.action_output_frame.input_output_frame.input_video_var.get()

        initial_dir = self.get_initial_dir("output") # Use output dir logic
        # Suggest filename based on input video if possible
        suggested_name = ""
        if input_video:
            suggested_name = f"{Path(input_video).stem}_clean.srt"

        filepath = filedialog.asksaveasfilename(
            title="Save Clean Subtitle File As",
            initialdir=initial_dir,
            initialfile=suggested_name,
            defaultextension=".srt",
            filetypes=(("SRT Subtitles", "*.srt"), ("All Files", "*.*"))
        )
        if filepath:
            self.subs_output_var.set(filepath)
            self.update_last_dir("output", filepath) # Update last output dir
            self.log_to_console(f"Selected clean subtitle output: {filepath}\n")


    def browse_plex_json(self):
        """Opens a save file dialog for the PlexAutoSkip JSON file."""
        # Similar to browse_subs_output, accessing input_video_var via references
        if not self.action_output_frame or not hasattr(self.action_output_frame, 'input_output_frame'):
             self.log_to_console("Error: Cannot browse plex json, reference to input frame missing.\n")
             messagebox.showerror("Internal Error", "Cannot access input video path for Plex JSON output.")
             return

        input_video = self.action_output_frame.input_output_frame.input_video_var.get()

        initial_dir = self.get_initial_dir("output") # Use output dir logic
        # Suggest filename based on input video if possible
        suggested_name = ""
        if input_video:
            suggested_name = f"{Path(input_video).stem}_PlexAutoSkip.json"

        filepath = filedialog.asksaveasfilename(
            title="Save PlexAutoSkip JSON As",
            initialdir=initial_dir,
            initialfile=suggested_name,
            defaultextension=".json",
            filetypes=(("JSON Files", "*.json"), ("All Files", "*.*"))
        )
        if filepath:
            self.plex_json_var.set(filepath)
            self.update_last_dir("output", filepath) # Update last output dir
            self.log_to_console(f"Selected PlexAutoSkip JSON output: {filepath}\n")


    def list_audio_streams(self):
        """Triggers the listing of audio streams via the action_output_frame."""
        if self.action_output_frame:
            # Need the input video path from the InputOutputFrame
            if not hasattr(self.action_output_frame, 'input_output_frame'):
                 self.log_to_console("Error: Cannot list streams, reference to input frame missing.\n")
                 messagebox.showerror("Internal Error", "Cannot access input video path to list streams.")
                 return

            input_video = self.action_output_frame.input_output_frame.input_video_var.get()
            self.action_output_frame.list_audio_streams_and_output(input_video)
        else:
            self.log_to_console("Error: ActionOutputFrame not linked to OptionsFrame.\n")
            messagebox.showerror("Internal Error", "Action output frame not available.")

    def log_to_console(self, message):
        """Logs a message to the output console via the action_output_frame."""
        if self.action_output_frame:
            self.action_output_frame.log_output(message)
        else:
            print(f"LOG (OptionsFrame): {message}", end='') # Fallback print


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
        "cleanvidgui_input_output.py", # Need a dummy for the reference
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
                     f.write("    def list_audio_streams_and_output(self, video_path): print(f'DUMMY LIST STREAMS for {video_path}')\n")
                elif "input_output" in fname:
                     f.write("class InputOutputFrame(ctk.CTkFrame): def __init__(self, master, **kwargs): super().__init__(master, **kwargs); self.input_video_var = ctk.StringVar(value='dummy_video.mp4'); ctk.CTkLabel(self, text='InputOutputFrame Placeholder').pack()\n")
                     f.write("    def log_to_console(self, msg): print(f'DUMMY LOG (Input): {msg}', end='')\n")


    # Now import the dummy/real modules
    from .cleanvidgui_config import ConfigManager
    from .cleanvidgui_action_output import ActionOutputFrame # Import dummy/real
    from .cleanvidgui_input_output import InputOutputFrame # Import dummy/real

    root = ctk.CTk()
    root.title("OptionsFrame Demo")
    root.geometry("800x600") # Adjust size for this frame

    config_manager = ConfigManager()
    # Create dummy frames for the references
    dummy_action_output = ActionOutputFrame(root)
    dummy_input_output = InputOutputFrame(root)
    # Manually set the references on the dummy action frame for testing list_streams
    dummy_action_output.input_output_frame = dummy_input_output


    options_frame = OptionsFrame(root, config_manager=config_manager, action_output_frame=dummy_action_output)
    options_frame.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()