import requests
from requests_oauthlib import OAuth1


class TwitterAPI:

    '''
    簡易 Twitter API
    '''

    def __init__(self,
                 oauth=None,
                 consumer_key=None, consumer_secret=None,
                 access_token=None, access_secret=None):
        if oauth is not None:
            self.oauth = oauth
        else:
            self.oauth = OAuth1(client_key=consumer_key,
                                client_secret=consumer_secret,
                                resource_owner_key=access_token,
                                resource_owner_secret=access_secret)

    def call_api(self, method, url, params=None):
        r = requests.request(method, url, params=params, auth=self.oauth)
        response = r.json()
        if 'errors' not in response:
            return response
        for error in response['errors']:
            raise TwitterError.from_code(error['code'], error['message'])

    @property
    def statuses(self):
        return TwitterStatusesAPI(oauth=self.oauth)

    @property
    def help(self):
        return TwitterHelpAPI(oauth=self.oauth)


class TwitterStatusesAPI(TwitterAPI):

    UPDATE_URL = 'https://api.twitter.com/1.1/statuses/update.json'

    def update(self, status):
        return self.call_api('POST', self.UPDATE_URL,
                             params={'status': status})


class TwitterHelpAPI(TwitterAPI):

    CONFIGURATION_URL = 'https://api.twitter.com/1.1/help/configuration.json'

    def configuration(self):
        return self.call_api('GET', self.CONFIGURATION_URL)


class TwitterError(Exception):

    def __init__(self, code, message):
        super().__init__('code {}: {}'.format(code, message))
        self.code = code

    @classmethod
    def from_code(cls, code, message):
        if code == 88:
            return TwitterRateLimitExceeded(code, message)
        if code == 187:
            return TwitterStatusDuplicate(code, message)

        return TwitterError(code, message)


class TwitterRateLimitExceeded(TwitterError):
    pass


class TwitterStatusDuplicate(TwitterError):
    pass
