'''Twitter bot daemon which notifies recent articles of Hatena Anonymous Diary.

Usage:
  anondbot [-hvndq] [-c FILE] [-t DIR]

Options:
  -h --help         Show this help.
  -v --version      Show version.
  -c --config FILE  Specify configuration file [default: /etc/anondbotrc].
  -t --cache DIR    Specify cache directory [default: /var/tmp/anondbotrc].
  -d --daemonize    Daemonize after startup.
  -n --dry-run      Do not post tweets actually.
  -q --quiet        Be quiet.
'''

from .anondbot import AnondBotDaemon
from docopt import docopt


def main():
    args = docopt(__doc__, version='anondbot 1.2.6')
    daemon = AnondBotDaemon(
        config_file_path=args['--config'],
        cache_dir_path=args['--cache'],
        daemonize=args['--daemonize'],
        dry_run=args['--dry-run'],
        quiet=args['--quiet'],
    )
    daemon.run()
