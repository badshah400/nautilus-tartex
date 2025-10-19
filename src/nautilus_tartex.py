# vim: set ai et ts=4 sw=4 tw=80:
#
# Copyright 2025 Atri Bhattacharya <badshah400@opensuse.org>
# Licensed under the terms of MIT License. See LICENSE.txt for details.

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from subprocess import run

# Try to import the Nautilus and GObject libraries.
# If this fails, the script will not be loaded by Nautilus,
# which is the desired behavior for non-GNOME environments.
try:
    import gi

    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    try:
        gi.require_version("Nautilus", "4.0")
    except ValueError:
        gi.require_version("Nautilus", "4.1")
    gi.require_version("Notify", "0.7")
    gi.require_version("Pango", "1.0")
    from gi.repository import (  # type: ignore [attr-defined]
        Adw,
        GLib,
        GObject,
        Gio,
        Gtk,
        Nautilus,
        Notify,
        Pango,
    )
except ImportError:
    pass

__appname__ = "nautilus-tartex"
__version__ = "0.3.0.dev0"


class TartexNautilusExtension(GObject.GObject, Nautilus.MenuProvider):
    """
    This extension provides a right-click menu item in Nautilus
    for .tex and .fls files to create a tarball using tartex.
    """

    Notify.init("TarTeX")

    def __init__(self):
        # Set terminal width long enough that most tartex log messages do not
        # have to wrap their lines. Also makes wrapping consistent and not
        # dependent on the width of the console launching nautilus (or 80
        # when started from the desktop menus).
        os.environ["COLUMNS"] = "132"

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
        app = Gtk.Application.get_default()
        if app:
            # Get the active nautilus window
            win = app.get_active_window()

        if app:
            app.mark_busy()
        self._run_tartex_process(file_obj, notif, app, win)

    def _notify_send(self, head: str, msg: str, n: Notify.Notification):
        """Send notification at end of process one way or another"""
        n.update(head, msg)
        n.set_urgency(Notify.Urgency.NORMAL)  # remove persistence
        n.set_timeout(Notify.EXPIRES_DEFAULT)
        n.show()
        return False

    def _run_tartex_process(
        self,
        file_obj: Nautilus.FileInfo,
        n: Notify.Notification,
        app: Gtk.Application,
        win: Gtk.Window,
    ):
        """
        Runs the blocking tartex process asynchronously.
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

        cmd = [tartex_path, file_path, "-b", "-v", "-s"]

        try:
            git_cmd = shutil.which("git")
            if git_cmd:
                _ = run(
                    [git_cmd, "rev-parse", "--git-dir"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                cmd += [
                    "--overwrite",
                    "--git-rev",
                    "--output",
                    parent_dir.get_path(),  # specify dir but use default
                                            # tartex git-rev name for output
                ]
            else:
                raise RuntimeError("unable to find git in PATH")

        except Exception:
            # Do not use git route but otherwise no problem
            # Generate a unique filename with a timestamp
            timestamp = datetime.now().strftime(r"%Y%m%d_%H%M%S")
            output_name = GLib.build_filenamev(
                [parent_dir.get_path(), f"{file_name_stem}_{timestamp}.tar.gz"]
            )
            cmd += ["--output", output_name]

        try:
            tartex_proc = Gio.SubprocessLauncher.new(
                Gio.SubprocessFlags.STDOUT_PIPE
                | Gio.SubprocessFlags.STDERR_PIPE
            )
            process = tartex_proc.spawnv(cmd)
            process.communicate_utf8_async(
                None,  # No stdin
                None,  # Cancellable (None)
                self._on_tartex_complete,  # Gio.AsyncReadyCallback function
                (app, win, file_obj, n),  # data to pass to the callback
            )

        except GLib.Error as err:
            GLib.timeout_add(
                0,
                self._notify_send,
                "TarTeX Error",
                f"🚨 Failed to launch command: {err}",
            )

        except Exception as e:
            GLib.timeout_add(
                0,
                self._notify_send,
                "TarTeX Error",
                f"🚫 An unknown error occurred: {e}",
            )

    def _on_tartex_complete(
        self, proc: Gio.Subprocess, res: Gio.AsyncResult, params: tuple
    ):
        """Callback func to run upon tartex completion"""

        app, win, file_obj, notif = params
        success, stdout, stderr = proc.communicate_utf8_finish(res)
        if app:
            app.unmark_busy()
        exit_code = proc.get_exit_status()

        if exit_code:
            GLib.timeout_add(
                0,
                self._notify_send,
                "TarTeX Error",
                f"🚨 Failed to create archive using {file_obj.get_name()}",
                notif,
            )
            full_error_output = f"{stdout}\n"
            GLib.timeout_add(
                0,
                self._show_error_dialog,
                win,
                file_obj,
                full_error_output,
                exit_code,
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
                    success_msg.split()[1],
                ]
            )
            GLib.idle_add(
                self._update_recent,
                [file_obj.get_uri(), GLib.filename_to_uri(output_file)],
            )

    def _update_recent(self, files: list[str]):
        """
        Update Gtk.RecentManager with list of uri

        :files: list of uri (list[str])
        """
        rec_man = Gtk.RecentManager.get_default()
        for _f in files:
            if not rec_man.add_item(_f):
                print(
                    f"Error: {__appname__}: Failed to add {_f} to recent manager."
                )

    def _show_error_dialog(
        self,
        parent_window: Gtk.Window,
        dir_path: str,
        error_details: str,
        exit_code: int,
    ) -> bool:
        """
        Shows a modal dialog with full error details, using a GTK4 layout.
        """
        err_dict: dict[int, str] = {
            1: "system error",
            2: "cache access",
            3: "git checkout",
            4: "LaTeX compilation",
            5: "tarball creation",
        }

        builder = Gtk.Builder()
        try:
            builder.add_from_file(
                str(Path(__file__).parent / "nautilus-tartex.ui")
            )
        except Exception as e:
            print(f"FATAL: Could not load UI file: {e}")
            return False

        # Retrieve widgets by ID (matching the UI file IDs)
        dialog: Adw.Dialog = builder.get_object("error_dialog")  # type: ignore[assignment]
        error_label: Gtk.Label = builder.get_object("summary_label")  # type: ignore[assignment]
        scrolled_box: Gtk.ScrolledWindow = builder.get_object(
            "scrolled_window"
        )  # type: ignore[assignment]
        text_view: Gtk.TextView = builder.get_object("text_view")  # type: ignore[assignment]
        copy_button: Gtk.Button = builder.get_object("copy_button")  # type: ignore[assignment]
        log_button: Gtk.Button = builder.get_object("log_button")  # type: ignore[assignment]
        close_button: Gtk.Button = builder.get_object("close_button")  # type: ignore[assignment]
        header_search_button: Gtk.Button = builder.get_object("search_button")  # type: ignore[assignment]
        header_search_bar: Gtk.SearchBar = builder.get_object("search_bar")  # type: ignore[assignment]
        search_entry: Gtk.SearchEntry = builder.get_object("search_entry")  # type: ignore[assignment]
        toggle_group: Adw.ToggleGroup = builder.get_object("toggle_group")  # type: ignore[assignment]
        toast_widget: Adw.ToastOverlay = builder.get_object("toast_overlay")  # type: ignore[assignment]

        win_width, win_height = parent_window.get_default_size()
        if not win_width:
            win_width = 600
        if not win_height:
            win_height = 400

        # padding from win size has to be large for win headerbar space, etc.
        size_padding = 150

        # To determine min size, we use relatively large values of width/height
        # for comparison since window sizes smaller than the comparison value
        # will anyway determine the minimum sizes. For window sizes larger than
        # the comparison values, this ensures the dialog box is not unwieldily
        # large.
        #
        # "... - 1" ensures when size_min and size_max are both determined by
        # the window size, the former is at least a pixel less than size_max
        box_size_min = (
            min(win_width - size_padding - 1, 900),
            min(win_height - size_padding - 1, 800),
        )

        dialog.set_size_request(*box_size_min)

        error_label.set_markup(
            f"<b>TarTeX failed at {err_dict[exit_code]}</b>",
        )

        # max size must always be determined by the window size, minus padding
        scrolled_box.set_max_content_width(win_width - size_padding)
        scrolled_box.set_max_content_height(win_height - size_padding)

        text_buffer = Gtk.TextBuffer()
        text_buffer.set_text(error_details)
        text_view.set_buffer(text_buffer)

        # Copy to clipboard button
        copy_button.connect(
            "clicked",
            lambda _: GLib.idle_add(
                text_view.get_clipboard().set,
                text_buffer.get_text(
                    text_buffer.get_start_iter(),
                    text_buffer.get_end_iter(),
                    False,
                ),
            ),
        )

        tag_table = text_buffer.get_tag_table()

        # highlight tag for search matches
        highlight_tag = Gtk.TextTag.new("match_highlight")
        default_adw_style = Adw.StyleManager.get_default()
        is_dark_theme = default_adw_style.get_dark()
        if default_adw_style.get_system_supports_accent_colors():
            acc_color = default_adw_style.get_accent_color()
            highlight_back = acc_color.to_rgba()
            highlight_back.alpha = 0.3
            highlight_tag.set_property("background-rgba", highlight_back)
        else:
            highlight_tag.set_property(
                "background", "yellow" if is_dark_theme else "cyan"
            )
            highlight_tag.set_property(
                "foreground", "black" if is_dark_theme else None
            )
        tag_table.add(highlight_tag)

        self._markup_text(text_buffer, tag_table, acc_color, is_dark_theme)

        if exit_code == 4:
            # latexmk err, log file saved; add "open log" button

            log_filename = "tartex_compile_error.log"
            log_path = GLib.build_filenamev([f"{Path.cwd()!s}", log_filename])
            log_button.set_visible(True)
            log_button.connect(
                "clicked",
                lambda _: GLib.idle_add(
                    self._open_log_file, (log_path, toast_widget)
                ),
            )

        close_button.connect("clicked", lambda _: dialog.close())

        def _on_search_text_changed(search_entry, *args):
            """Performs case-insensitive search and highlights matches."""

            search_query = search_entry.get_text().strip()

            # Remove existing highlights from the entire buffer
            start_iter = text_buffer.get_start_iter()
            end_iter = text_buffer.get_end_iter()
            text_buffer.remove_tag(highlight_tag, start_iter, end_iter)

            if not search_query:
                return

            search_query_lower = search_query.lower()
            text_to_search_lower = text_buffer.get_text(
                text_buffer.get_start_iter(),
                text_buffer.get_end_iter(),
            ).lower()

            # Iterate through text and apply new highlights
            offset = 0
            while True:
                match_index = text_to_search_lower.find(
                    search_query_lower, offset
                )

                if match_index == -1:
                    break  # No more matches found

                start_match_iter = text_buffer.get_iter_at_offset(match_index)

                # Get the end iterator (start + length of query)
                end_match_iter = text_buffer.get_iter_at_offset(
                    match_index + len(search_query)
                )

                text_buffer.apply_tag(
                    highlight_tag, start_match_iter, end_match_iter
                )
                offset = match_index + len(search_query)

        def _on_search_click(btn):
            search_mode = header_search_bar.get_search_mode()
            header_search_bar.set_search_mode(not search_mode)
            if not search_mode:  # search activated (search_mode: False)
                search_entry.grab_focus()
            else:
                # When closing the search bar, clear text and reset highlights
                search_entry.set_text("")
                _on_search_text_changed(search_entry)

        header_search_button.connect("clicked", _on_search_click)
        search_entry.connect("search-changed", _on_search_text_changed)
        header_search_bar.connect_entry(search_entry)  # ESC key to exit search

        def _filter_msg(_tgrp: Adw.ToggleGroup, pspec):
            lead_dict = {
                "All": "",
                "Errors": "CRITICAL|ERROR",
                "Warnings": "WARNING",
            }
            active_toggle = _tgrp.get_active_name()
            lead_filter = re.compile(
                rf"^(?:{lead_dict[active_toggle]}\s).*$",
                re.MULTILINE,
            )
            new_msg = ""
            if active_toggle == "All":
                text_buffer.set_text(error_details)
            elif active_toggle == "Errors":
                for _msg in lead_filter.findall(error_details):
                    new_msg += f"{_msg}\n"
                text_buffer.set_text(new_msg)
            elif active_toggle == "Warnings":
                for _msg in lead_filter.findall(error_details):
                    new_msg += f"{_msg}\n"
                text_buffer.set_text(new_msg)
            else:
                text_buffer.set_text(error_details)

            self._markup_text(text_buffer, tag_table, acc_color, is_dark_theme)
            if header_search_bar.get_search_mode():
                search_entry.grab_focus()
                _on_search_text_changed(search_entry)

        toggle_group.connect("notify::active", _filter_msg)

        dialog.present(parent_window)
        return False

    def _markup_text(
        self,
        text_buffer: Gtk.TextBuffer,
        tag_table: Gtk.TextTagTable,
        acc_color: Adw.AccentColor,
        dark_theme: bool,
    ):
        text = text_buffer.get_text(
            text_buffer.get_start_iter(), text_buffer.get_end_iter(), False
        )

        # Red colour to highlight "ERROR" in text...
        error_tag = Gtk.TextTag.new("error")
        error_tag.set_property("foreground", "red")

        # ... and bold fonts for the error message itself
        highlight_tag = Gtk.TextTag.new("error-highlight")
        highlight_tag.set_property("weight", Pango.Weight.BOLD)

        # Dim lines that begin with "INFO"
        info_tag = Gtk.TextTag.new("info-dim")
        info_tag.set_property("foreground", "grey")

        # Increase spacing between lines, accounting for wrapping
        spacing_tag = Gtk.TextTag.new("line-spacing")
        spacing_tag.set_property("pixels-above-lines", 8)

        # highlight line numbers (line XX or l.XX) using accent if possible
        if acc_color:
            acc_color_standalone_rgba = acc_color.to_standalone_rgba(
                dark_theme
            )
            acc_color_standalone = acc_color_standalone_rgba.to_string()
        else:
            acc_color_standalone = "Teal"

        lnum_tag = Gtk.TextTag.new("line-num")
        lnum_tag.set_property("foreground", acc_color_standalone)

        for _tag in [
            error_tag,
            highlight_tag,
            info_tag,
            spacing_tag,
            lnum_tag,
        ]:
            if not tag_table.lookup(_tag.get_property("name")):
                tag_table.add(_tag)

        # Error line may wrap into a second line (which will then start with
        # whitespace)
        error_pattern = re.compile(
            r"^(error|fatal|critical) (?P<err1>.*)(?:\r\n\s|\n\s)?"
            r"(?P<err2>.*)?",
            re.IGNORECASE | re.MULTILINE,
        )

        # Apply ERROR tags
        for match in error_pattern.finditer(text):
            start_iter = text_buffer.get_iter_at_offset(match.start(1))
            end_iter = text_buffer.get_iter_at_offset(match.end(1))
            text_buffer.apply_tag_by_name("error", start_iter, end_iter)
            start_iter = text_buffer.get_iter_at_offset(match.start("err1"))
            end_iter = text_buffer.get_iter_at_offset(match.end("err1"))
            text_buffer.apply_tag_by_name(
                "error-highlight", start_iter, end_iter
            )
            if match.group("err2"):
                start_iter = text_buffer.get_iter_at_offset(
                    match.start("err2")
                )
                end_iter = text_buffer.get_iter_at_offset(match.end("err2"))
            text_buffer.apply_tag_by_name(
                "error-highlight", start_iter, end_iter
            )

        # helper func to apply tags
        def _apply_tag(tag_name: str, patt: re.Pattern):
            for match in patt.finditer(text):
                start_iter = text_buffer.get_iter_at_offset(match.start())
                end_iter = text_buffer.get_iter_at_offset(match.end())
                text_buffer.apply_tag_by_name(tag_name, start_iter, end_iter)

        # INFO line tagging: lines may wrap into the next line, but wrapped line
        # starts with whitespace
        info_pattern = re.compile(
            r"^INFO .+(?:\r\n\s|\n\s)?.*", re.IGNORECASE | re.MULTILINE
        )
        _apply_tag("info-dim", info_pattern)

        lspace_pattern = re.compile(r"^\S", re.MULTILINE)
        _apply_tag("line-spacing", lspace_pattern)

        re_lnum = re.compile(r"(line |l\.)(\d+)")
        _apply_tag("line-num", re_lnum)

    def _open_log_file(self, data: tuple[str, Adw.ToastOverlay]):
        log_path = data[0]
        log_file = Gio.File.new_for_path(log_path)

        toast: Adw.ToastOverlay = data[1]
        try:
            Gio.AppInfo.launch_default_for_uri(
                log_file.get_uri(),
                None,  # LaunchContext (not needed here)
            )

        except GLib.GError as err:
            if err.domain == "g-io-error-quark":
                log_msg = f"File not found: {log_file.get_basename()}"
                print(f"{__appname__}: ERROR: {log_msg}", file=sys.stderr)
                toast_msg = Adw.Toast.new(log_msg)
                toast_msg.set_timeout(5)
                toast.add_toast(toast_msg)
