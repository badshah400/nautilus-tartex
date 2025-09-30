project('nautilus-tartex',
  version: '0.0.3.dev0',
  meson_version: '>= 0.59.0'
)

files_app = 'nautilus'

python = import('python')
python.find_installation('python3',
  modules: [
        'gi',
        'gi.repository.GLib',
        'gi.repository.GObject',
        'gi.repository.Gio',
        'gi.repository.Gtk',
        'gi.repository.Nautilus',
        'gi.repository.Notify',
  ],
)

find_program('tartex', required: true, version: '>= 0.10.4')

user_install = get_option('user')
if user_install
  fs = import('fs')
  prefix = fs.expanduser('~') / '.local'
else
  prefix = get_option('prefix')
endif

datadir = get_option('datadir')
extension_dir = prefix / datadir / files_app + '-python' / 'extensions'

install_data('src/nautilus_tartex.py', install_dir: extension_dir)
