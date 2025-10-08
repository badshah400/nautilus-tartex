# Changelog

## Unreleased

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

