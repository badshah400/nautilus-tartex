## TarTeX context menu extension for nautilus ##

`nautilus-tartex` is a context menu extension for the GNOME Files app,
nautilus, to enable one-click generation of tarball of all files needed to
compile your LaTeX project using [`tartex`](https://pypi.org/project/tartex/).

### Usage ###

*Note*: Only works on single file selections.

Right click on the main `.tex` or `.fls` file in a LaTeX project and select
"Create a TarTeX archive" from the context menu.

When clicking on an `.fls` file, the input sources listed in this record file
are directly added to the resulting tarball, named identically to the fls
filename (sans extension) with a time-stamp appended to it. This naming scheme
allows you to create and store snapshots of your TeX project as it evolves. Note
that *no checks are made* as to whether the tarballed TeX project will compile
when the trigger file is `.fls`.

When clicking on a `.tex` file, the tarball procedure follows the usual tartex
route of checking the cache, recompiling sources in a temporary directory if it
is stale, and including the required sources detected from either the cache or
logs from the re-compile.

`nautilus-tartex` automatically routes tartex into the latter's
[`git-rev` mode](https://github.com/badshah400/tartex?tab=readme-ov-file#usage)
if it detects a `.git` directory inside the project.

If tartex fails to create the archive, `nautilus-tartex` launches a dialog box
relaying output messages from tartex. The dialog box offers basic searching and,
when the error is due to LaTeX compilation failure, a button to open the full
LaTeX compilation log. It also provides a toggle bar to optionally filter the
output messages by errors or warnings.

### Installation ###

#### Pre-requisites ####

The command line utility [`tartex`](https://pypi.org/project/tartex/) version
`0.11.0` or higher must be installed and in `PATH`.

`nautilus-tartex` depends on the following libraries and their Python bindings
exposed via
[`gobject-introspection`](https://developer.gnome.org/documentation/guidelines/programming/introspection.html):

* `libadwaita-1.0`
* `gtk-4.0`
* `glib-2.0`
* `libnotify >= 0.7.0`
* `pango`
* [`nautilus-python`](https://gitlab.gnome.org/GNOME/nautilus-python)

Additionally, [`meson`](https://mesonbuild.com/) is recommended for installing,
because, before installing, it checks whether all requirements are satisfied.

However, if you are sure of all pre-requisites being installed in your system,
you may simply copy over the
[`src/nautilus_tartex.py`](./src/nautilus_tartex.py) file into your
`nautilus-python` extensions directory, typically at
`$XDG_DATA_HOME/nautilus-python/extensions/`.

#### Install using `meson` ####

Download and extract a
[release](https://github.com/badshah400/nautilus-tartex/releases) tarball. `cd`
into the extracted directory and use `meson` to configure and install the
extension using _one_ of the following modes (from a console):

1. As a regular, non-privileged user:
   ```console
   meson setup -Duser=true build
   meson install -C build
   ```
   **OR**
2. With root privileges:
   ```console
   meson setup build
   sudo meson install -C build
   ```

Quit open nautilus windows (`nautilus -q`) and re-launch nautilus to see
`nautilus-tartex` in action.

### License ###

© 2025 Atri Bhattacharya

`nautilus-tartex` is distributed under the terms of MIT License. See the
[LICENSE](./LICENSE.txt) file for details.
