#!/usr/bin/python

import os, time, datetime
import threading, Queue, multiprocessing
import sqlite3, gzip, shutil, hashlib, re, tempfile
from socket import gethostname
from urlparse import urlparse
from collections import OrderedDict
import numpy as np
import cvmoving

def md5hash(fname):
    """Calculate the md5 hash on a file."""
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def gunzip(gzipFile, ofname=None, tmpfs='/dev/shm/'):
    # make the output file name
    ofname = os.path.join(tmpfs, os.path.splitext(gzipFile)[0]) if ofname is None else ofname
    with gzip.open(gzipFile, 'rb') as gzf, open(ofname, 'wb') as of:
        of.write(gzf.read())
    return ofname

def drainQueue(q):
    out = []
    while not q.empty():
        try:
            o = q.get(block=False)
            out.append(o)
        except Queue.Empty:
            break
    return out

class ZipTraj(object):
    """
    A class holding a compressed representation of a trajectory
    as an initial point followed by the position of each point 
    relative to the previous point (so the first derivative),
    with values limited to a fixed precision. This is meant to
    hold the same information as a normal trajectory (where all
    values are in a common reference frame), but without using
    so much space.
    """
    def __init__(self, traj=None, precision=0.01, truncate=False):
        self.traj = np.array(traj)
        self.precision = precision
        self.truncate = truncate
    
    def __repr__(self):
        return str(self.asArray())
    
    def __eq__(self, zt):
        if isinstance(zt, ZipTraj):
            return np.all(self.asArray() == zt.asArray())
        elif isinstance(zt, np.ndarray):
            return np.all(self.asArray() == zt)
    
    @classmethod
    def fromTrajectory(cls, traj, **kwargs):
        a = np.array([p.astuple() for p in traj])
        
        # save the first value
        p0 = a[0,:]
        
        # calculate relative values
        al = a[0:-1,:]
        ar = a[1:,:]
        rv = ar - al
        
        return ZipTraj(np.vstack([p0, rv]), **kwargs)
    
    @classmethod
    def fromCompressed(cls, zt, precision=0.01, **kwargs):
        return ZipTraj(np.array(zt)*precision, precision=precision, **kwargs)
    
    def asArray(self):
        if self.traj is not None:
            return np.cumsum(self.traj,axis=0)
    
    def asTrajectory(self, compressed=False):
        traj = self.compressed() if compressed else self.asArray()
        if traj is not None:
            pl = [(x,y) for x,y in traj]
            return cvmoving.Trajectory.fromPointList(pl)
    
    def compressed(self):
        """
        Return a copy of the trajectory with values limited to the precision
        specified in self.precision. Note that the values returned will be as
        integers with a higher order of magnitude.
        """
        if self.traj is not None:
            t = np.array(self.traj/self.precision)
            t = np.trunc(t) if self.truncate else np.round(t)
            return np.int64(t)

def getStoragePrecision(cameraFramePrecision, maxValue, error=0.005, nMeasures=1000, maxIters=100):
    """
    Return the order of magnitude that suitably represents the cameraFramePrecision
    specified to a maximum accumulated error of error percent of maxValue over nMeasures
    measurements (stops at maxIters if that can't be reached)
    """
    i = 0
    e = np.inf
    while e > error and i < maxIters:
        o = 10**(np.floor(np.log10(cameraFramePrecision))-i)
        e = abs((cameraFramePrecision-o*round(cameraFramePrecision/o))/cameraFramePrecision)*nMeasures/maxValue
        i += 1
    return o

class GZfile(object):
    """A class for managing writable, gzipped file."""
    def __init__(self, filename, tmpfs='/dev/shm'):
        self.filename = filename
        self.tmpfs = tmpfs
        self.fname, self.fext = os.path.splitext(os.path.basename(filename))
        self.isZipped = self.fext == '.gz'
        self.tmpFilename = ''
        self.tmpFile = None
        self.md5 = None
        self.open()
        
    def __repr__(self):
        return "<GZfile {} - {}zipped, readable file at {}>".format(self.filename, 'not ' if not self.isZipped else '', self.tmpFilename)
        
    def getFileName(self):
        return self.tmpFilename
        
    def inflate(self):
        """Inflate (unzip) the file to the tmpfs so it can be read by other things."""
        if self.isZipped:
            self.tmpFilename = os.path.join(self.tmpfs, self.fname)
            #self.tmpFile = tempfile.NamedTemporaryFile(
            with gzip.open(self.filename, 'rb') as gzf, open(self.tmpFilename, 'wb') as odbf:
                odbf.write(gzf.read())
        else:       # if it's not zipped, its already inflated
            self.tmpFilename = self.filename
    
    def deflate(self):
        """Deflate (zip) the file to the disk, overwriting the original file."""
        # write to a temporary zip file in tmpfs
        tmpzip = os.path.join(self.tmpfs, self.tmpFilename + '.gz')
        with gzip.open(tmpzip, 'wb') as ogzf, open(self.tmpFilename, 'rb') as dbf:
            ogzf.write(dbf.read())
        
        # replace the original file and delete the temp file
        shutil.copy(tmpzip, self.filename)
        os.remove(tmpzip)
        
    def open(self):
        """'Open' a gzipped file. If the file is zipped (gzip format),
        it will be unzipped to a temporary file in /dev/shm."""
        self.inflate()
        if self.isZipped:                       # calculate the md5 hash of the original file when we open it so we can know if it has changed
            self.md5 = md5hash(self.tmpFilename)
        
    def close(self):
        """'Close' a gzipped file, re-zipping and replacing the original
           file if it has changed."""
        if self.isZipped:
            # check the md5 hash to see if the file has changed
            md5 = md5hash(self.tmpFilename)
            if md5 != self.md5:
                self.deflate()          # if it has, deflate it
            os.remove(self.tmpFilename)       # then remove the temp file

class CVsqlite(object):
    """A class for interacting with an sqlite database of computer vision data."""
       
    def __init__(self, filename, withFeatures=True, objTablePrefix=None, homography=None, invHom=None, withImageBoxes=False, allFeatures=False, objFetchSize=10, compressed=False, precision=0.01):
        self.filename = filename
        self.withFeatures = withFeatures
        self.objTablePrefix = objTablePrefix.rstrip('_') if objTablePrefix is not None else ''
        self.homography = homography
        self.invHom = invHom
        self.withImageBoxes = withImageBoxes
        self.allFeatures = allFeatures
        self.objFetchSize = objFetchSize
        self.compressed = compressed
        self.precision = precision
        
        self.fname, self.fext = os.path.splitext(os.path.basename(filename))
        self.isZipped = self.fext == '.gz'
        self.gzdb = None
        self.dbFile = None
        self.features = []
        self.objects = []
        self.imageObjects = []
        self.objectFeatures = []
        self.annotations = []
        self.tableInfo = {}
        self.lastFrame = None
        self.firstObjId, self.lastObjId = -1, -1
        
        self.thread = None
        self.objectQueue = multiprocessing.Queue()
        self.featureQueue = multiprocessing.Queue()
        self.imageObjectQueue = multiprocessing.Queue()
        
        # check filename to see if data is compressed with ZipTraj
        if '%' in self.fname:
            precSufx = self.fname.split('%')
            if len(precSufx) > 1 and 'p' in precSufx[1]:
                pstr = precSufx[1].split('p')[0]
                try:
                    self.precision = float(pstr)
                    self.compressed = True
                except ValueError:
                    print "Error reading precision value from filename {} !"
                    print "The % character is used to indicate compression with the "
                    print "ZipTraj class, so you may not want to use it for other things."
        self.open()
        
    def __repr__(self):
        s = "<CVsqlite DB '{}'".format(self.dbFile)
        if len(self.objects) > 0:
            s += " - {} objects".format(len(self.objects))
            if len(self.features) > 0:
                s += ", {} features>".format(len(self.features))
        else:
            # print table info if we haven't loaded objects yet
            s += " - Tables:".format(self.dbFile)
            tableInfo = self.getTableInfo()
            if len(tableInfo) == 0:
                s += ' None>'
            else:
                for tableName, nRecords in tableInfo.iteritems():
                    s += " '{}' ({} records),".format(tableName, nRecords)
                s = s.strip(',') + '>'
        return s
        
    def buildTrajectories(self, cursor, featureNumbers=None, returnDict=False):
        """
        Build a list of position and velocity trajectories (features or objects) 
        from a database cursor. You must execute a query on the cursor before 
        executing this function.
        """
        # initialize
        objId = -1
        obj = None
        trajectories = {} if returnDict else []
        
        # iterate over the rows in the query result
        currentObjId = None
        positions = []
        velocities = []
        firstInstant, lastInstant = 0, -1
        for row in cursor:
            objId, i, x, y, vx, vy = row
            if objId != currentObjId:         # if the object ID is different, we should start a new object
                if len(positions) > 0:
                    # construct object that has ended and place in trajectories
                    # if the trajectories are compressed and at a fixed precision,
                    # they will be transformed into floating point values
                    obj = cvmoving.MovingObject.fromTableRows(currentObjId, firstInstant, lastInstant, positions, velocities, featureNumbers=featureNumbers, compressed=self.compressed, precision=self.precision)
                    if returnDict:
                        trajectories[currentObjId] = obj
                    else:
                        trajectories.append(obj)
                    positions = []
                    velocities = []
                
                currentObjId = objId
                firstInstant = i
            lastInstant = i
            positions.append((x,y))
            velocities.append((vx,vy))
        
        # add the last object to the list
        if len(positions) > 0:
            obj = cvmoving.MovingObject.fromTableRows(currentObjId, firstInstant, lastInstant, positions, velocities, featureNumbers=featureNumbers, compressed=self.compressed, precision=self.precision)
            if returnDict:
                trajectories[currentObjId] = obj
            else:
                trajectories.append(obj)
        return trajectories
    
    def getVideoFilename(self):
        """Return the name of the video file used to create this database
           (the name of the database with '.sqlite' replaced with '.avi')."""
        return self.dbFile.replace('.sqlite', '.avi')
    
    def open(self):
        """Open the database, unzipping it first if necessary."""
        if self.isZipped:
            self.gzdb = GZfile(self.filename)
            self.dbFile = self.gzdb.getFileName()
        else:
            self.dbFile = self.filename
        self.connection = sqlite3.connect(self.dbFile)
        
    def close(self):
        """Commit and close the database. If the file has been changed, the GZfile class will know and will handle it."""
        self.connection.commit()
        if self.isZipped:
            self.gzdb.close()
    
    def compressTrajectories(self, precision=None):
        """
        Copy all feature and object data to a new database that uses a relative-
        position/velocity trajectory encoding scheme with fixed precision for 
        improved storage efficiency. The new database will have the same name
        as the existing database, but with %0.XXp appended before the filename,
        where 0.XX is the precision of the data in world units (0.01 by default),
        e.g. 'sample%0.01p.sqlite'
        
        Note that the values in the new database will not be meaningful by themselves
        in the same way that uncompressed values are. For more details on how this
        all works, see the ZipTraj class, which handles encoding trajectories in the
        new scheme.
        """
        precision = self.precision if precision is None else precision
        newfn = "{}%{}p".format(self.fname, precision) + self.fext
        
        # create a new CVsqlite class instance with compression turned on
        print "Outputting compressed trajectories to file '{}' ...".format(newfn)
        cdb = CVsqlite(newfn, compressed=True, precision=precision)
        
        # write features and objects to the new database
        if len(self.features) == 0:
            self.loadFeatures()
        print "Writing {} features to database...".format(len(self.features))
        fSuccess = cdb.writeFeatures(self.features)
        print "Success!" if fSuccess else "Failed to write features!"
        if len(self.objects) == 0:
            self.loadObjects(objTablePrefix=None)
        print "Writing {} objects to database...".format(len(self.objects))
        oSuccess = cdb.writeObjects(self.objects, tablePrefix=None)
        print "Success!" if oSuccess else "Failed to write objects!"
        return fSuccess and oSuccess
    
    def getLastFrame(self):
        cursor = self.connection.cursor() 
        self.lastFrame = None
        try:
            cursor.execute("SELECT MAX(frame_number) FROM positions;")
            self.lastFrame = cursor.fetchall()[0][0]
        except sqlite3.OperationalError as error:
            print error
            print "Could not get last frame number from database {}!".format(self.dbFile)
        return self.lastFrame
    
    def getTableInfo(self):
        cursor = self.connection.cursor() 
        
        # list the tables in the database
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tableNames = [tn[0] for tn in cursor]
            
            # go through the tables and get the number of records in each
            self.tableInfo = {}
            for tn in tableNames:
                cursor.execute("SELECT COUNT(*) FROM {}".format(tn))
                nrecords = cursor.fetchall()[0][0]
                self.tableInfo[tn] = nrecords
                #print "{} - {} records".format(tn, nrecords)
            return self.tableInfo
        except sqlite3.OperationalError as error:
            print error
            print "Could not get table info from database {}!".format(self.dbFile)

    def dropTables(self, tableNames):
        """Drop (delete) the table from the database."""
        if isinstance(tableNames, str):
            tableNames = [tableNames]
        
        cursor = self.connection.cursor()
        
        try:
            for tn in tableNames:
                cursor.execute("DROP TABLE IF EXISTS {}".format(tn))
        except sqlite3.OperationalError as error:
            print error
            print "Error dropping table '{}' from database '{}'".format(self.dbFile, tableName)

    def getFrameList(self):
        cursor = self.connection.cursor()
        
        try:
            cursor.execute('SELECT DISTINCT frame_number from positions ORDER BY frame_number ASC;')
            frames = [n[0] for n in cursor.fetchall()]
            #return frames[-1] + 1       # number of frames is highest frame number (plus 1 b/c of 0 index)
            return frames
        except sqlite3.OperationalError as error:
            print error
            print "Could not get frames from database {}!".format(self.dbFile)
    
    def computeClearMOT(self, matchDistance):
        """Compute the ClearMOT tracking performance metrics.
           
           Output: returns motp, mota, mt, mme, fpt, gt
             + mt (missed tracks?):  number of missed ground truth frames (sum of the number of GT not detected in each frame)
             + mme: number of mismatches
             + fpt: number of false positive frames (tracker objects without match in each frame)
             + gt:  number of ground truth frames
        """
        # get the frame limits, then calculate the metrics
        self.frameNumbers = self.getFrameList()
        if len(self.frameNumbers) > 0:
            firstFrame = self.frameNumbers[0]
            lastFrame = self.frameNumbers[-1]
    
    def update(self):
        """
        Update the object lists from the queues.
        """
        for f in drainQueue(self.featureQueue):
            self.features.append(f)
        for o in drainQueue(self.objectQueue):
            self.objects.append(o)
        for io in drainQueue(self.imageObjectQueue):
            self.imageObjects.append(io)
    
    def loadObjectsInThread(self, sameProcess=False):
        """
        Load and construct objects (and image objects) in a process, passing them into a queue
        as they are finished
        """
        # create a process and start it
        threadType = multiprocessing.Process if not sameProcess else threading.Thread
        self.thread = threadType(target=self._loadObjects, kwargs={'useQueue': True}, name='ObjectLoader')
        self.thread.daemon = True
        self.thread.start()
        
        if self.allFeatures:
            self.featureDB = CVsqlite(self.filename, withFeatures=self.withFeatures, objTablePrefix=self.objTablePrefix, homography=self.homography, invHom=self.invHom, withImageBoxes=self.withImageBoxes, allFeatures=self.allFeatures, objFetchSize=self.objFetchSize, compressed=self.compressed, precision=self.precision)
            self.featureDB.featureQueue = self.featureQueue
            self.featureDB.loadFeaturesInThread()
    
    def loadFeaturesInThread(self, sameProcess=False):
        """
        Load and construct features in a process, passing them into a queue
        as they are finished
        """
        # create a process and start it
        threadType = multiprocessing.Process if not sameProcess else threading.Thread
        self.thread = threadType(target=self._loadFeatures, kwargs={'useQueue': True}, name='FeatureLoader')
        self.thread.daemon = True
        self.thread.start()
        
    def loadFeatures(self):
        """Load feature positions and velocities from the database."""
        self._loadFeatures(useQueue=False)
        
    def _loadFeatures(self, useQueue=True):
        """Load feature positions and velocities from the database into a multiprocessing.Queue."""
        cursor = self.connection.cursor()
        
        # load position and velocities
        pvQuery = '''SELECT p.trajectory_id,
                         p.frame_number,
                         p.x_coordinate,
                         p.y_coordinate,
                         v.x_coordinate,
                         v.y_coordinate
                       FROM 'positions' p,'velocities' v
                       WHERE p.trajectory_id=v.trajectory_id
                         AND p.frame_number=v.frame_number
                       ORDER BY p.trajectory_id,p.frame_number;'''
        cursor.execute(pvQuery)
        self.features = self.buildTrajectories(cursor)
        if useQueue:
            for f in self.features:
                self.featureQueue.put(f)
        
    def loadObjects(self, objTablePrefix=None):
        """
        Load object positions and velocities from the database into a list. Any objTablePrefix
        provided here will overwrite the object's current objTablePrefix property.
        """
        if objTablePrefix is not None:
            self.objTablePrefix = objTablePrefix
        self._loadObjects(useQueue=False)
        
    def _loadObjects(self, useQueue=True):
        """Load object positions and velocities from the database into a multiprocessing.Queue."""
        # make the object (object feature numbers) table name
        otp = self.objTablePrefix + '_' if len(self.objTablePrefix) > 0 else ''
        self.objTableName = otp + 'objects_features'
        
        # get the objects
        cursor = self.connection.cursor()
        
        # first load the feature numbers
        cursor.execute("SELECT * FROM {tn};".format(tn=self.objTableName))
        self.featureNumbers = {}
        for row in cursor:
            oid, fid = row
            if oid not in self.featureNumbers:
                self.featureNumbers[oid] = []
            self.featureNumbers[oid].append(fid)
        
        # now read in the objects and features in chunks
        self.maxObjId = max(self.featureNumbers.keys())
        self.objects = []
        self.oidKeyedObjects = {}
        self.imageObjects = []
        while self.lastObjId < self.maxObjId:
            # set the object number range
            self.firstObjId = self.lastObjId + 1
            self.lastObjId = min(self.firstObjId + self.objFetchSize,self.maxObjId)
            
            if not self.compressed:
                # build a query to read the objects
                objQuery = '''SELECT o.object_id,
                                p.frame_number,
                                AVG(p.x_coordinate),
                                AVG(p.y_coordinate),
                                AVG(v.x_coordinate),
                                AVG(v.y_coordinate)
                            FROM '{otn}' o, 'positions' p, 'velocities' v
                            WHERE o.trajectory_id=p.trajectory_id
                                AND o.trajectory_id=v.trajectory_id
                                AND p.frame_number=v.frame_number
                                AND o.object_id BETWEEN {first} AND {last}
                            GROUP BY o.object_id,p.frame_number
                            ORDER BY o.object_id,p.frame_number;'''.format(otn=self.objTableName, first=self.firstObjId, last=self.lastObjId)
                cursor.execute(objQuery)
                objects = self.buildTrajectories(cursor, featureNumbers=self.featureNumbers, returnDict=True)
            
            if self.withFeatures or self.allFeatures:
                # build a query to read the features
                fnums = []
                for oid in range(self.firstObjId, self.lastObjId+1):
                    if oid in self.featureNumbers:
                        fnums.extend(self.featureNumbers[oid])
                    #print o.velocities
                featQuery = '''SELECT p.trajectory_id,
                                p.frame_number,
                                p.x_coordinate,
                                p.y_coordinate,
                                v.x_coordinate,
                                v.y_coordinate
                                FROM 'positions' p,'velocities' v
                                WHERE p.trajectory_id=v.trajectory_id
                                AND p.frame_number=v.frame_number
                                AND p.trajectory_id IN ({fnums})
                                ORDER BY p.trajectory_id,p.frame_number;'''.format(fnums=','.join(map(str,fnums)))
                
                # assemble the features and assign them to objects
                cursor.execute(featQuery)
                features = self.buildTrajectories(cursor, returnDict=True)
                for oid in range(self.firstObjId, self.lastObjId+1):
                    if not self.compressed:
                        o = objects[oid]
                        if hasattr(o, 'featureNumbers'):
                            o.setFeatures(features)
                    else:
                        ofeats = [features[fid] for fid in self.featureNumbers[oid]]
                        o = cvmoving.MovingObject.fromFeatures(oid, ofeats)
                    self.objects.append(o)
                    if useQueue:
                        self.objectQueue.put(o)
                    if self.homography is not None and self.invHom is not None:
                        io = cvmoving.ImageObject(o, self.homography, self.invHom, withBoxes=self.withImageBoxes)
                        self.imageObjects.append(io)
                        if useQueue:
                            self.imageObjectQueue.put(io)
            else:
                for oid in range(self.firstObjId, self.lastObjId+1):
                    o = objects[oid]
                    self.objects.append(o)
    
    # TODO fix this to reflect changes
    #def loadAnnotations(self, objTablePrefix):
        ## make the object (object feature numbers) table name
        #objTablePrefix = objTablePrefix.rstrip('_')
        #otp = objTablePrefix + '_' if len(objTablePrefix) > 0 else ''
        #objTableName = otp + 'objects_features'
        #self.annotations = self.loadObjectTable(objTableName)
    
    def writeObjects(self, objects, tablePrefix=None):
        """Write the feature numbers for the given list of objects to the tables prefixed with the given name. NOTE: Object numbers are reset during this process."""
        if len(objects) == 0:
            return False
        if tablePrefix is not None:
            tablePrefix = tablePrefix.rstrip('_')
            objTableName = "{prefix}_objects".format(prefix=tablePrefix)
            objFeatTableName = "{prefix}_objects_features".format(prefix=tablePrefix)
        else:
            objTableName = 'objects'
            objFeatTableName = 'objects_features'
        
        cursor = self.connection.cursor()
        
        # create the tables if necessary
        cursor.execute("CREATE TABLE IF NOT EXISTS {tableName} ( object_id INTEGER, road_user_type INTEGER DEFAULT 0, n_objects INTEGER DEFAULT 1, PRIMARY KEY(object_id) );".format(tableName=objTableName))
        cursor.execute("CREATE TABLE IF NOT EXISTS {tableName} (object_id INTEGER, trajectory_id INTEGER, PRIMARY KEY(object_id, trajectory_id) );".format(tableName=objFeatTableName))
        
        # we don't need object IDs, throw them out if we got them
        if isinstance(objects, dict):
            objects = objects.values()
        
        # extract the feature numbers if we were given objects
        if isinstance(objects[0], cvmoving.MovingObject):
            objectFeatures = []
            for o in objects:
                objectFeatures.append(o.featureNumbers)
        else:
            objectFeatures = objects
        
        # format the data into a list of tuples for writing to the database
        objTableData = []
        objFeatTableData = []
        oId = 0
        for oFeats in objectFeatures:
            #oId = o.getNum()
            objTableData.append((oId,0,1))
            for fId in oFeats:
                #print (oId, fId)
                objFeatTableData.append((oId, fId))
            oId += 1
                
        # push the data to the database
        success = False
        try:
            cursor.executemany("INSERT INTO {tableName} (object_id, road_user_type, n_objects) values (?, ?, ?)".format(tableName=objTableName), objTableData)
            cursor.executemany("INSERT INTO {tableName} (object_id, trajectory_id) values (?, ?)".format(tableName=objFeatTableName), objFeatTableData)
            self.connection.commit()
            success = True
        except sqlite3.IntegrityError as error:
            # data is already there, no need to do any more
            print error
        return success
    
    def writeFeatures(self, features):
        """Write the positions and velocities of features into the database."""
        cursor = self.connection.cursor()

        # create tables if necessary
        dtype = 'INTEGER' if self.compressed else 'REAL'
        cursor.execute("CREATE TABLE IF NOT EXISTS positions (trajectory_id INTEGER,frame_number INTEGER, x_coordinate {dt}, y_coordinate {dt}, PRIMARY KEY(trajectory_id, frame_number))".format(dt=dtype))
        cursor.execute("CREATE TABLE IF NOT EXISTS velocities (trajectory_id INTEGER,frame_number INTEGER, x_coordinate {dt}, y_coordinate {dt}, PRIMARY KEY(trajectory_id, frame_number))".format(dt=dtype))
        
        # format the data into a list of tuples
        posData = []
        velData = []
        for f in features:
            fId = f.getNum()
            pos = ZipTraj.fromTrajectory(f.positions, precision=self.precision).asTrajectory(compressed=True) if self.compressed else f.positions
            vel = ZipTraj.fromTrajectory(f.velocities, precision=self.precision).asTrajectory(compressed=True) if self.compressed else f.velocities
            
            for i, p, v in zip(f.timeInterval, pos, vel):
                    posData.append((fId,i,p.x,p.y))
                    velData.append((fId,i,v.x,v.y))
        
        # push the data to the database
        success = False
        try:
            cursor.executemany("INSERT INTO positions (trajectory_id, frame_number, x_coordinate, y_coordinate) values (?,?,?,?)", posData)
            cursor.executemany("INSERT INTO velocities (trajectory_id, frame_number, x_coordinate, y_coordinate) values (?,?,?,?)", velData)
            self.connection.commit()
            success = True
        except sqlite3.IntegrityError as error:
            # data is already there, no need to do any more
            print error
        return success
