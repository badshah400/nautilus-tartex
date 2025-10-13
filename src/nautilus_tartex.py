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
__version__ = "0.2.0.dev0"


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
        parent_window = None
        if app:
            # Attempt to get the active window (likely the Nautilus window)
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

        cmd = [tartex_path, file_path, "-b", "-v", "-s"]
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
                print(f"Error: {__appname__}: Failed to add {_f} to recent manager.")

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
            1: "unknown error",
            2: "cache access",
            3: "git checkout",
            4: "LaTeX compilation",
            5: "tarball creation",
        }

        win_width, win_height = parent_window.get_default_size()
        if not win_width:
            win_width = 600
        if not win_height:
            win_height = 400

        # padding from win size has to be large for win headerbar space, etc.
        size_padding = 200

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
        # max size must always be determined by the window size, minus padding
        box_size_max = (win_width - size_padding, win_height - size_padding)

        # a cut-off for when to start dropping elements from dialog box to
        # accommodate the decreasing width/height
        size_limit = (500, 400)

        dialog = Adw.Dialog.new()
        dialog.set_title("TarTeX error")
        dialog.set_size_request(*box_size_min)
        dialog.set_follows_content_size(True)

        content = Adw.ToolbarView()
        dialog.set_child(content)

        BOX1_MARGIN = 12
        box1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box1.set_hexpand(True)
        box1.set_vexpand(True)
        box1.set_halign(Gtk.Align.FILL)
        box1.set_margin_end(BOX1_MARGIN)
        box1.set_margin_start(BOX1_MARGIN)
        box1.set_margin_top(BOX1_MARGIN)
        content.set_content(box1)

        box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        BOX2_MARGIN = 6
        box2.set_halign(Gtk.Align.FILL)
        box2.set_margin_start(BOX2_MARGIN)
        box2.set_margin_end(BOX2_MARGIN)
        box2.set_margin_top(BOX2_MARGIN)
        box2.set_margin_bottom(BOX2_MARGIN)
        if box_size_min[1] > size_limit[1]:
            box1.append(box2)
        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        error_icon.set_icon_size(Gtk.IconSize.LARGE)
        error_icon.set_valign(Gtk.Align.START)
        error_icon.add_css_class("error")
        if box_size_min[0] > (size_limit[0] + 50):
            box2.append(error_icon)

        err_summary = Gtk.Label(
            label=f"<b>TarTeX failed at {err_dict[exit_code]}</b>",
            use_markup=True,
            halign=Gtk.Align.START,
            wrap=False,
        )
        err_summary.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        err_summary.set_hexpand(True)
        if box_size_min[0] > size_limit[0]:
            box2.append(err_summary)

        scrolled_box = Gtk.ScrolledWindow()
        scrolled_box.set_hexpand(True)
        scrolled_box.set_vexpand(True)
        scrolled_box.set_min_content_width(box_size_min[0])
        scrolled_box.set_min_content_height(box_size_min[1])
        scrolled_box.set_max_content_width(box_size_max[0])
        scrolled_box.set_max_content_height(box_size_max[1])
        # Don't propagate natural height: it causes the dialog height to jump
        # around when alternating between different output msg filters if the
        # number of lines in the text_buffer changes significantly, providing
        # a rather poor user experience
        scrolled_box.set_propagate_natural_height(False)
        scrolled_box.set_propagate_natural_width(True)

        TEXTVIEW_MARGIN = 6
        text_view = Gtk.TextView()
        text_buffer = Gtk.TextBuffer()
        text_buffer.set_text(error_details)
        text_view.set_buffer(text_buffer)
        text_view.set_margin_bottom(TEXTVIEW_MARGIN)
        text_view.set_margin_end(TEXTVIEW_MARGIN)
        text_view.set_margin_start(TEXTVIEW_MARGIN)
        text_view.set_left_margin(TEXTVIEW_MARGIN)
        text_view.set_right_margin(TEXTVIEW_MARGIN)
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_monospace(True)
        text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        scrolled_box.set_child(text_view)

        # Copy to clipboard button
        copy_button = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        copy_button.set_tooltip_text("Copy Output Text")
        copy_button.add_css_class("raised")
        copy_button.add_css_class("circular")
        copy_button.add_css_class("suggested-action")
        copy_button.set_opacity(0.8)
        copy_button.connect(
            "clicked",
            lambda _: GLib.idle_add(
                text_view.get_clipboard().set,
                text_buffer.get_text(
                    text_buffer.get_start_iter(),
                    text_buffer.get_end_iter(),
                    False,
                )
            ),
        )

        copy_button.set_halign(Gtk.Align.END)
        copy_button.set_valign(Gtk.Align.START)
        copy_button.set_size_request(32, 32)
        copy_button.set_margin_top(12)
        copy_button.set_margin_end(20)  # more space for right scrollbar

        copy_overlay = Gtk.Overlay.new()
        copy_overlay.add_overlay(copy_button)
        toast_widget = Adw.ToastOverlay.new()
        toast_widget.set_child(scrolled_box)
        copy_overlay.set_child(toast_widget)

        box1.append(copy_overlay)

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

        header_bar = Adw.HeaderBar()

        if (exit_code == 4):
            # latexmk err, log file saved; add "open log" button

            log_filename = "tartex_compile_error.log"
            log_path = GLib.build_filenamev([f"{Path.cwd()!s}", log_filename])
            header_log_button = Gtk.Button.new_with_mnemonic("_Open Log")
            header_log_button.set_tooltip_markup(
                f"Open <b>{log_filename}</b> in Text Editor"
            )
            header_bar.pack_start(header_log_button)
            header_log_button.connect(
                "clicked",
                lambda _: GLib.idle_add(
                    self._open_log_file, (log_path, toast_widget)
                ),
            )

        if box_size_min[0] > size_limit[0]:
            header_bar.set_show_end_title_buttons(False)
            header_close_button = Gtk.Button.new_with_label("Close")
            header_close_button.add_css_class("destructive-action")
            header_close_button.connect("clicked", lambda _: dialog.close())
            header_bar.pack_end(header_close_button)
        else:
            header_bar.set_show_end_title_buttons(True)

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

        # header searchbar
        header_search_button = Gtk.Button.new_from_icon_name(
            "edit-find-symbolic"
        )
        header_bar.pack_start(header_search_button)

        header_search_bar = Gtk.SearchBar()
        header_search_bar.set_search_mode(False)

        def _on_search_click(btn):
            search_mode = header_search_bar.get_search_mode()
            header_search_bar.set_search_mode(not search_mode)
            if (not search_mode):  # search activated (search_mode: False)
                search_entry.grab_focus()
            else:
                # When closing the search bar, clear text and reset highlights
                search_entry.set_text("")
                _on_search_text_changed(search_entry)

        header_search_button.connect("clicked", _on_search_click)

        search_entry = Gtk.SearchEntry()
        search_entry.set_hexpand(True)
        search_entry.connect("search-changed", _on_search_text_changed)
        header_search_bar.set_child(search_entry)
        header_search_bar.set_key_capture_widget(dialog)
        header_search_bar.connect_entry(search_entry)  # ESC key to exit search

        content.add_top_bar(header_bar)
        content.add_top_bar(header_search_bar)
        # headerbars with labelled buttons look better with the "RAISED" style
        content.set_top_bar_style(Adw.ToolbarStyle.RAISED)

        def _filter_msg(_tgrp: Adw.ToggleGroup, pspec):
            lead_dict = {
                "All": "", "Errors": "CRITICAL|ERROR", "Warnings": "WARNING"
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

            self._markup_text(
                text_buffer, tag_table, acc_color, is_dark_theme
            )
            if header_search_bar.get_search_mode():
                search_entry.grab_focus()
                _on_search_text_changed(search_entry)

        toggle_error = Adw.Toggle.new()
        toggle_error.set_label("Errors")
        toggle_warn = Adw.Toggle.new()
        toggle_warn.set_label("Warnings")
        toggle_all = Adw.Toggle.new()
        toggle_all.set_label("All")
        toggle_all.set_enabled(True)

        toggle_group = Adw.ToggleGroup.new()
        toggle_group.add_css_class("round")
        for _togg in [toggle_all, toggle_error, toggle_warn]:
            _togg.set_name(_togg.get_label())
            toggle_group.add(_togg)
        toggle_group.set_active_name(toggle_all.get_name())
        toggle_group.connect("notify::active", _filter_msg)
        if box_size_min[0] < size_limit[0]:
            toggle_group.set_hexpand(True)
            toggle_group.set_halign(Gtk.Align.FILL)

        box2.append(toggle_group)
        box1.set_margin_bottom(BOX1_MARGIN)

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
                error_tag, highlight_tag, info_tag, spacing_tag, lnum_tag
        ]:
            if not tag_table.lookup(_tag.get_property("name")):
                tag_table.add(_tag)

        # Error line may wrap into a second line (which will then start with
        # whitespace)
        error_pattern = re.compile(
            r"^(Error|FATAL|Critical) (?P<err1>.*)(?:\r\n\s|\n\s)?"
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

        # INFO line tagging: lines may wrap into the next line, but wrapped line
        # starts with whitespace
        info_pattern = re.compile(
            r"^INFO .+(?:\r\n\s|\n\s)?.*", re.IGNORECASE | re.MULTILINE
        )
        for match in info_pattern.finditer(text):
            start_iter = text_buffer.get_iter_at_offset(match.start())
            end_iter = text_buffer.get_iter_at_offset(match.end())
            text_buffer.apply_tag_by_name("info-dim", start_iter, end_iter)

        for match in re.finditer(r"^\S", text, re.MULTILINE):
            start_iter = text_buffer.get_iter_at_offset(match.start())
            end_iter = text_buffer.get_iter_at_offset(match.end())
            text_buffer.apply_tag_by_name("line-spacing", start_iter, end_iter)

        re_lnum = re.compile(r"(line |l\.)(\d+)")
        for match in re_lnum.finditer(text):
            start_iter = text_buffer.get_iter_at_offset(match.start())
            end_iter = text_buffer.get_iter_at_offset(match.end())
            text_buffer.apply_tag_by_name("line-num", start_iter, end_iter)

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
