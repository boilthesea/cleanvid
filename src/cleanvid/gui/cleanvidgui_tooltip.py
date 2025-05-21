import tkinter as tk
import customtkinter as ctk # Import customtkinter for potential future use or consistency
import sys # Import sys for platform check if needed

class Tooltip:
    """
    Basic tooltip implementation for customtkinter widgets.
    Displays a text tooltip when the mouse hovers over a widget.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self._after_id = None # To store the after() id
        self.widget.bind("<Enter>", self.schedule_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<ButtonPress>", self.hide_tooltip) # Hide on click

    def schedule_tooltip(self, event=None):
        """Schedules the tooltip to be shown after a delay."""
        # Cancel any previous hide schedule
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        # Schedule to show after a delay (e.g., 500ms)
        self._after_id = self.widget.after(500, self.show_tooltip)

    def show_tooltip(self):
        """Displays the tooltip window."""
        # Check if mouse is still over the widget before showing
        if self.widget.winfo_containing(self.widget.winfo_pointerx(), self.widget.winfo_pointery()) != self.widget:
            self.hide_tooltip() # Hide if mouse moved away during delay
            return

        if self.tooltip_window or not self.text:
            return

        # Calculate position relative to the widget
        # Position the tooltip slightly below and centered horizontally on the widget
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5 # 5 pixels below the widget

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True) # No window decorations
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        # Make it appear on top
        self.tooltip_window.wm_attributes("-topmost", True)

        label = tk.Label(self.tooltip_window, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         wraplength=350, # Wrap long tooltips after 350 pixels
                         font=("tahoma", "8", "normal")) # Use a common font
        label.pack(ipadx=2, ipady=2) # Add some internal padding

    def hide_tooltip(self, event=None):
        """Hides the tooltip window and cancels any pending show schedule."""
        # Cancel any pending show schedule
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        # Destroy the tooltip window if it exists
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# Example Usage (for testing purposes, can be removed later)
if __name__ == "__main__":
    root = ctk.CTk()
    root.title("Tooltip Demo")
    root.geometry("300x200")

    button = ctk.CTkButton(root, text="Hover for Tooltip")
    button.pack(pady=50)

    tooltip_text = "This is a sample tooltip.\nIt provides helpful information\nabout the button."
    button_tooltip = Tooltip(button, tooltip_text)

    label = ctk.CTkLabel(root, text="Another Widget")
    label.pack(pady=10)
    label_tooltip = Tooltip(label, "Tooltip for the label.")

    root.mainloop()