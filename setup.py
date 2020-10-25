import os

from setuptools import find_packages, setup

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='kobodl',
    author='Brandon Davis',
    version='0.5.0',
    author_email='kobodl@subdavis.com',
    url="https://github.com/subdavis/kobo-book-downloader",
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'bs4',
        'click',
        'dataclasses',
        'dataclasses-json',
        'flask',
        'pycryptodome',
        'requests',
        'tabulate',
    ],
    license='MIT',
    entry_points={'console_scripts': ['kobodl = kobodl:cli'],},
    python_requires='>=3.6',
    setup_requires=['setuptools-git'],
)
