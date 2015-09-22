from configparser import ConfigParser
import syslog
import time
import datetime
import sys

import requests
from requests_oauthlib import OAuth1
from bs4 import BeautifulSoup
import pep3143daemon as daemon

CONFIG_FILE_PATH = '/etc/anondbot.conf'


class AnondArticle:

    '''
    はてな匿名ダイアリーの記事を表現するクラス
    '''

    def __init__(self, url):
        self._url = url
        self.fetched = False

    def fetch(self):
        if self.fetched:
            return
        doc = requests.get(self.url)
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
        '''記事が他の記事へトラックバックしている場合，その記事の URL を返す'''
        self.fetch()
        try:
            return self.soup.find('a', {'class': 'self', 'name': 'tb'})['href']
        except TypeError:
            return None

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
        return datetime.datetime.strptime(self.id, '%Y%m%d%H%M%S')


class AnondFeed:

    '''
    はてな匿名ダイアリーのフィードを表現するクラス
    '''

    def __init__(self, url):
        doc = requests.get(url)
        self.soup = BeautifulSoup(doc.content, 'html.parser')
        self._url = url

        article_urls = [tag['rdf:resource'] for tag in self.soup.find_all('rdf:li')]
        self._articles = [AnondArticle(article_url) for article_url in article_urls]

    def __len__(self):
        return len(self._articles)

    def __getitem__(self, key):
        return self._articles[key]

    def __iter__(self):
        return iter(self._articles)


class AnondBotDaemon:

    '''
    はてな匿名ダイアリー通知bot
    '''

    STATUSES_UPDATE_URL = 'https://api.twitter.com/1.1/statuses/update.json'
    ANOND_FEED_URL = 'http://anond.hatelabo.jp/rss'

    def __init__(self, config_file_path):
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
        self.pid_file = daemon.PidFile(self.pid_file_path)
        self.daemon = daemon.DaemonContext(pidfile=self.pid_file)

    def run(self):
        '''デーモンを開始する'''
        self.daemon.open()
        while True:
            syslog.syslog('fetching')
            try:
                self.update()
            except Exception as e:
                syslog.syslog(str(e))
                syslog.syslog('exiting')
                sys.exit(1)
            time.sleep(self.interval_sec)

    def update(self):
        '''新着記事を確認し Twitter に投稿する'''
        articles = AnondFeed(self.ANOND_FEED_URL)
        for article in reversed(articles):
            if self.last_article_timestamp >= article.datetime.timestamp():
                continue
            self.last_article_timestamp = int(article.datetime.timestamp())
            if not article.trackback_url:
                self.post_twitter('{} {}'.format(article.title, article.url))

        # 設定の保存
        self.config['config']['last_article_timestamp'] = str(self.last_article_timestamp)
        with open(self.config_file_path, 'w') as f:
            self.config.write(f)

    def post_twitter(self, status):
        requests.post(self.STATUSES_UPDATE_URL, params={'status': status}, auth=self.oauth)
        syslog.syslog(status)


def main():
    daemon = AnondBotDaemon(CONFIG_FILE_PATH)
    daemon.run()

if __name__ == '__main__':
    main()
