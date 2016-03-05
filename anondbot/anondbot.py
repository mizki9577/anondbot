from configparser import ConfigParser
import sys
import syslog
import time
import traceback

import requests
import iso8601
from requests_oauthlib import OAuth1
from bs4 import BeautifulSoup
from daemon import daemon, pidfile


class AnondArticle:

    '''
    はてな匿名ダイアリーの記事を表現するクラス
    '''

    def __init__(self, item, output):
        self._url = item.link.string
        self._dt = iso8601.parse_date(item.find('dc:date').string)
        self.feed_content = BeautifulSoup(item.find('content:encoded').string, 'html.parser')
        self.output = output
        self.fetched = False

    def fetch(self):
        '''記事を取得する'''
        if self.fetched:
            return

        while True:
            try:
                doc = requests.get(self.url)
            except (requests.ConnectionError, requests.TooManyRedirects) as e:
                self.output(e)
                raise e
            except (requests.HTTPError, requests.Timeout) as e:
                self.output(e)
                self.output('retrying...')
            else:
                try:
                    doc.raise_for_status()
                except requests.HTTPError as e:
                    self.output(e)
                    raise(e)
                else:
                    break

        self.real_content = BeautifulSoup(doc.content, 'html.parser')
        self.fetched = True

    @property
    def title(self):
        '''記事タイトルを返す'''
        self.fetch()
        return self.real_content.find('title').string

    @property
    def trackback_url(self):
        '''トラックバック先の URL を返す'''
        self.fetch()
        tb = self.real_content.find('a', {'class': 'self', 'name': 'tb'})
        if tb:
            return tb['href']
        else:
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
        return self._dt

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return self.url == other.url


class AnondBotDaemon:

    '''
    はてな匿名ダイアリー通知bot
    '''

    CONFIG_FILE_PATH = '/etc/anondbot.conf'
    STATUSES_UPDATE_URL = 'https://api.twitter.com/1.1/statuses/update.json'
    ANOND_FEED_URL = 'http://anond.hatelabo.jp/rss'

    def __init__(self, config_file_path,
                 daemonize=None, dry_run=False, quiet=False):
        self.dry_run = dry_run
        self.daemonize = daemonize
        self.quiet = quiet

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

    def output(self, value):
        value = str(value)
        if self.daemonize:
            syslog.syslog(value)
        elif not self.quiet:
            print(value, file=sys.stdout)

    def run(self):
        '''デーモンを開始する'''
        pid_file = pidfile.PIDLockFile(self.pid_file_path)
        daemon_context = daemon.DaemonContext(
            working_directory='.',
            initgroups=False,
            detach_process=self.daemonize,
            pidfile=pid_file,
            stdout=sys.stdout,
            stderr=sys.stderr)

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

    def get_anond_articles(self):
        '''新着記事の一覧を取得し古い順にリストで返す'''
        self.output('fetching {}'.format(self.ANOND_FEED_URL))
        doc = requests.get(self.ANOND_FEED_URL)
        self.output('fetching finished.')

        soup = BeautifulSoup(doc.content, 'html.parser')
        result = []
        for item in reversed(soup.find_all('item')):
            article = AnondArticle(item, output=self.output)
            result.append(article)

        return result

    def update(self):
        '''新着記事を確認し Twitter に投稿する'''
        articles = self.get_anond_articles()

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
