import setuptools

setuptools.setup(
    name='anondbot',
    version='1.1.0',
    author='Mizki SUZUMORI',
    author_email='mizki9577@gmail.com',
    license='2-Clause BSD',
    packages=['anondbot'],
    install_requires=[
        'requests',
        'requests_oauthlib',
        'BeautifulSoup4',
        'python-daemon',
        'docopt',
    ],
    entry_points={
        'console_scripts': [
            'anondbotd=anondbot:main'
        ],
    },
)
