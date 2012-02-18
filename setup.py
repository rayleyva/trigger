#!/usr/bin/env python

# Copyright, 2005-2011 AOL Inc.

try:
    from setuptools import setup, find_packages, Command
except ImportError:
    raise SystemExit('We require setuptools. Sorry! Install it and try again: http://pypi.python.org/pypi/setuptools')
import glob
import os
import sys
import unittest

# Get version from pkg index
from trigger import release as __version__

# Names of required packages
requires = [
    'IPy>=0.73',
    'Twisted',
    'pycrypto',
    'pytz',
    'SimpleParse',
    'redis', # The python interface, not the daemon!
]

class CleanCommand(Command):
    user_options = []
    def initialize_options(self):
        self.cwd = None
    def finalize_options(self):
        self.cwd = os.getcwd()
    def run(self):
        assert os.getcwd() == self.cwd, 'Must be in package root: %s' % self.cwd
        os.system ('rm -rf ./build ./dist ./*.pyc ./*.tgz ./*.egg-info')

class TestCommand(Command):
    user_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        # Set up environment to point to mockup files.
        test_path = os.path.join(os.getcwd(), 'tests', 'data')
        os.environ['NETDEVICESXML_FILE'] = \
            os.path.join(test_path, 'netdevices.xml')
        os.environ['AUTOACL_FILE'] = os.path.join(test_path, 'autoacl.py')
        os.environ['TACACSRC'] = os.path.join(test_path, 'tacacsrc')
        os.environ['TACACSRC_KEYFILE'] = os.path.join(test_path, 'tackf')

        # Run each .py file found under tests/.
        args = [unittest.__file__]
        for root, dirs, files in os.walk('tests'):
            for file in files:
                if file.endswith('.py'):
                    args.append(os.path.join(root, file[:-3]))
        unittest.main(None, None, args)

desc = 'Trigger is a framework and suite of tools for configuring network devices'
long_desc = '''
Trigger is a framework for communicating with network devices that was written
by the Network Security team at AOL to enhance management of security policies
on network devices. It was written in Python utilizing the freely available
Twisted Matrix event-driven networking engine. The libraries can connect to
network devices by any available method (e.g. telnet, ssh), communicate with
them in their native interface (e.g. Juniper JunoScript, Cisco IOS), and return
output. Utilizing the Twisted framework, Trigger is able to manage any number of
jobs in parallel and handle output or errors as they return. With the high
number of network devices on the AOL network this application is invaluable to
performance and reliability. 
'''

setup(
    name='trigger',
    version=__version__,
    author='Jathan McCollum',
    author_email='jathan@gmail.com',
    packages=find_packages(exclude='tests'),
    license='BSD',
    url='https://github.com/aol/trigger',
    description=desc,
    long_description=long_desc,
    scripts=[
        'bin/acl',
        'bin/acl_script',
        'bin/aclconv',
        'bin/check_access',
        'bin/fe',
        'bin/gong',
        'bin/gnng',
        'bin/load_acl',
        'bin/netdev',
        'bin/optimizer',
        'bin/find_access',
        'tools/gen_tacacsrc.py',
        'tools/convert_tacacsrc.py',
        'tools/tacacsrc2gpg.py',
    ],
    include_package_data=True,
    install_requires=requires,
    cmdclass={
        'test': TestCommand,
        'clean': CleanCommand
    }
)
