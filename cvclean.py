#!/usr/bin/python
from os import path
from shutil import rmtree

if __name__ == '__main__':
    if path.exists('sql_files'):
        rmtree('sql_files')
        print 'deleted sql_files directory'
    if path.exists('cfg_files'):
        rmtree('cfg_files')
        print 'deleted cfg_files directory'
