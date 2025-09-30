# vim: set ai et ts=4 sw=4 tw=80:
#
# Copyright 2025 Atri Bhattacharya <badshah400@opensuse.org>
# Licensed under the terms of MIT License. See LICENSE.txt for details.

import os
import shutil
from datetime import datetime
from pathlib import Path

# Try to import the Nautilus and GObject libraries.
# If this fails, the script will not be loaded by Nautilus,
# which is the desired behavior for non-GNOME environments.
try:
    import gi  # type: ignore[import-untyped]

    gi.require_version("Gtk", "4.0")
    gi.require_version("Nautilus", "4.1")
    gi.require_version("Notify", "0.7")
    from gi.repository import (  # type: ignore[import-untyped]
        Nautilus,
        Notify,
        GLib,
        GObject,
        Gio,
        Gtk,
    )
except ImportError:
    pass

__appname__ = "nautilus-tartex"
__version__ = "0.0.1"

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
            success_msg = stdout.splitlines()[-1]
            success_msg = success_msg.replace("Summary: ", "", count=1)
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
            rec_man.add_item(_f)

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

    def _show_error_dialog(self, dir_path, error_details, exit_code):
        """
        Shows a modal dialog with full error details, using a GTK4 layout.
        """
        # Get the active application instance if possible
        application = Gtk.Application.get_default()
        parent_window = None
        if application:
            # Attempt to get the active window (likely the Nautilus window)
            parent_window = application.get_active_window()

        # 1. Create a modal dialog
        dialog = Gtk.Dialog(
            title="TarTeX Archive Generation Failed",
            modal=True,
            default_width=600,
            default_height=400,
            application=application,  # Attach to the main application if available
            transient_for=parent_window,
        )

        # 2. Add the 'Close' button to the action area (standard GTK Dialog footer)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)

        # Connect response signal to close the dialog
        dialog.connect("response", lambda d, r: d.close())

        # 3. Set up the content area box
        content_area = dialog.get_content_area()
        content_area.set_orientation(Gtk.Orientation.VERTICAL)
        content_area.set_spacing(12)
        content_area.set_margin_top(18)
        content_area.set_margin_bottom(6)
        content_area.set_margin_start(18)
        content_area.set_margin_end(18)

        # 4. Header Message with Icon
        header_hbox = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12
        )

        # Using a standard GNOME error icon
        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        error_icon.set_icon_size(Gtk.IconSize.LARGE)
        error_icon.set_valign(Gtk.Align.START)
        header_hbox.append(error_icon)

        # Header text
        header_label = Gtk.Label(
            label=f"<b>TarTeX failed with exit code {exit_code}.</b>\n\n",
            use_markup=True,
            xalign=0,
            halign=Gtk.Align.START,
            wrap=True,
        )
        header_hbox.append(header_label)
        content_area.append(header_hbox)

        # 5. Add the scrollable text area for details
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )
        scrolled_window.set_margin_top(6)
        scrolled_window.get_style_context().add_class("dialog-output-frame")

        # Use Gtk.TextView inside Gtk.ScrolledWindow for proper selection and
        # scrolling of large output
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)

        text_buffer = text_view.get_buffer()
        text_buffer.set_text(error_details)

        scrolled_window.set_child(text_view)
        content_area.append(scrolled_window)

        dialog.present()
        return False
