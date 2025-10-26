project('nautilus-tartex',
  version: '0.3.0.dev0',
  meson_version: '>= 0.59.0'
)

files_app = 'nautilus'

python = import('python')
python.find_installation('python3',
  modules: [
        'gi',
        'gi.repository.Adw',
        'gi.repository.GLib',
        'gi.repository.GObject',
        'gi.repository.Gio',
        'gi.repository.Gtk',
        'gi.repository.Nautilus',
        'gi.repository.Pango',
  ],
)

find_program('tartex', required: true, version: '>= 0.11.0')

user_install = get_option('user')
if user_install
  fs = import('fs')
  prefix = fs.expanduser('~') / '.local'
else
  prefix = get_option('prefix')
endif

datadir = get_option('datadir')
extension_dir = prefix / datadir / files_app + '-python' / 'extensions'

gnome = import('gnome')
resources = gnome.compile_resources(
  meson.project_name() + '-resources',
  'resources' / 'resources.gresource.xml',
  gresource_bundle: true,
  source_dir: meson.current_build_dir(),
  install: true,
  install_dir: extension_dir,
)

install_data('src/nautilus_tartex.py', install_dir: extension_dir)
# install_data('src/nautilus-tartex.ui', install_dir: extension_dir)
# install_data('data/icons/archive-symbolic.svg', install_dir: extension_dir)
