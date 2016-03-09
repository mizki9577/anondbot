import json
import logging
import logging.handlers
import os
import os.path
import re
import sys
import time
import traceback
import urllib.parse
from itertools import takewhile

import requests
import iso8601
from bs4 import BeautifulSoup
from daemon import daemon, pidfile

from .twitter import TwitterAPI, TwitterError


class AnondArticle:

    '''
    はてな匿名ダイアリーの記事を表現するクラス
    '''

    def __init__(self, title, url, dt, content, bookmark_count=None):
        self._url = url
        self._dt = dt
        self._content = BeautifulSoup(content, 'html.parser')
        self._title = title
        self._bookmark_count = bookmark_count
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
        if re.search(r'^anond:\d+$', self.title, re.ASCII):
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

    @property
    def bookmark_count(self):
        '''ブクマ数を返す'''
        return self._bookmark_count

    @staticmethod
    def is_anond_article_url(url):
        '''はてな匿名ダイアリーの記事を表す URL であれば True を返す'''
        _, netloc, path, _, _, _ = urllib.parse.urlparse(url)
        return netloc == 'anond.hatelabo.jp' and re.search(r'^\/[0-9]+$', path)


class AnondBotDaemon:

    '''
    はてな匿名ダイアリー通知bot
    '''

    ANOND_FEED_URL = 'http://anond.hatelabo.jp/rss'
    ANOND_HOT_ENTRIES_URL = 'http://b.hatena.ne.jp/entrylist?sort=hot&url=http://anond.hatelabo.jp/&mode=rss'
    TWITTER_CONFIG_FILE_NAME = 'twitter_config.json'

    def __init__(self, config_file_path, cache_dir_path,
                 daemonize=None, dry_run=False, quiet=False):
        self.dry_run = dry_run
        self.daemonize = daemonize
        self.quiet = quiet

        # 設定読み込み
        self.config_file_path = config_file_path
        with open(self.config_file_path, 'r') as f:
            self.config = json.load(f)

        # キャッシュディレクトリの作成
        self.cache_dir_path = cache_dir_path
        if not os.access(self.cache_dir_path, os.R_OK):
            os.mkdir(self.cache_dir_path)
        self.twitter_config_cache_file_path = os.path.join(
            self.cache_dir_path, self.TWITTER_CONFIG_FILE_NAME)

        # Twitter 関係
        self.twitter_api = TwitterAPI(**self.config['twitter'])

        # デーモンの設定
        self.last_article_timestamp = self.config['last_article_timestamp']
        self.last_hot_entries = set(self.config['last_hot_entries'])
        self.interval_sec = self.config['update_interval']
        self.pid_file_path = self.config['pid_file_path']

        # ロガーの設定
        self.logger = logging.getLogger('anondbot')
        self.logger.setLevel(logging.DEBUG)
        if not self.quiet:
            self.logger.addHandler(logging.StreamHandler())

        # Twitter の設定を取得
        self.logger.debug('fetching twitter configuration...')
        try:
            self.twitter_config = self.twitter_api.help.configuration()
        except TwitterError:
            self.logger.info('fetching failed. loading chached configuration...')
            try:
                with open(self.twitter_config_cache_file_path, 'r') as f:
                    json.load(f)
            except FileNotFoundError:
                self.logger.error('loading failed. use default configuration.')
                self.twitter_config = {'short_url_length': 23}
        else:
            self.logger.debug('fetching done.')
            with open(self.twitter_config_cache_file_path, 'w') as f:
                json.dump(self.twitter_config, f)
        self.twitter_config['tweet_length_limit'] = 140

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
                self.logger.debug('starting...')
                while True:
                    self.logger.debug('updating...')
                    self.check_recent_articles()
                    self.check_hot_entries()
                    self.logger.debug('updating done')
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

    def get_hot_entries(self):
        '''注目エントリの一覧を取得しブクマ数順にリストで返す'''
        self.logger.info('fetching {}'.format(self.ANOND_HOT_ENTRIES_URL))
        doc = requests.get(self.ANOND_HOT_ENTRIES_URL)
        self.logger.info('fetching finished.')

        soup = BeautifulSoup(doc.content, 'html.parser')
        items = soup.find_all('item')
        articles = []
        for item in items:
            articles.append(AnondArticle(
                title=item.find('title').string,
                content=item.find('description').string,
                url=item.find('link').string,
                dt=iso8601.parse_date(item.find('dc:date').string),
                bookmark_count=int(item.find('hatena:bookmarkcount').string)
            ))
        articles.sort(key=(lambda x: x.bookmark_count), reverse=True)
        return articles

    def check_hot_entries(self):
        '''ホットエントリを確認し Twitter に投稿する'''
        hot_entries = {
            article.url: article
            for article in takewhile(
                lambda x: x.bookmark_count >= self.config['hot_entry_threshold'],
                self.get_hot_entries()
            )
        }
        changed_hot_entry_urls = hot_entries.keys() - self.last_hot_entries
        self.last_hot_entries = hot_entries.keys()

        for url in changed_hot_entry_urls:
            try:
                self.post_twitter('【注目エントリ】'
                                  + hot_entries[url].title,
                                  hot_entries[url].body, url)
            except TwitterError as e:
                self.logger.error(e.message)

        self.config['last_hot_entries'] = list(self.last_hot_entries)
        with open(self.config_file_path, 'w') as f:
            json.dump(self.config, f, indent='\t')

    def check_recent_articles(self):
        '''新着記事を確認し Twitter に投稿する'''
        articles = self.get_anond_articles()

        for article in articles:
            # 既に Twitter に投稿したものより古い記事はスキップ
            if self.last_article_timestamp >= article.datetime.timestamp():
                continue

            self.last_article_timestamp = article.datetime.timestamp()

            # トラックバックだったらスキップ
            if article.has_trackback:
                continue

            # 本文がNGパターンにマッチしたらスキップ
            if any(re.search(pattern, article.body) is not None
                   for pattern in self.config['ng_patterns']):
                continue

            # Twitter に投稿
            try:
                self.post_twitter(article.title, article.body, article.url)
            except TwitterError as e:
                self.logger.error(e.message)

            # 設定の保存
            self.config['last_article_timestamp'] = self.last_article_timestamp
            with open(self.config_file_path, 'w') as f:
                json.dump(self.config, f, indent='\t')

    def post_twitter(self, title, body, url):
        max_body_length = (
            self.twitter_config['tweet_length_limit']
            - self.twitter_config['short_url_length']
        )
        if len(title):
            max_body_length -= len(title) + 1  # タイトルの後ろのスペース+1
        if len(body):
            max_body_length -= 3  # 本文の後ろのスペース+1, ダブルクォート+2

            body = re.sub(r'\s+', ' ', body.strip())
            if len(body) > max_body_length:
                body = body[:max_body_length-3] + '...'

        status = url
        if len(body):
            status = '"' + body + '" ' + status
        if len(title):
            status = title + ' ' + status

        if not self.dry_run:
            self.twitter_api.statuses.update(status)
        self.logger.info(status)
