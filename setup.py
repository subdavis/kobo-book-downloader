import os

from setuptools import find_packages, setup

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='kobodl',
    author='Brandon Davis',
    version='0.7.2',
    author_email='kobodl@subdavis.com',
    url="https://github.com/subdavis/kobo-book-downloader",
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'beautifulsoup4<5.0.0',
        'click<8',
        'dataclasses<1.0.0',
        'dataclasses-json<0.6.0',
        'flask>=1.1.0',
        'pycryptodome<4',
        'pyperclip',
        'requests>=2.25',
        'tabulate<0.9.0',
    ],
    license='MIT',
    entry_points={
        'console_scripts': ['kobodl = kobodl:cli'],
    },
    python_requires='>=3.6',
    setup_requires=['setuptools-git'],
)
