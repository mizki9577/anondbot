import requests
from requests_oauthlib import OAuth1


class TwitterAPI:

    '''
    簡易 Twitter API
    '''

    STATUSES_UPDATE_URL = 'https://api.twitter.com/1.1/statuses/update.json'
    HELP_CONFIGURATION_URL = \
        'https://api.twitter.com/1.1/help/configuration.json'

    def __init__(self,
                 consumer_key, consumer_secret,
                 access_token, access_secret):
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
            raise TwitterException(error['code'], error['message'])

    def statuses_update(self, status):
        return self.call_api('POST', self.STATUSES_UPDATE_URL,
                             params={'status': status})

    def help_configuration(self):
        return self.call_api('GET', self.HELP_CONFIGURATION_URL)


class TwitterException(Exception):

    def __init__(self, code, message):
        super().__init__('code {}: {}'.format(code, message))
        self.code = code
