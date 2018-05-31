#!/usr/bin/env python

from os import path, remove
from shutil import rmtree

if __name__ == '__main__':
    if path.exists('sql_files'):
        rmtree('sql_files')
        print('deleted sql_files directory')
    if path.exists('cfg_files'):
        rmtree('cfg_files')
        print('deleted cfg_files directory')
    if path.exists('tracking_only.sqlite'):
        remove('tracking_only.sqlite')
        print('deleted tracking_only.sqlite')
