## TarTeX context menu extension for nautilus ##

`nautilus-tartex` is a context menu extension for the GNOME Files app,
nautilus, to enable one-click tarball-ing of all files needed to compile your
LaTeX project using [`tartex`](https://pypi.org/project/tartex/).

### Usage ###

Right click on the main `.tex` or `.fls` file in a LaTeX project and select
"Create a TarTeX archive" from the context menu.

*Note*: Only works on single file selections.

### Installation ###

#### Pre-requisites ####

The command line utility [`tartex`](https://pypi.org/project/tartex/) version
`0.10.4` or higher must be installed and in `PATH`.

`nautilus-tartex` depends on the following libraries and their Python bindings
exposed via
[`gobject-introspection`](https://developer.gnome.org/documentation/guidelines/programming/introspection.html):

* `gtk-4.0`
* `glib-2.0`
* `libnotify >= 0.7.0`
* [`nautilus-python`](https://gitlab.gnome.org/GNOME/nautilus-python)

Additionally, [`meson`](https://mesonbuild.com/) is recommended for installing,
because, before installing, it checks whether all requirements are satisfied.

However, if you are sure of all pre-requisites being installed in your system,
you may simply copy over the
[`src/nautilus_tartex.py`](./src/nautilus_tartex.py) file into your
`nautilus-python` extensions directory, typically at
`$XDG_DATA_HOME/nautilus-python/extensions/`.

#### Meson based installation ####

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
