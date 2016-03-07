import json
import logging
import re
import sys
import time
import traceback
import urllib.parse

import requests
import iso8601
from requests_oauthlib import OAuth1
from bs4 import BeautifulSoup
from daemon import daemon, pidfile


class AnondArticle:

    '''
    はてな匿名ダイアリーの記事を表現するクラス
    '''

    def __init__(self, title, url, dt, content):
        self._url = url
        self._dt = dt
        self._content = BeautifulSoup(content, 'html.parser')
        self._title = title
        self.logger = logging.getLogger('anondbot')

    @property
    def title(self):
        '''記事タイトルを返す'''
        if re.search(r'^(■|\s+)$', self._title):
            return ''
        return self._title

    @property
    def body(self):
        '''記事本文を返す'''
        return self._content.get_text()

    @property
    def has_trackback(self):
        '''トラックバック先の記事があれば True を返す'''
        if self.is_anond_article_url(self.title):
            return True

        links = self._content.find_all('a')
        for link in links:
            if self.is_anond_article_url(link['href']):
                return True

        return False

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

    @staticmethod
    def is_anond_article_url(url):
        '''はてな匿名ダイアリーの記事を表す URL であれば True を返す'''
        _, netloc, path, _, _, _ = urllib.parse.urlparse(url)
        return netloc == 'anond.hatelabo.jp' and re.search(r'^\/[0-9]+$', path)

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return self.url == other.url


class AnondBotDaemon:

    '''
    はてな匿名ダイアリー通知bot
    '''

    CONFIG_FILE_PATH = '/etc/anondbotrc'
    ANOND_FEED_URL = 'http://anond.hatelabo.jp/rss'

    def __init__(self, config_file_path,
                 daemonize=None, dry_run=False, quiet=False):
        self.dry_run = dry_run
        self.daemonize = daemonize
        self.quiet = quiet

        # 設定読み込み
        self.config_file_path = config_file_path
        with open(self.config_file_path, 'r') as f:
            self.config = json.load(f)

        # Twitter 関係
        self.twitter_api = TwitterAPI(**self.config['twitter'])

        # デーモンの設定
        self.last_article_timestamp = self.config['config']['last_article_timestamp']
        self.interval_sec = self.config['config']['update_interval']
        self.pid_file_path = self.config['config']['pid_file_path']

        # Twitter の設定を取得
        self.twitter_config = self.twitter_api.help_configuration()
        self.twitter_config['tweet_length_limit'] = 140

        # ロガーの設定
        self.logger = logging.getLogger('anondbot')
        self.logger.setLevel(logging.DEBUG)
        if self.daemonize:
            self.logger.addHandler(logging.handlers.SysLogHandler())
        elif not self.quiet:
            self.logger.addHandler(logging.StreamHandler())

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
            self.logger.info('exiting request received. exiting...')
            raise e
        except KeyboardInterrupt as e:
            self.logger.info('exiting request received. exiting...')
            sys.exit()
        except:
            self.logger.critical(traceback.format_exc())
            self.logger.critical('error(s) occured. exiting...')
            sys.exit(1)

    def get_anond_articles(self):
        '''新着記事の一覧を取得し古い順に返すジェネレータを返す'''
        self.logger.info('fetching {}'.format(self.ANOND_FEED_URL))
        doc = requests.get(self.ANOND_FEED_URL)
        self.logger.info('fetching finished.')

        soup = BeautifulSoup(doc.content, 'html.parser')
        for item in reversed(soup.find_all('item')):
            yield AnondArticle(
                title=item.find('title').string,
                content=item.find('content:encoded').string,
                url=item.find('link').string,
                dt=iso8601.parse_date(item.find('dc:date').string)
            )

    def update(self):
        '''新着記事を確認し Twitter に投稿する'''
        articles = self.get_anond_articles()

        for article in articles:
            if self.last_article_timestamp >= article.datetime.timestamp():
                continue

            self.last_article_timestamp = article.datetime.timestamp()

            if not article.has_trackback:
                max_body_length = (
                    self.twitter_config['tweet_length_limit']
                    - self.twitter_config['short_url_length']
                    - 3  # 本文ダブルクォート*2 + 本文とURLの間のスペース
                )
                if article.title != '':
                    max_body_length -= len(article.title) + 1  # タイトルと本文の間のスペース

                body = re.sub(r'\s+', ' ', article.body.strip())
                if len(body) > max_body_length:
                    body = body[:max_body_length-3] + '...'

                status = '"{}" {}'.format(body, article.url)
                if article.title != '':
                    status = article.title + ' ' + status
                self.post_twitter(status)

            # 設定の保存
            self.config['config']['last_article_timestamp'] = self.last_article_timestamp
            with open(self.config_file_path, 'w') as f:
                json.dump(self.config, f, indent='\t')

    def post_twitter(self, status):
        if not self.dry_run:
            self.twitter_api.statuses_update(status)
        self.logger.info(status)


class TwitterAPI:

    '''
    簡易 Twitter API
    '''

    STATUSES_UPDATE_URL = 'https://api.twitter.com/1.1/statuses/update.json'
    HELP_CONFIGURATION_URL = 'https://api.twitter.com/1.1/help/configuration.json'

    def __init__(self,
                 consumer_key, consumer_secret,
                 access_token, access_secret):
        self.oauth = OAuth1(client_key=consumer_key,
                            client_secret=consumer_secret,
                            resource_owner_key=access_token,
                            resource_owner_secret=access_secret)

    def call_api(self, method, url, params=None):
        r = requests.request(method, url, params=params, auth=self.oauth)
        return r.json()

    def statuses_update(self, status):
        return self.call_api('POST', self.STATUSES_UPDATE_URL,
                             params={'status': status})

    def help_configuration(self):
        return self.call_api('GET', self.HELP_CONFIGURATION_URL)
