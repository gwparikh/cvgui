#!/usr/bin/env python3

import os, sys, glob
from datetime import datetime
import argparse, argcomplete, textwrap, subprocess
from cvguipy import cvgui

appDir = os.path.dirname(__file__)
defaultConfig = os.path.join(appDir, 'tracking.cfg')

def find_file(withstr, fext='txt', fdir=os.getcwd(), ignoreCase=True): #, askIfMultiple=True):
    flist = glob.glob(os.path.join(fdir,"*.{}".format(fext)))
    for f in flist:
        ws, fs = withstr, os.path.basename(f)
        if ignoreCase:
            ws, fs = ws.lower(), fs.lower()
        if ws in fs:
            return f
    return ''

# TODO update this to be accurate
if __name__ == '__main__':
    parser = argparse.ArgumentParser(usage='%(prog)s [options] filename',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent("Extract trajectories from a single video file into a like-named sqlite database file using TrafficIntelligence. If there are any homography files (.txt files with 'homography' in their name, mask images (.png or .jpg files with 'mask' in their anem, or TrafficIntelligence configuration files (.cfg files with 'tracking' in their name) in the same directory as the video file, and no files are specified via arguments, the first of each qualifying file will be automatically used."))
    parser.add_argument('inputFile', help = "Video file to process. Output databases will be named by taking the input video filename and replacing the extension with 'sqlite', unless otherwise specified. Unless the '-y' flag is provided, the user must confirm before a file with the same name is overwritten (alternatively the -n flag will skip it without asking).")
    parser.add_argument('-t', '--traffintel-config', dest='traffintelConfigFile', help = "Location of the TrafficIntelligence configuration file (tries to find one in the video directory by default, otherwise uses {})".format(defaultConfig))
    parser.add_argument('-d', '--database-file', dest='databaseFile', help="Name of the database file to create (you must include the '.sqlite' extension). If not provided, one is generated automatically from the input video")
    parser.add_argument('-o', '--homography-file', dest='homographyFile', help = 'Location of the homography file for projecting between world space and image space (REQUIRED and UNIQUE to a specific camera placement.')
    parser.add_argument('-m', '--mask-filename', dest='maskFilename', help = "Mask image file to use when performing feature tracking (optional).")
    parser.add_argument('--tf', '--track-features-only', dest='trackFeaturesOnly', action = 'store_true', help = "Only run feature TRACKING, not feature grouping.")
    parser.add_argument('--gf', '--group-features-only', dest='groupFeaturesOnly', action = 'store_true', help = "Only run feature GROUPING, not feature tracking.")
    parser.add_argument('-O', '--output-dir', dest = 'outputDir', help = 'Directory to place output files.')
    parser.add_argument('-y', '--overwrite-files', dest='overwriteFiles', action = 'store_true', help = 'If a video file will be processed into a database with a name that already exists, delete the old database without asking for confirmation.')
    parser.add_argument('-n', '--dont-overwrite-files', dest='dontOverwriteFiles', action = 'store_true', help = 'If a video file will be processed into a database with a name that already exists, exit and do nothing without asking for confirmation.')
    parser.add_argument('-x', '--exe-path', dest='exePath', default = 'feature-based-tracking', help = "Location of the TrafficIntelligence binary feature-based-tracking (defaults to 'feature-based-tracking' in the user's $PATH.")
    parser.add_argument('-l', '--time-log', dest='timeLog', action = 'store_true', help = "Log the amount of time taken to process each file in a file named <videofile>.trktime.")
    
    # TODO this doesn't work?
    #argcomplete.autocomplete(parser)
    args = parser.parse_args()
    maskFilename = args.maskFilename
    
    # don't do anything if the file doesn't exist
    if os.path.exists(args.inputFile):
        # make some filenames
        fdir = os.path.dirname(args.inputFile)                  # directory, so we can look for the homography
        fname, fext = os.path.splitext(args.inputFile)
        if 'avi' in fext:
            vidfn = args.inputFile
            ovidfn = ''
            logfn = fname + '.trktime'
            
            # label the database with _features if we're only doing tracking
            if args.trackFeaturesOnly:
                dbfn = fname + '_features.sqlite'
            else:
                dbfn = fname + '.sqlite'
                
            # output to outputDir if specified
            if args.outputDir is not None:
                dbfn = os.path.join(args.outputDir, dbfn)
                print("Output will be written to {}".format(dbfn))
        
        if args.databaseFile is not None:
            dbfn = args.databaseFile
        
        if args.outputDir is not None:
            logfn = os.path.join(args.outputDir, logfn)
        
        # if they didn't tell us what homography to use, try to look for one in the same directory as the file
        homographyFile = find_file('homography', 'txt', fdir) if args.homographyFile is None else args.homographyFile
        print("Using homography file {}...".format(homographyFile))
        
        # if they didn't tell us what mask to use, try to look for one in the same directory as the file
        maskFilename = find_file('mask', 'png', fdir) if maskFilename is None else maskFilename
        maskFilename = find_file('mask', 'jpg', fdir) if maskFilename == '' else maskFilename
        print("Using mask file {}...".format(maskFilename))
        
        # look for a tracking config file in the file's directory
        traffintelConfigFile = find_file('tracking', 'cfg', fdir) if args.traffintelConfigFile is None else args.traffintelConfigFile # ignores case by default
        if traffintelConfigFile == '':
            traffintelConfigFile = defaultConfig
        print("Using TrafficIntelligence configuration file {}...".format(traffintelConfigFile))
        
        # make sure the config file and homography file exist, otherwise exit with error
        filesExist = True
        if not os.path.exists(traffintelConfigFile):
            print("Error! The TrafficIntelligence configuration file {} could not be found! It is required to run trajectory extraction!".format(traffintelConfigFile))
            filesExist = False
        if not os.path.exists(homographyFile):
            print("Error! The homography file {} could not be found! It is required for all operations!".format(homographyFile))
            filesExist = False
        if not filesExist:
            sys.exit(2)
        
        # check if the output file exists and decide what to do
        doit = True
        fExists = None
        if os.path.exists(dbfn):
            fExists = dbfn
        if fExists is not None:
            if args.dontOverwriteFiles:
                print("File {} exists! Skipping...".format(fExists))
                doit = False
            elif args.groupFeaturesOnly:
                print("Grouping features directly into input database {}...".format(fExists))
            else:
                doit = cvgui.yesno("File {} exists! Overwrite? [y/N]".format(fExists))
                if doit:
                    print("Removing old file {}...".format(fExists))
                    os.remove(fExists)
            
        if doit:
            print("Extracting trajectories from video file {}...".format(vidfn))
            startTime = datetime.now()
            
            # format command (casting everything to string since otherwise subprocess will complain)
            cmd = [args.exePath, '--config-file', traffintelConfigFile, '--homography-filename', homographyFile, '--video-filename', vidfn, '--database-filename', dbfn]
            if maskFilename is not None:
                    cmd += ['--mask-filename', maskFilename]
            cmd = list(map(str, cmd))
            if not args.groupFeaturesOnly:
                subprocess.call(cmd + ['--tf'])       # run feature tracking
            tfTime = datetime.now() - startTime
            if not args.trackFeaturesOnly:
                subprocess.call(cmd + ['--gf'])       # run feature grouping
            totTime = datetime.now() - startTime
            gfTime = totTime - tfTime
            
            # feature tracking time, feature grouping time, total time
            tLogStr = "{},{},{}\n".format(tfTime,gfTime,totTime)
            print("Trajectory extraction completed in {}!".format(totTime))
            
            with open(logfn, 'w') as tlf:
                tlf.write(tLogStr)
            sys.exit(0)
    else:
        print("Input file {} does not exist! Exiting...".format(args.inputFile))
        sys.exit(1)
    