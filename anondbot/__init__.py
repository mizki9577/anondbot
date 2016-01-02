from .anondbot import AnondBotDaemon
from docopt import docopt

__doc__ = '''Twitter bot daemon which notifies recent articles of Hatena Anonymous Diary.

Usage:
  anondbotd [-hvndq] [-c FILE]

Options:
  -h --help         Show this help.
  -v --version      Show version.
  -c --config FILE  Specify configuration file [default: {}].
  -d --daemonize    Daemonize after startup.
  -n --dry-run      Do not post tweets actually.
  -q --quiet        Be quiet.
'''.format(AnondBotDaemon.CONFIG_FILE_PATH)


def main():
    args = docopt(__doc__, version='anondbot 1.1.0')
    daemon = AnondBotDaemon(
        config_file_path=args['--config'],
        daemonize=args['--daemonize'],
        dry_run=args['--dry-run'],
        quiet=args['--quiet'],
    )
    daemon.run()
