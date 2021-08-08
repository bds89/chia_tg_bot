from setuptools import setup, find_packages
from os.path import join, dirname
import chia_tg_bot

setup(
    name='chia_tg_bot',
    version=chia_tg_bot.__version__,
    author='bds89',
    author_email='bds89@mail.ru',
    packages=find_packages(),
    long_description=open(join(dirname(__file__), 'README.md')).read(),
    include_package_data=True,
    install_requires=[
        'Flask==2.0.1', 
        'psutil==5.8.0', 
        'python-telegram-bot==13.7', 
        'wakeonlan==2.0.1', 
        'hddtemp==0.1.0'
]
)
