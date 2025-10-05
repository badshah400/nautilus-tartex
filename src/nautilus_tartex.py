# vim: set ai et ts=4 sw=4 tw=80:
#
# Copyright 2025 Atri Bhattacharya <badshah400@opensuse.org>
# Licensed under the terms of MIT License. See LICENSE.txt for details.

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

# Try to import the Nautilus and GObject libraries.
# If this fails, the script will not be loaded by Nautilus,
# which is the desired behavior for non-GNOME environments.
try:
    import gi  # type: ignore[import-untyped]

    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Nautilus", "4.1")
    gi.require_version("Notify", "0.7")
    from gi.repository import (  # type: ignore[import-untyped]
        Adw,
        GLib,
        GObject,
        Gio,
        Gtk,
        Nautilus,
        Notify,
    )
except ImportError:
    pass

__appname__ = "nautilus-tartex"
__version__ = "0.0.3.dev0"

class TartexNautilusExtension(GObject.GObject, Nautilus.MenuProvider):
    """
    This extension provides a right-click menu item in Nautilus
    for .tex and .fls files to create a tarball using tartex.
    """

    Notify.init("TarTeX")

    def __init__(self):
        os.environ["TERM"] = "dumb"  # suppress rich formatting
        GObject.GObject.__init__(self)

    def get_file_items(self, items):
        """
        Called by Nautilus to get the list of menu items to display for the
        given files.  The 'items' parameter is the list of Nautilus.FileInfo
        objects for the selected files.
        """
        # Single file selection only
        if len(items) != 1:
            return []

        file_obj = items[0]

        # Check the object type by confirming it is not a directory
        if not file_obj.is_directory() and (
            file_obj.get_name().endswith((".tex", ".fls"))
        ):
            top_menu_item = Nautilus.MenuItem(
                name="TartexNautilusExtension::CreateTarball",
                label="Create TarTeX Archive",
                tip="Creates a compressed tarball of the project using tartex.",
            )
            top_menu_item.connect(
                "activate", self.on_tartex_activate, file_obj
            )
            return [top_menu_item]

        return []

    def get_background_items(
        self,
        current_folder: Nautilus.FileInfo,
    ) -> list[Nautilus.MenuItem]:
        return []

    def _run_tartex_process(
        self, file_obj: Nautilus.FileInfo, n: Notify.Notification
    ):
        """
        Runs the blocking tartex process in a separate thread.
        This function handles the synchronous part and sends the final
        notification.
        """
        parent_dir = file_obj.get_parent_location()

        # chdir into proj dir so that tartex output msgs use relative file
        # names w.r.t it
        GLib.chdir(parent_dir.get_path())

        tartex_path = shutil.which("tartex")
        if not tartex_path:
            self._notify_send(
                "Error", "🚨 tartex command not found in PATH", n
            )
            return

        file_path = file_obj.get_location().get_path()
        file_name_stem = os.path.splitext(file_obj.get_name())[0]

        use_git = (Path(parent_dir.get_path()) / ".git").is_dir()

        # Generate a unique filename with a timestamp
        timestamp = datetime.now().strftime(r"%Y%m%d_%H%M%S")
        output_name = GLib.build_filenamev(
            [parent_dir.get_path(), f"{file_name_stem}_{timestamp}.tar.gz"]
        )

        cmd = [tartex_path, file_path, "-b", "-s"]
        if use_git:
            cmd += [
                "--overwrite",
                "--git-rev",
                "--output",
                parent_dir.get_path(),  # specify dir but allow default git tag
            ]
        else:  # use unique time-stamped output tar name
            cmd += ["--output", output_name]

        try:
            tartex_proc = Gio.SubprocessLauncher.new(
                Gio.SubprocessFlags.STDOUT_PIPE |
                Gio.SubprocessFlags.STDERR_PIPE
            )
            process = tartex_proc.spawnv(cmd)
            process.communicate_utf8_async(
                None,  # No stdin
                None,  # Cancellable (None)
                self._on_tartex_complete,  # Gio.AsyncReadyCallback function
                (file_obj, n),  # data to pass to the callback
            )

        except GLib.Error as err:
            GLib.timeout_add(
                0,
                self._notify_send,
                "TarTeX Error",
                f"🚨 Failed to launch command: {err}"
            )

        except Exception as e:
            GLib.timeout_add(
                0,
                self._notify_send,
                "TarTeX Error",
                f"🚫 An unknown error occurred: {e}"
            )

    def _on_tartex_complete(
        self, proc: Gio.Subprocess, res: Gio.AsyncResult, params: tuple
    ):
        """Callback func to run upon tartex completion"""

        file_obj, notif = params
        success, stdout, stderr = proc.communicate_utf8_finish(res)
        exit_code = proc.get_exit_status()

        if exit_code:
            GLib.timeout_add(
                0,
                self._notify_send,
                "TarTeX Error",
                f"🚨 Failed to create archive using {file_obj.get_name()}",
                notif,
            )
            full_error_output = f"Output:\n{stdout}\n"
            if stderr:
                full_error_output += f"\nError log:\n{stderr}\n"
            GLib.timeout_add(
                0,
                self._show_error_dialog,
                file_obj,
                full_error_output,
                exit_code
            )
        else:
            re_summary = re.compile(r"^Summary:\s(.*)$", re.MULTILINE)
            success_match = re_summary.search(stdout)
            if success_match:
                success_msg = success_match.group(0)
                success_msg = re_summary.sub(r"\1", success_msg)
                if success_msg[-1] != ".":  # line wrapped, add next line
                    success_msg = success_msg + f" {stdout.splitlines()[-1]}"
            else:  # bare success_msg, hopefully never reached
                success_msg = (
                    f"Created TarTeX archive using {file_obj.get_name()}"
                )
            GLib.timeout_add(
                0, self._notify_send, "TarTeX Success", success_msg, notif
            )
            output_file = GLib.build_filenamev(
                [
                    file_obj.get_parent_location().get_path(),
                    success_msg.split()[1]
                ]
            )
            GLib.idle_add(
                self._update_recent,
                [file_obj.get_uri(), GLib.filename_to_uri(output_file)]
            )

    def _update_recent(self, files: list[str]):
        """
        Update Gtk.RecentManager with list of uri

        :files: list of uri (list[str])
        """
        rec_man = Gtk.RecentManager.get_default()
        for _f in files:
            if not rec_man.add_item(_f):
                print(f"Error: Failed to add {_f} to recent manager.")

    def on_tartex_activate(self, menu_item, file_obj):
        """
        Method is called when the user clicks the menu item. Sends a
        notification and call the function to run tartex
        """
        notif = Notify.Notification.new(
            "TarTeX",
            "⏳ Archive creation started (running in background)",
        )
        notif.set_urgency(Notify.Urgency.CRITICAL)  # make notif persistent
        notif.show()
        self._run_tartex_process(file_obj, notif)

    def _notify_send(self, head: str, msg: str, n: Notify.Notification):
        """Send notification at end of process one way or another"""
        n.update(head, msg)
        n.set_urgency(Notify.Urgency.NORMAL)  # remove persistence
        n.set_timeout(Notify.EXPIRES_DEFAULT)
        n.show()
        return False

    def _show_error_dialog(
            self, dir_path: str, error_details: str, exit_code: int
    ) -> bool:
        """
        Shows a modal dialog with full error details, using a GTK4 layout.
        """
        # Get the active application instance if possible
        application: Gtk.Application = Gtk.Application.get_default()
        parent_window = None
        if application:
            # Attempt to get the active window (likely the Nautilus window)
            parent_window = application.get_active_window()

        dialog = Adw.Dialog.new()
        dialog.set_title("TarTeX error")
        dialog.set_follows_content_size(True)
        dialog_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
        )
        dialog.set_child(dialog_box)

        box1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog_box.append(box1)

        header_bar = Adw.HeaderBar.new()

        box1.append(header_bar)
        scrolled_box = Gtk.ScrolledWindow()
        box1.append(scrolled_box)
        scrolled_box.set_hexpand(True)
        scrolled_box.set_vexpand(True)
        scrolled_box.set_min_content_height(100)
        scrolled_box.set_min_content_width(600)
        scrolled_box.margin_bottom = 12
        scrolled_box.margin_right = 12
        scrolled_box.margin_top = 12
        scrolled_box.margin_left = 12
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)

        text_buffer = text_view.get_buffer()
        text_buffer.set_text(error_details)

        scrolled_box.set_child(text_view)
        dialog.present(parent_window or application)
        return False
