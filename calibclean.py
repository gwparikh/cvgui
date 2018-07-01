#!/usr/bin/env python
"""
Cleaning Script for the calibration tool
"""
from os import path, remove
from shutil import rmtree
import argparse
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="clean files created by calibration tool")
    parser.add_argument('-nt', '--no-tracking-only-db', action='store_true', dest='notrackingdb', help="Do not Delete Tracking_only.sqlie.")
    args = parser.parse_args()
    if path.exists('sql_files'):
        rmtree('sql_files')
        print('deleted sql_files directory')
    if path.exists('cfg_files'):
        rmtree('cfg_files')
        print('deleted cfg_files directory')
    if not args.notrackingdb:
        if path.exists('tracking_only.sqlite'):
            remove('tracking_only.sqlite')
            print('deleted tracking_only.sqlite')
