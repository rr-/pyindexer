from setuptools import setup, find_packages

setup(
    author='rr-',
    author_email='rr-@sakuya.pl',
    name='webindexer',
    long_description='Simple file indexer for web/WSGI',
    packages=find_packages(),
    package_dir={'webindexer': 'webindexer'},
    package_data={'webindexer': ['data/*']},

    install_requires=[
        'uwsgi',
        'jinja2',
        'Pillow',
        'pyramid',
        'xdg',
    ])
