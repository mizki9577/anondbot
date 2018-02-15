import setuptools

setuptools.setup(
    name='anondbot',
    version='1.2.7',
    author='Mizki SUZUMORI',
    author_email='suzumorimizuki@gmail.com',
    description='Twitter bot daemon which notifies recent articles of Hatena Anonymous Diary.',
    license='2-Clause BSD',
    packages=['anondbot'],
    install_requires=[
        'requests',
        'requests_oauthlib',
        'BeautifulSoup4',
        'python-daemon',
        'docopt',
        'iso8601',
    ],
    entry_points={
        'console_scripts': [
            'anondbot=anondbot:main'
        ],
    },
)
