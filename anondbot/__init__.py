from .anondbot import AnondBotDaemon


def main():
    #daemon = AnondBotDaemon(AnondBotDaemon.CONFIG_FILE_PATH)
    daemon = AnondBotDaemon('/home/mizki/project/anondbot/anondbot.conf', fork=False, dry_run=True)
    daemon.run()
