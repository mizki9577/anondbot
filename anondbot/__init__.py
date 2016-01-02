from configparser import ConfigParser
from datetime import datetime
import sys
import syslog
import time
import traceback

import requests
from requests_oauthlib import OAuth1
from bs4 import BeautifulSoup
from daemon import daemon
import lockfile


class AnondArticle:

    '''
    はてな匿名ダイアリーの記事を表現するクラス
    '''

    def __init__(self, url, output):
        self._url = url
        self.output = output
        self.fetched = False

    def fetch(self):
        if self.fetched:
            return

        while True:
            try:
                doc = requests.get(self.url)
                doc.raise_for_status()
            except requests.RequestException:
                self.output('An error occured. Retrying to fetch...')
            else:
                break

        self.soup = BeautifulSoup(doc.content, 'html.parser')
        self._url = doc.url
        self.fetched = True

    @property
    def title(self):
        '''記事タイトルを返す'''
        self.fetch()
        return self.soup.find('title').string

    @property
    def trackback_url(self):
        '''トラックバック先の URL を返す'''
        self.fetch()
        try:
            return self.soup.find('a', {'class': 'self', 'name': 'tb'})['href']
        except TypeError:
            return []

    @property
    def url(self):
        '''記事の URL を返す'''
        return self._url

    @property
    def id(self):
        '''記事の ID を返す'''
        return self.url.rsplit('/', 1)[-1]

    @property
    def datetime(self):
        '''記事の投稿日時を返す'''
        return datetime.strptime(self.id, '%Y%m%d%H%M%S')


def get_anond_articles(url, output):
    doc = requests.get(url)
    soup = BeautifulSoup(doc.content, 'html.parser')
    return (AnondArticle(item['rdf:resource'], output=output)
            for item in reversed(soup.find_all('rdf:li')))


class AnondBotDaemon:

    '''
    はてな匿名ダイアリー通知bot
    '''

    CONFIG_FILE_PATH = '/etc/anondbot.conf'
    STATUSES_UPDATE_URL = 'https://api.twitter.com/1.1/statuses/update.json'
    ANOND_FEED_URL = 'http://anond.hatelabo.jp/rss'

    def __init__(self, config_file_path, fork=None, dry_run=False):
        self.dry_run = dry_run
        self.fork = fork
        if self.fork:
            self.output = syslog.syslog
        else:
            self.output = lambda *v: print(*v, file=sys.stderr)

        # 設定読み込み
        self.config_file_path = config_file_path
        self.config = ConfigParser()
        with open(self.config_file_path, 'r') as f:
            self.config.read_file(f)

        # Twitter 関係
        consumer_key = self.config['twitter']['consumer_key']
        consumer_secret = self.config['twitter']['consumer_secret']
        access_token = self.config['twitter']['access_token']
        access_secret = self.config['twitter']['access_secret']
        self.oauth = OAuth1(client_key=consumer_key,
                            client_secret=consumer_secret,
                            resource_owner_key=access_token,
                            resource_owner_secret=access_secret)

        # デーモンの設定
        self.last_article_timestamp = int(
            self.config['config']['last_article_timestamp'])
        self.interval_sec = int(
            self.config['config']['update_interval'])
        self.pid_file_path = self.config['config']['pid_file_path']

    def run(self):
        '''デーモンを開始する'''
        pid_file = lockfile.FileLock(self.pid_file_path)
        daemon_context = daemon.DaemonContext(
            pidfile=pid_file,
            uid=1000, gid=100, initgroups=False,
            stdout=sys.stdout, stderr=sys.stderr,
            detach_process=self.fork)

        try:
            with daemon_context:
                while True:
                    self.update()
                    time.sleep(self.interval_sec)
        except SystemExit as e:
            self.output('exiting request received. exiting...')
            raise e
        except:
            self.output(traceback.format_exc())
            self.output('error(s) occured. exiting...')
            sys.exit(1)

    def update(self):
        '''新着記事を確認し Twitter に投稿する'''
        self.output('fetching...')
        articles = get_anond_articles(self.ANOND_FEED_URL, output=self.output)
        self.output('fetching done.')

        for article in articles:
            if self.last_article_timestamp >= article.datetime.timestamp():
                continue
            self.last_article_timestamp = int(article.datetime.timestamp())
            if not article.trackback_url:
                self.post_twitter('{} {}'.format(article.title, article.url))

        # 設定の保存
        self.config['config']['last_article_timestamp'] = str(
            self.last_article_timestamp)
        with open(self.config_file_path, 'w') as f:
            self.config.write(f)

    def post_twitter(self, status):
        if not self.dry_run:
            requests.post(self.STATUSES_UPDATE_URL,
                          params={'status': status},
                          auth=self.oauth)
        self.output(status)


def main():
    daemon = AnondBotDaemon(AnondBotDaemon.CONFIG_FILE_PATH)
    # daemon = AnondBotDaemon('/home/mizki/project/anondbot/anondbot.conf', fork=False, dry_run=True)
    daemon.run()
