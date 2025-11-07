# Changelog

## 0.3.1 [2025-11-08]

### Added

- Select generated tar file in the active nautilus folder if tartex succeeds
- Add accent colour to spinner in progress dialog
- Use "success" css style for icon in success pop-up dialog

### Fixed

- Limit wrapped lines in success dialog on narrow displays to two at most

## 0.3.0 [2025-11-02]

### Added

- Use transient dialog-box with spinner as indicator when tartex archiving is in progress
- Drop notification indicating tartex archiving in progress
- Add pop-up dialog attached to active nautilus window when tartex succeeds

### Fixed

- Improve logic for detection of whether to use tartex's `git-rev` workflow
- Fix GLib exception handling that used `GLib.GError` instead of `GLib.Error`

## 0.2.0 [2025-10-17]

### Added

- Make error dialog box adaptive for improved experience on narrow screens
- Add toggles to filter output message by error or warnings (or show all)
- Filter out UI layout, property, and style elements into a GTK .ui XML file and use Gtk.Builder to refer to them in code

### Fixed

- Lots of layout fixes for improved user experience
- Fix dialog height jumping with content changes (message filtering, search-bar dropping down, etc.)
- Add margins to prevent text flowing into, and beyond, scroll-bars
- Allow working with nautilus version 4.0 or 4.1, whichever is available and loaded first
- Use the nautilus window active at menu trigger, not the (potentially different) one that is active when compilation is done
- When clicking on the "Copy" button, copy output text shown in dialog box, not the full error log
- Ensure searching targets displayed output, not the entire error log
- Check for Adw and Pango libraries when configuring for install

## 0.1.0 [2025-10-09]

### Added

- Show dialog box with tartex output and logs when archiving fails
- Show an "Open Log" button on dialog window when archiving fails due to latexmk
    error
- Show Copy to clipboard button overlaid on output messages area in dialog box
- Add simple search and highlight functionality to dialog box, triggered either
    by clicking search button or simply starting to type in search terms
- Add toast overlay message for the edge case where the error log file may have
    been deleted after the dialog is launched, causing "Open Log" button to fail

### Fixed

- Set environment variable "COLUMNS" to 132 for consistent line wrapping and for
    only really long lines
- Avoid possible race issues from obtaining application id at multiple points in
    the code by getting it initially and propagating it throughout
- *Note*: `tartex >= 0.11.0` is now required.

## [0.0.2] 2025-10-01

### Added

- Add used .tex or .fls file and generated tarball to list of "Recent" files for easy access

### Fixed

- Better, more robust handling of `tartex` summary message re-used in notification body when tarballing is successful
- Change working directory to project dir to allow `tartex` to use relative, shorter file names in output logs and messages
- *Note*: `tartex >= 0.10.4` is now required

## [0.0.1] 2025-09-30

*Initial release*

