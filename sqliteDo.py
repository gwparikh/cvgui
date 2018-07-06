#!/usr/bin/env python3

import os, sys, time, argparse, traceback
import sqlite3
from cvguipy import cvgui, trajstorage

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A script to manipulate an sqlite3 database.")
    parser.add_argument('databaseFilename', help="Name of the database file to read")
    parser.add_argument('-ls', dest='listTables', action='store_true', help="List tables in the database and the number of records in each one.")
    parser.add_argument('-y', dest='dontConfirm', action='store_true', help="Skip confirmation before performing an action that will change the database.")
    parser.add_argument('--drop', dest='dropTables', nargs='+', help="Drop the given tables from the database.")
    args = parser.parse_args()
    
    # open the database
    db = trajstorage.CVsqlite(args.databaseFilename)
    
    if args.listTables:
        # get the table info and print it
        tableInfo = db.getTableInfo()
        for tn in sorted(tableInfo.keys()):
            nr = tableInfo[tn]
            print("{}: {} records".format(tn, nr))
    elif len(args.dropTables) > 0:
        # confirm the change
        print("Going to delete tables {} from database '{}'".format(args.dropTables, args.databaseFilename))
        if args.dontConfirm or cvgui.yesno("This action cannot be undone. Are you sure you want to do this? [y/N]"):
            db.dropTables(args.dropTables)
    
    sys.exit(0)
