project('nautilus-tartex',
  version: '0.0.1',
  meson_version: '>= 0.59.0'
)

files_app = 'nautilus'

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
