import ctypes
from ctypes import wintypes
import json
import os
import sys
import time
import threading

# UI Related Imports
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (QApplication, QLabel, QWidget, QVBoxLayout, QFrame, QDialog, QGridLayout,
                               QPushButton, QHBoxLayout, QSlider, QSpinBox, QCheckBox)
from PySide6.QtCore import Qt, QTimer, QPoint

def get_key_name(vk_code):
    """Converts a virtual key code to a readable string."""
    # Special cases that GetKeyNameText sometimes misses or formats oddly
    special_keys = {
        0x01: "L-Mouse", 0x02: "R-Mouse", 0x04: "M-Mouse",
        0x12: "Alt", 0x11: "Ctrl", 0x10: "Shift",
        0x09: "Tab", 0x0D: "Enter", 0x20: "Space", 0x28: "Down Arrow",
        0x26: "Up Arrow", 0x27: "Right Arrow", 0x25: "Left Arrow",
    }
    if vk_code in special_keys:
        return special_keys[vk_code]

    # Map Virtual Key to Scan Code
    scan_code = user32.MapVirtualKeyW(vk_code, 0)

    # GetKeyNameTextW expects a bitmask:
    # scan_code << 16 | (1 << 24 if extended else 0)
    # We use a buffer to store the resulting string
    buffer = ctypes.create_unicode_buffer(32)
    user32.GetKeyNameTextW(scan_code << 16, buffer, 32)

    return buffer.value if buffer.value else hex(vk_code)

class RebindDialog(QDialog):
    def __init__(self, tracker, parent=None):
        super().__init__(parent)
        self.tracker = tracker

        EXCLUDED_KEYS = ["bg_alpha", "window_x", "window_y", "timer_visibility", "use_images", "Use Grid Layout"]
        NUMERIC_KEYS = ["Passive Timer", "Image Scale", "Font Size"]
        NUMERIC_UI_KEYS = ["Image Scale", "Font Size"]

        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Settings")
        self.setStyleSheet("background-color: #2D2D30; color: white;")
        self.setMinimumSize(300, 450)

        self.layout = QGridLayout(self)
        self.buttons = {}

        row = 0

        # 1. Add Timer Toggles Section
        self.layout.addWidget(QLabel("<b>Active Timers</b>"), row, 0, 1, 2)
        row += 1
        for timer_name in self.tracker.counts.keys():
            check = QCheckBox(f"Show {timer_name}")
            check.setChecked(self.tracker.timer_visibility.get(timer_name, True))
            # Updates UI in real-time
            check.stateChanged.connect(lambda state, tn=timer_name: self.toggle_timer(tn, state, parent))
            self.layout.addWidget(check, row, 0, 1, 2)
            row += 1

        # 2. Map Keybind Buttons
        for key_name, val in self.tracker.keybinds.items():
            if key_name in EXCLUDED_KEYS:
                continue

            label = QLabel(key_name)
            self.layout.addWidget(label, row, 0)

            if key_name in NUMERIC_KEYS:
                # Create a number input box
                spin = QSpinBox()
                spin.setRange(1, 999)
                spin.setValue(int(val))

                spin.setButtonSymbols(QSpinBox.NoButtons)
                spin.setStyleSheet("""
                                QSpinBox {
                                    background-color: #444;
                                    color: white;
                                    border: 1px solid #5C5470;
                                    border-radius: 3px;
                                    padding: 2px;
                                }
                            """)

                if key_name in NUMERIC_UI_KEYS:
                    spin.valueChanged.connect(lambda v, kn=key_name: self.update_numeric_setting(kn, v, parent))
                else:
                    spin.valueChanged.connect(lambda v, kn=key_name: self.update_numeric_setting(kn, v, None))
                self.layout.addWidget(spin, row, 1)
            else:
                btn = QPushButton(get_key_name(val))
                btn.clicked.connect(lambda checked, kn=key_name: self.request_rebind(kn))
                self.layout.addWidget(btn, row, 1)
                self.buttons[key_name] = btn

            row += 1

        # 3. Add Horizontal Line Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #5C5470;")
        self.layout.addWidget(line, row, 0, 1, 2)
        row += 1

        # 4. Add Transparency Slider
        self.layout.addWidget(QLabel("Background Opacity"), row, 0)
        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setMinimum(0)
        self.alpha_slider.setMaximum(255)
        self.alpha_slider.setValue(self.tracker.keybinds.get("bg_alpha", 200))

        # Connect to the parent (OverlayUI) method
        if parent and hasattr(parent, "update_transparency"):
            self.alpha_slider.valueChanged.connect(parent.update_transparency)

        self.layout.addWidget(self.alpha_slider, row, 1)
        row += 1

        # Checkbox for Image Toggle
        image_check = QCheckBox(f"Show Images")
        image_check.setChecked(self.tracker.use_images)

        # Grid Layout
        grid_check = QCheckBox("Use Compact Layout (2 Columns)")
        grid_check.setChecked(self.tracker.use_grid_layout)
        grid_check.stateChanged.connect(lambda state: self.toggle_layout(state, parent))
        self.layout.addWidget(grid_check, row, 0, 1, 2)
        row += 1

        # Connect to a new method that updates UI in real-time
        image_check.stateChanged.connect(lambda state: self.toggle_images(state, parent))
        self.layout.addWidget(image_check, row, 0)

    def request_rebind(self, key_name):
        self.buttons[key_name].setText("...")
        self.tracker.start_capture(key_name)
        QTimer.singleShot(100, lambda: self.wait_for_finish(key_name))

    def update_numeric_setting(self, key_name, value, overlay):
        self.tracker.keybinds[key_name] = value
        if key_name == "Image Scale":
            self.tracker.image_scale = value
        elif key_name == "Font Size":
            self.tracker.font_size = value
        self.tracker.save_config()
        if self.tracker.debug:
            print(f"Updated {key_name} to {value}")
        if overlay:
            overlay.rebuild_labels()

    def toggle_timer(self, name, state, overlay):
        is_visible = (state == Qt.Checked.value)
        self.tracker.timer_visibility[name] = is_visible
        self.tracker.save_config()

        if overlay:
            overlay.labels.clear()
            overlay.rebuild_labels()

    def toggle_images(self, state, overlay):
        is_visible = (state == Qt.Checked.value)
        self.tracker.use_images = is_visible
        self.tracker.save_config()

        if overlay:
            overlay.rebuild_labels()

    def toggle_layout(self, state, overlay):
        self.tracker.use_grid_layout = (state == Qt.Checked.value)
        self.tracker.save_config()
        if overlay:
            overlay.rebuild_labels()

    def wait_for_finish(self, key_name):
        if self.tracker.capturing_for is None:
            new_val = self.tracker.keybinds[key_name]
            self.buttons[key_name].setText(get_key_name(new_val))
        else:
            QTimer.singleShot(100, lambda: self.wait_for_finish(key_name))

class OverlayUI(QWidget):
    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.old_pos = None
        self.labels = {}

        # Window Setup
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.move(self.tracker.keybinds.get("window_x", 100),
                  self.tracker.keybinds.get("window_y", 100))

        # Main Container
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("MainContainer")
        self.main_frame.setStyleSheet("""
                    QFrame#MainContainer {
                        background-color: rgba(30, 30, 35, 200);
                        border: none;
                        border-radius: 10px;
                        padding: 5px;
                    }
                """)
        self.layout = QGridLayout(self.main_frame)

        # --- Header Row (Settings Icon Only) ---
        header = QHBoxLayout()
        header.addStretch()
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(25, 25)
        self.settings_btn.setStyleSheet("background: #444; border-radius: 5px; color: white;")
        self.settings_btn.clicked.connect(self.open_settings)
        header.addWidget(self.settings_btn)

        # --- Close Button ---
        self.close_btn = QPushButton("✕")  # Multiplication X looks cleaner than 'X'
        self.close_btn.setFixedSize(25, 25)
        self.close_btn.setStyleSheet("""
                    QPushButton {
                        background: #444; 
                        border-radius: 5px; 
                        color: white;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #cc3333;
                    }
                """)
        self.close_btn.clicked.connect(QApplication.instance().quit)
        header.addWidget(self.close_btn)

        # --- Add Buttons to Header ---
        # Use: layout.addLayout(sub_layout, row, column, rowSpan, columnSpan)
        self.layout.addLayout(header, 0, 0, 1, 2)

        # --- Labels ---
        self.rebuild_labels()

        # Root Layout
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.main_frame)

        # Initialize background alpha immediately
        self.update_transparency(self.tracker.keybinds.get("bg_alpha", 200))

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.refresh_ui)
        self.ui_timer.start(100)

    # --- Click and Drag ---
    def mousePressEvent(self, event):
        # Only allow dragging if clicking the main window or the background frame
        if event.button() == Qt.LeftButton:
            # Check if the widget under the mouse is the frame or the window itself
            focused_widget = self.childAt(event.position().toPoint())
            if focused_widget in [self, self.main_frame] or isinstance(focused_widget, QLabel):
                self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
            new_x = self.x() + delta.x()
            new_y = self.y() + delta.y()
            self.move(new_x, new_y)
            self.old_pos = event.globalPosition().toPoint()

            # Update tracker and save to file
            self.tracker.keybinds["window_x"] = new_x
            self.tracker.keybinds["window_y"] = new_y
            self.tracker.save_config()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    # --- UI Logic with Dynamic Resizing ---
    def refresh_ui(self):
        for key, value in self.tracker.counts.items():
            if key in self.labels:
                lbl = self.labels[key]
                # Check if we are currently in image mode for this specific key
                is_image_mode = self.tracker.use_images and self.tracker.timer_images.get(key)

                if value > 0:
                    # Image Mode: "26s" | Text Mode: "Night Parade: 26s"
                    txt = f"{value}s" if is_image_mode else f"{key}: {value}s"
                    lbl.setText(txt)
                    lbl.setStyleSheet("color: #FF7676; background: transparent;")
                else:
                    # Image Mode: "READY" | Text Mode: "Night Parade: READY"
                    txt = "READY" if is_image_mode else f"{key}: READY"
                    lbl.setText(txt)
                    lbl.setStyleSheet("color: #76FF76; background: transparent;")

        self.adjustSize()

    # Sub window for rebinding
    def open_settings(self):
        # Attach the dialog to "self" so it doesn't get garbage collected
        self.dialog = RebindDialog(self.tracker, self)
        self.dialog.show()
        if self.tracker.debug:
            print("Settings window opened.")

    def update_transparency(self, value):
        self.main_frame.setStyleSheet(f"""
            QFrame#MainContainer {{
                background-color: rgba(30, 30, 35, {value});
                border: none;
                border-radius: 10px;
                padding: 5px;
            }}

            /* This targets only the labels inside the main container */
            QFrame#MainContainer QLabel {{
                border: 2px solid #5C5470;
                border-radius: 10px;
                padding: 5px;
                background: transparent;
            }}
        """)
        self.tracker.keybinds["bg_alpha"] = value
        self.tracker.save_config()

    def rebuild_labels(self):
        # 1. Clear everything from the grid EXCEPT the header (Row 0)
        # We iterate backwards to safely remove items without shifting indices
        for i in reversed(range(self.layout.count())):
            # getItemPosition returns (row, column, rowSpan, columnSpan)
            pos = self.layout.getItemPosition(i)
            if pos[0] > 0:  # If row is greater than 0, it's a timer row
                item = self.layout.takeAt(i)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self.labels.clear()

        # 2. Starting position for the first timer
        current_row = 1
        current_col = 0

        # 3. Get scaling factor
        scale = self.tracker.image_scale if self.tracker.image_scale else 25

        for key in self.tracker.counts:
            # Check if this specific timer is toggled "ON" in settings
            if self.tracker.timer_visibility.get(key, True):
                container = QWidget()
                row_layout = QHBoxLayout(container)
                row_layout.setContentsMargins(2, 2, 2, 2)
                row_layout.setSpacing(10)

                # --- Icon Logic ---
                show_img = self.tracker.use_images and self.tracker.timer_images.get(key)
                if show_img and os.path.exists(self.tracker.timer_images[key]):
                    icon_lbl = QLabel()
                    pixmap = QPixmap(self.tracker.timer_images[key])
                    icon_lbl.setPixmap(pixmap.scaled(scale, scale, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    icon_lbl.setStyleSheet("border: none; background: transparent;")
                    row_layout.addWidget(icon_lbl)

                # --- Text Logic ---
                # Remove prefix if image is present
                display_text = "READY" if show_img else f"{key}: READY"

                val_lbl = QLabel(display_text)
                val_lbl.setFont(QFont("Segoe UI", self.tracker.font_size, QFont.Bold))
                val_lbl.setStyleSheet("color: #76FF76; background: transparent; border: none;")

                row_layout.addWidget(val_lbl)

                # Store the label reference for refresh_ui updates
                self.labels[key] = val_lbl

                # --- Grid Placement Logic ---
                self.layout.addWidget(container, current_row, current_col)

                if self.tracker.use_grid_layout:
                    # Compact mode: Move to next column, or next row if full
                    current_col += 1
                    if current_col > 1:
                        current_col = 0
                        current_row += 1
                else:
                    # Original mode: Always move to the next row
                    current_row += 1
                    current_col = 0

        # Force the window to shrink/grow to fit the new layout
        self.adjustSize()

# --- 64-bit Pointer Definitions ---
LRESULT = ctypes.c_longlong
WPARAM = wintypes.WPARAM
LPARAM = ctypes.c_longlong

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- Main Tracker Class ---
class MightyMiner:
    def __init__(self, config_path="settings.json"):
        self.debug = False
        self.config_path = config_path
        self.hook = None
        self._proc = None
        self.capturing_for = None  # State for rebinding keys
        self.concertoState = False
        self.awakeningState = False
        # State Variables
        self.isChangeTitlePressed = False
        self.title_Desc = None
        self.change_title_timer = None
        # Cooldown values
        self.counts = {
            "Concerto": 0,
            "Night Parade": 0,
            "The Setting Sun": 0,
            "Fighter": 0,
            "Passive": 0,
        }
        self.timer_images = {
            "Night Parade": "images/np.png",
            "Concerto": "images/concerto.png",
            "The Setting Sun": "images/sun.png",
            "Fighter": "images/fighter.png",
        }
        self.timer_visibility = {k: True for k in self.counts.keys()}
        self.use_images = True
        self.image_scale = 30
        self.font_size = 20
        self.use_grid_layout = False
        # Load binds from JSON
        self.keybinds = self.load_config()

    def load_config(self):
        default_binds = {
            "Change Title": "0x70",
            "Night Parade": "0x31",
            "Reset": "0x52",
            "bg_alpha": 200,
            "window_x": 100,
            "window_y": 100,
            "Passive Timer": 21
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)

                    # 1. Update visibility separately
                    if "timer_visibility" in data:
                        self.timer_visibility.update(data["timer_visibility"])
                    # 2. Check whether to use images
                    if "use_images" in data:
                        self.use_images = data["use_images"]
                    # 3. Check for image scale
                    if "Image Scale" in data:
                        self.image_scale = data["Image Scale"]
                    # 4. Check for font size
                    if "Font Size" in data:
                        self.font_size = data["Font Size"]
                    # 5. Check layout
                    if "Use Grid Layout" in data:
                        self.use_grid_layout = data["Use Grid Layout"]

                    # 3. Extract keybinds without including the nested visibility dict
                    config_binds = {k: v for k, v in data.items() if k != "timer_visibility"}

                    full_data = default_binds.copy()
                    full_data.update(config_binds)

                    return {k: (int(v, 16) if isinstance(v, str) and v.startswith("0x") else v)
                            for k, v in full_data.items()}
            except Exception as e:
                print(f"Config error: {e}")

        return {k: (int(v, 16) if isinstance(v, str) and v.startswith("0x") else v)
                for k, v in default_binds.items()}

    def save_config(self):
        PLAIN_INTS = ["bg_alpha", "window_x", "window_y", "Image Scale", "Passive Timer"]

        save_data = {}
        for k, v in self.keybinds.items():
            if k in PLAIN_INTS:
                save_data[k] = v
            else:
                save_data[k] = hex(v) if isinstance(v, int) else v
        save_data["timer_visibility"] = self.timer_visibility
        save_data["use_images"] = self.use_images
        save_data["Image Scale"] = self.image_scale
        save_data["Font Size"] = self.font_size
        save_data["Use Grid Layout"] = self.use_grid_layout

        with open(self.config_path, "w") as f:
            json.dump(save_data, f, indent=4)

    def reset_change_title_state(self):
        """Equivalent to TimerCallback_ChangeTitle"""
        self.isChangeTitlePressed = False

    def check_binds(self, vk_code):
        if self.debug:
            print(f"Key press detected: {hex(vk_code)}")
        # 1. Handle Change Title (The "Modifier" key)
        if vk_code == self.keybinds.get("Change Title"):
            self.isChangeTitlePressed = True
            # Reset timer: 3 seconds to press the next key
            if self.change_title_timer:
                self.change_title_timer.cancel()
            self.change_title_timer = threading.Timer(3.0, self.reset_change_title_state)
            self.change_title_timer.start()

        # 2. Handle Title Switching (Must be within 3s of Change Title)
        if self.isChangeTitlePressed:
            if vk_code == self.keybinds["Night Parade"]:
                self.title_Desc = "Night Parade"
                self.isChangeTitlePressed = False
            elif vk_code == self.keybinds["Concerto"]:
                self.title_Desc = "Concerto"
                self.isChangeTitlePressed = False
            elif vk_code == self.keybinds["Damage Title"]:
                self.title_Desc = "Damage Title"
                self.isChangeTitlePressed = False
            elif vk_code == self.keybinds["The Setting Sun"]:
                self.title_Desc = "The Setting Sun"
                self.isChangeTitlePressed = False

        # 3. Handle Skill Triggers
        else:
            # Night Parade Skill logic
            if ((vk_code == self.keybinds["NP Skill 1"] or vk_code == self.keybinds["NP Skill 2"])
                    and self.title_Desc == "Night Parade"):
                if self.counts["Night Parade"] <= 0:
                    self.start_timer("Night Parade", 26)

            # Buff items logic
            if vk_code in [self.keybinds["Awakening"],
                             self.keybinds["Onion"],
                             self.keybinds["Superhuman Apple"]]:
                if self.title_Desc == "Concerto" and self.counts["Concerto"] <= 0:
                    self.start_timer("Concerto", 61)
                elif self.title_Desc == "The Setting Sun" and self.counts["The Setting Sun"] <= 0:
                    self.start_timer("The Setting Sun", 30)

            # Fighters
            if vk_code == self.keybinds["Fighter"]:
                self.start_timer("Fighter", 120)

            # Passive Key
            if vk_code == self.keybinds.get("Passive"):  # Match your JSON key name
                if self.counts["Passive"] <= 0:
                    # Pull the duration from the config, fallback to 21 if missing
                    duration = self.keybinds.get("Passive Timer", 21)
                    self.start_timer("Passive", duration)

            # Reset Key
            if vk_code == self.keybinds["Reset"]:
                for key in self.counts:
                    self.counts[key] = 0
                if self.debug:
                    print("All timers reset.")

    def start_capture(self, skill_name):
        """Call this to put the program into "Listen for next key" mode."""
        self.capturing_for = skill_name

    def start_timer(self, name, seconds):
        self.counts[name] = seconds
        if self.debug:
            print(f"[Timer] Started {name} for {seconds}s")

    # Key Logger Logic
    def install(self):
        """Sets the hook and starts the mandatory Windows Message Loop."""
        self._proc = HOOKPROC(self.hook_callback)
        h_module = kernel32.GetModuleHandleW(None)

        self.hook = user32.SetWindowsHookExW(13, self._proc, h_module, 0)
        if not self.hook:
            # Fallback for some environments: pass NULL handle
            self.hook = user32.SetWindowsHookExW(13, self._proc, 0, 0)

        if not self.hook:
            print(f"Critical Error: Could not install hook. Error Code: {ctypes.get_last_error()}")
            return

        if self.debug:
            print("--- MightyMiner Active ---\nListening for game inputs...")

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def hook_callback(self, nCode, wParam, lParam):
        """The core function called by Windows on every keypress."""
        try:
            if nCode == 0 and wParam == 0x0100:  # WM_KEYDOWN
                vk_code = lParam.contents.vkCode

                # Handle Rebinding Mode
                if self.capturing_for:
                    self.keybinds[self.capturing_for] = vk_code
                    self.save_config()
                    if self.debug:
                        print(f"Bound {self.capturing_for} to {hex(vk_code)}")
                    self.capturing_for = None  # This signals the UI to update
                    return 1  # Returns 1 to "consume" the key so the game/tracker doesn't see it

                # Handle Cooldown Triggers
                self.check_binds(vk_code)
        except Exception as e:
            print(f"Callback Error: {e}")

        return user32.CallNextHookEx(self.hook, nCode, wParam, lParam)

# --- Entry Point ---
if __name__ == "__main__":
    # Check Admin
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("ERROR: Run as Administrator")
        sys.exit()

    # 1. Initialize App & Tracker
    app = QApplication(sys.argv)
    tracker = MightyMiner()

    # 2. Background Thread for Keyboard Hook
    # The hook MUST run in its own thread so the UI doesn't freeze
    hook_thread = threading.Thread(target=tracker.install, daemon=True)
    hook_thread.start()

    # 3. Background Thread for Countdown Logic
    def timer_loop():
        while True:
            for key in tracker.counts:
                if tracker.counts[key] > 0:
                    tracker.counts[key] -= 1
            time.sleep(1)

    countdown_thread = threading.Thread(target=timer_loop, daemon=True)
    countdown_thread.start()

    # 4. Show UI
    window = OverlayUI(tracker)
    window.resize(250, 300)
    window.show()

    sys.exit(app.exec())