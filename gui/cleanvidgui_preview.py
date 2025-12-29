import customtkinter as ctk
import tkinter as tk
import json

class PreviewWindow(ctk.CTkToplevel):
    """
    Window for previewing profanity filter changes and selecting which to apply.
    """
    def __init__(self, master, json_data, on_apply_callback):
        super().__init__(master)
        self.title("CleanVid Preview")
        self.geometry("800x600")
        
        self.json_data = json_data
        self.on_apply_callback = on_apply_callback
        self.items = [] # To store checkbox and item info

        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Content Frame
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(1, weight=1)

        # Header
        ctk.CTkLabel(self.scroll_frame, text="Apply?", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(self.scroll_frame, text="Proposed Changes", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Populate changes
        edits = self.json_data.get("edits", [])
        if not edits:
            ctk.CTkLabel(self.scroll_frame, text="No profanity detected.").grid(row=1, column=1, padx=5, pady=10, sticky="w")
        else:
            for i, edit in enumerate(edits):
                row = i + 1
                var = ctk.BooleanVar(value=True)
                
                check = ctk.CTkCheckBox(self.scroll_frame, text="", variable=var, width=20)
                check.grid(row=row, column=0, padx=5, pady=5)
                
                text_frame = ctk.CTkFrame(self.scroll_frame)
                text_frame.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
                text_frame.grid_columnconfigure(0, weight=1)
                
                original = edit.get("old", "")
                cleaned = edit.get("new", "")
                timestamp = f"{edit.get('start', '')} --> {edit.get('end', '')}"
                
                # We don't have the index directly in the old JSON, but I added it to the new one.
                # If it's missing (legacy), we'll have to rely on order, but my new cleanvid.py provides it.
                # pysrt index is usually sub.index
                # Wait, I should make sure my JSON includes the index.
                # In my previous edit to cleanvid.py:
                # self.jsonDumpList.append({'old': sub.text, 'new': newText, 'start': str(sub.start), 'end': str(sub.end)})
                # I should add 'index': sub.index there.
                
                idx = edit.get("index", row) # Fallback to row if index not provided
                
                ctk.CTkLabel(text_frame, text=f"Index: {idx} | {timestamp}", font=ctk.CTkFont(size=10, slant="italic")).grid(row=0, column=0, sticky="w")
                ctk.CTkLabel(text_frame, text=f"Original: {original}", wraplength=600, justify="left").grid(row=1, column=0, sticky="w")
                ctk.CTkLabel(text_frame, text=f"Cleaned:  {cleaned}", wraplength=600, justify="left", text_color="green").grid(row=2, column=0, sticky="w")
                
                self.items.append({"var": var, "index": idx})

        # Footer Buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=1, column=0, padx=10, pady=10, sticky="e")
        
        apply_btn = ctk.CTkButton(button_frame, text="Apply Selected", command=self.apply)
        apply_btn.pack(side="right", padx=5)
        
        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=self.destroy, fg_color="gray", hover_color="darkgray")
        cancel_btn.pack(side="right", padx=5)

    def apply(self):
        """Collects excluded indices and calls the callback."""
        excluded_indices = [str(item["index"]) for item in self.items if not item["var"].get()]
        self.on_apply_callback(excluded_indices)
        self.destroy()
