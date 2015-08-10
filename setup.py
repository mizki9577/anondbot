import setuptools

setuptools.setup(
    name='anondbot',
    version='1.0.0',
    author='Mizki SUZUMORI <mizki9577@gmail.com>',
    license='2-Clause BSD',
    packages=['anondbot'],
    install_requires=['requests', 'requests_oauthlib', 'BeautifulSoup4', 'pep3143daemon'],
    entry_points={
        'console_scripts': [
            'anondbotd=anondbot:main'
        ],
    },
)

