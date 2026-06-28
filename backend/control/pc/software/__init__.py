# control/pc/software/__init__.py
from .browser import open_url, search_google, click_element, fill_field, get_page_text, browser_screenshot, get_page_info, close_browser
from .files import list_directory, create_file, create_folder, read_file, write_file, rename, move, copy, delete, search_files, open_file, open_in_explorer, get_file_info
from .notify import send_notification, get_notification_history, clear_notification_history
from .window import close_window, minimize_window, maximize_window, focus_window, list_open_windows, snap_window, take_screenshot
from .input import move_mouse, click, double_click, right_click, scroll, type_text, press_key, hotkey
from .app import open_app
from .clipboard import clipboard_read, clipboard_write
