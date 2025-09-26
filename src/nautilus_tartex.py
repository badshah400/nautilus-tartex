# vim: set ai et ts=4 sw=4 tw=80:

import subprocess
import os
import shutil
from datetime import datetime
from pathlib import Path
import threading

# Try to import the Nautilus and GObject libraries.
# If this fails, the script will not be loaded by Nautilus,
# which is the desired behavior for non-GNOME environments.
try:
    import gi  # type: ignore[import-untyped]
    gi.require_version("Gtk", "4.0")
    gi.require_version("Notify", "0.7")
    from gi.repository import (  # type: ignore[import-untyped]
        Nautilus,
        Notify,
        GLib,
        GObject,
    )
except ImportError:
    pass


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
            top_menu_item.connect("activate", self.on_tartex_activate, file_obj)
            return [top_menu_item]

        return []

    def get_background_items(
          self,
          current_folder: Nautilus.FileInfo,
      ) -> list[Nautilus.MenuItem]:
          return []

    def _run_tartex_process(
        self,file_obj: Nautilus.FileInfo, n: Notify.Notification
    ):
        """
        Runs the blocking tartex process in a separate thread.
        This function handles the synchronous part and sends the final
        notification.
        """
        try:
            tartex_path = shutil.which("tartex")
            if not tartex_path:
                GLib.idle_add(
                    self._notify_send,
                    "Error",
                    "tartex command not found in PATH.",
                    n
                )
                return

            file_path = file_obj.get_location().get_path()
            file_name_stem = os.path.splitext(file_obj.get_name())[0]

            use_git = (Path(file_path).parent / ".git").is_dir()

            # Generate a unique filename with a timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"{file_name_stem}_{timestamp}.tar.gz"


            cmd = [tartex_path, file_path, "-b", "-s"]
            if use_git:
                cmd += ["--overwrite", "--git-rev"]
            else:  # use unique time-stamped output tar name
                cmd += ["--output", output_name]

            # This is the synchronous (blocking) part of the code
            tartex_proc = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )

            # Use final summary line upon success for notification
            success_msg = tartex_proc.stdout.splitlines()[-1]
            success_msg = success_msg.replace("Summary: ", "", count=1)
            GLib.idle_add(self._notify_send, "Success", success_msg, n)

        except subprocess.CalledProcessError:
            GLib.idle_add(
                self._notify_send,
                "Error",
                f"tartex failed to create archive using {file_path}",
                n,
            )

        except Exception:
            GLib.idle_add(
                self._notify_send,
                "Error",
                " An unexpected error occurred",
                n
            )

    def on_tartex_activate(self, menu_item, file_obj):
        """
        This method is called when the user clicks the menu item.
        It starts the tartex command in a new thread to keep the UI responsive.
        """
        # 1. Send an immediate notification that the work has started
        notif = Notify.Notification.new(
            "TarTeX",
            "Archive creation started (running in background).",
        )
        notif.show()

        # 2. Start the blocking process in a new thread
        thread = threading.Thread(
            target=self._run_tartex_process,
            args=(file_obj, notif),
            daemon=True,  # Ensures the thread exits if the main app is closed
        )
        thread.start()
        file_obj.invalidate_extension_info()

    def _notify_send(self, head: str, msg: str, n: Notify.Notification):
        """Send notification at end of process one way or another

        """
        n.update(head, msg)
        n.show()
