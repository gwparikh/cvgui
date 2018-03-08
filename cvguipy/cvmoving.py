#!/usr/bin/python

import numpy as np

# TrafficIntelligence modules (not a package)
import moving, cvutils

from . import cvgui, cvgeom

def getFeaturePositionAtInstant(f, i, invHom=None):
    """Get the position of a feature in image space at instant i."""
    if not hasattr(f, 'imgPos') and invHom is not None:
        f.imgPos = Trajectory(f.positions.project(invHom).positions)
    return f.imgPos[i-f.getFirstInstant()]

def getCardinalDirection(theta, cardinalDirections=None):
    if cardinalDirections is None:
        cardinalDirections = ['E','NE','N','NW','W','SW','S','SE']
    nDirs = len(cardinalDirections)
    snapTo = 2*np.pi/float(nDirs)
    snapIndex = int(round(theta/float(snapTo)))
    if snapIndex == len(cardinalDirections):
        snapIndex = 0
    return cardinalDirections[snapIndex]

def getBoxCorners(points):
    """
    Get the corners of the box made by the minimum and maximum X and Y
    coordinates of the given points.
    """
    pMin, pMax = None, None
    if len(points) > 0:
        minX, minY = np.inf, np.inf
        maxX, maxY = 0, 0
        for p in points:
            if p.x < minX:
                minX = p.x
            if p.y < minY:
                minY = p.y
            if p.x > maxX:
                maxX = p.x
            if p.y > maxY:
                maxY = p.y
        pMin = Point(minX, minY)
        pMax = Point(maxX, maxY)
    return pMin, pMax

class box(object):
    def __init__(self, pMin=None, pMax=None):
        self.pMin = pMin
        self.pMax = pMax
        self.area = None
        self.calcArea()
    
    def __repr__(self):
        return "<Area = {}; ({},{}) -> ({},{})>".format(self.area, self.pMin.x, self.pMin.y, self.pMax.x, self.pMax.y)
    
    def isNone(self):
        return self.pMin is None or self.pMax is None
    
    def calcArea(self):
        if not self.isNone():
            self.area = (self.pMax.x-self.pMin.x)*(self.pMax.y-self.pMin.y)
    
    def contains(self, x, y):
        if not self.isNone():
            return ((x >= self.pMin.x) and (x <= self.pMax.x) and (y >= self.pMin.y) and (y <= self.pMax.y))

class TimeInterval(moving.TimeInterval):
    pass

# silently try importing BBMovingObject as that or BBAnnotation (old TrafficIntelligence)
try:
    class BBMovingObject(moving.BBMovingObject):
        pass
except:
    pass

try:
    class BBMovingObject(moving.BBAnnotation):
        pass
except:
    pass

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
        
        return cls(np.vstack([p0, rv]), **kwargs)
    
    @classmethod
    def fromCompressed(cls, zt, precision=0.01, **kwargs):
        return cls(np.array(zt)*precision, precision=precision, **kwargs)
    
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

class MovingObject(moving.MovingObject):
    def __init__(self, *args, **kwargs):
        super(MovingObject, self).__init__(*args, **kwargs)
        
        # the lane of the object at each instant in time
        self.lane = []
        self.boundingbox = []
    
    @classmethod
    def fromTableRows(cls, oId, firstInstant, lastInstant, positions, velocities, featureNumbers=None, compressed=False, precision=0.01):
        tInt = TimeInterval(firstInstant, lastInstant)
        if compressed:
            # fixed precision, using ZipTraj
            # positions and velocities are fixed precision values
            # stored as integers at a certain precision
            ptraj = ZipTraj.fromCompressed(positions, precision=precision).asTrajectory()
            vtraj = ZipTraj.fromCompressed(velocities, precision=precision).asTrajectory()
        else:
            # floating precision
            ptraj = Trajectory.fromPointList(positions)
            vtraj = Trajectory.fromPointList(velocities)
            
        obj = MovingObject(oId, timeInterval=tInt, positions=ptraj, velocities=vtraj)
        if featureNumbers is not None and oId in featureNumbers:
            obj.featureNumbers = featureNumbers[oId]
        return obj
    
    @classmethod
    def fromFeatures(cls, oId, features):
        """Build the object from the features by averaging the position and velocity of all features at each instant."""
        firstInstant, lastInstant = np.inf, 0
        pX, pY = {}, {}
        vX, vY = {}, {}
        
        # go through all the features and make lists for creating the averages
        for f in features:
            if f.getFirstInstant() < firstInstant:
                firstInstant = f.getFirstInstant()
            if f.getLastInstant() > lastInstant:
                lastInstant = f.getLastInstant()
            for i in f.timeInterval:
                for dic in [pX, pY, vX, vY]:
                    if i not in dic:
                        dic[i] = []
                p = f.getPositionAtInstant(i)
                v = f.getVelocityAtInstant(i)
                pX[i].append(p.x)
                pY[i].append(p.y)
                vX[i].append(v.x)
                vY[i].append(v.y)
                
        ## create the object position and velocity at each instant by averaging all the features' values
        if (lastInstant - firstInstant) > 1:
            tInt = TimeInterval(firstInstant, lastInstant)
            positions, velocities = [], []
            for i in tInt:
                if i == tInt[0]:
                    pos = Trajectory([[np.mean(pX[i])], [np.mean(pY[i])]])
                    obj = MovingObject(oId, timeInterval=tInt, positions=pos)
                if i in pX and i in pY:
                    obj.positions.addPositionXY(np.mean(pX[i]), np.mean(pY[i]))
            obj.features = features
            obj.featureNumbers = [f.num for f in features]
            return obj
    
    def smooth(self, halfWidth=3):
        # extract the x and y coordinates
        x = self.getXCoordinates()
        y = self.getYCoordinates()
        smoothX = utils.filterMovingWindow(x, halfWidth)
        smoothY = utils.filterMovingWindow(y, halfWidth)
        self.smoothed = Trajectory.fromPointList(zip(smoothX, smoothY))
        return self.smoothed
    
    def getSmoothedPositionAtInstant(self, i, halfWidth=3, imageSpace=False):
        if imageSpace:
            if not hasattr(self.positions.imagespace, 'smoothed'):
                self.positions.imagespace.smooth(halfWidth)
            return self.positions.imagespace.smoothed[i-self.getFirstInstant()]
        else:
            if not hasattr(self.positions, 'smoothed'):
                self.positions.smooth(halfWidth)
            return self.positions.smoothed[i-self.getFirstInstant()]
    
    def getSmoothedVelocityAtInstant(self, i, halfWidth=3):
        if not hasattr(self.velocities, 'smoothed'):
            self.velocities.smooth(halfWidth)
        return self.velocities.smoothed[i-self.getFirstInstant()]
    
    def distanceLength(self):
        # go through the points and add up the norm2's
        length = 0.
        for i in range(0,len(self.positions)-1):
            p0 = self.positions[i]
            p1 = self.positions[i+1]
            length += (p0-p1).norm2()
        return length
    
    def matches(self, obj, i, matchDistance):
        d = Point.distanceNorm2(self.getPositionAtInstant(i), obj.getPositionAtInstant(i))
        if d < matchDistance:
            return d
        else:
            return matchDistance + 1
    
    def setFeatures(self, features):
        self.features = [features[i] for i in self.featureNumbers]
    
    def getFeaturesAtInstant(self, i):
        return [f for f in self.features if f.existsAtInstant(i)]
    
    def getPositionAtInstant(self, i, imageSpace=False):
        if imageSpace:
            return self.positions.imagespace[i-self.getFirstInstant()]
        else:
            return self.positions[i-self.getFirstInstant()]
    
    def getLaneAtInstant(self, i):
        if len(self.lane) > 0:
            return self.lane[i-self.getFirstInstant()]
        else:
            raise Exception("Object {} has not been assigned lane(s)!".format(self.getNum()))
    
    def getBoxAtInstant(self, i):
        if len(self.boundingbox) > 0:
            return self.boundingbox[i-self.getFirstInstant()]
        else:
            raise Exception("Object {} has not had a bounding trajectory computed!".format(self.getNum()))
    
    def getAverageVelocity(self, timeInt=None, fps=15.0):
        """
        Calculate the average (space-mean) velocity of the object over 
        time interval timeInt (a TimeInterval object). If an interval
        is not provided, the object's entire trajectory is used.
        
        Average velocity is calculated as (pF - p0)/(timeInt.length()/fps).
        """
        if timeInt is None:
            t0, tF = self.getFirstInstant(), self.getLastInstant()
        else:
            t0 = timeInt.first if timeInt.first != 0 else self.getFirstInstant()
            tF = timeInt.last if timeInt.last != -1 else self.getLastInstant()
        p0 = self.getPositionAtInstant(t0)
        pF = self.getPositionAtInstant(tF)
        
        # calculate distance and time
        d = pF - p0
        t = tF - t0
        
        # velocity and (optionally) speed/direction
        vFrames = d.divide(t)                   # units/frame
        vSecs = vFrames.multiply(float(fps))    # units/second
        return vSecs
    
    def getSpeedHeading(self, timeInt=None, fps=15.0, cardinal=False, degrees=False):
        """
        Calculate the average velocity of the object over time interval
        timeInt (a TimeInterval object), returning the speed (magnitude
        of velocity vector) and heading in angle or cardinal direction
        (if cardinal is True).
        
        If an interval is not provided, the object's entire trajectory is used.
        
        Average velocity is calculated as (pF - p0)/(timeInt.length()/fps).
        """
        vAvg = self.getAverageVelocity(timeInt=timeInt, fps=fps)
        
        # velocity magnitude (norm) and direction (angle) (+CC from 0 at +X axis)
        mag = vAvg.norm2()
        direction = np.arctan2(-vAvg.y,vAvg.x)          # need -y since uses +Y down on aerial image
        # flip direction if negative (to keep +CC)
        if direction < 0:
            direction = 2*np.pi + direction
        if cardinal:
            direction = getCardinalDirection(direction)
        elif degrees:
            direction = cvgeom.rad2deg(direction)
        return mag, direction
    
    #def 
        
class Point(moving.Point):
    def __div__(self, i):
        i = float(i)
        return Point(self.x/i, self.y/i)
    
    def __mul__(self, i):
        return Point(self.x*i, self.y*i)
    
class Trajectory(moving.Trajectory):
    # override __getitem__ to allow slicing
    def __getitem__(self, i):
        if isinstance(i, int):
            return Point(self.positions[0][i], self.positions[1][i])
        elif isinstance(i, slice):
            seg = []
            rng = range(i.start, i.stop) if i.step is None else range(i.start, i.stop, i.step)
            for indx in rng:
                if indx > 0 and indx < len(self.positions[0]):
                    seg.append(Point(self.positions[0][indx], self.positions[1][indx]))
            return seg
    
class ImageObject(object):
    def __init__(self, obj, hom, invHom, withBoxes=True, imageBoxes=True, worldBoxes=False, color='random'):
        self.obj = obj
        self.hom = hom
        self.invHom = invHom
        self.color = cvgeom.getColorCode(color)
        self.withBoxes = withBoxes or imageBoxes or worldBoxes
        
        self.hidden = False
        self.isExploded = False
        self.isDeleted = False
        self.boundingbox = []
        self.imgBoxes = []
        self.joinedWith = []
        self.joinedObj = None
        self.imgPos = None
        self.prevImgPos = []
        self.subObjects = []
        self.ungroupedFeatures = {}
        self.project()
        if self.withBoxes:
            self.computeBoundingTrajectory(imageSpace=imageBoxes, worldSpace=worldBoxes)
    
    def __repr__(self):
        objInfo = ''
        if len(self.subObjects) > 0:
            objInfo = ": {} subObjects, {} ungroupedFeatures".format(len(self.subObjects), len(self.ungroupedFeatures))
        elif self.isJoined():
            objInfo = ": joinedWith {}, joinedObj: {}".format(self.joinedWith, self.joinedObj)
        return "<{} {}{}>".format(self.__class__.__name__, self.obj.num, objInfo)
    
    def project(self):
        o = self.obj.positions.project(self.invHom)
        self.imgPos = Trajectory(o.positions)   # need to pass Trajectory constructor a list of points, not a Trajectory object
        
        self.obj.positions.imagespace = self.imgPos                                   # for compatibility with (old) roundabout code
        if self.obj.features is not None:
            for f in self.obj.features:
                f.imgPos = Trajectory(f.positions.project(self.invHom).positions)
                f.positions.imagespace = f.imgPos
    
    def hide(self):
        """Set the hidden attribute to True."""
        self.hidden = True
    
    def unhide(self):
        """Set the hidden attribute to False."""
        self.hidden = False
    
    def getNum(self):
        return self.obj.getNum()
    
    def getBox(self, i):
        indx = self.getIndex(i)
        if indx < len(self.imgBoxes) and indx > 0:
            return self.imgBoxes[indx]
        
    def isInBox(self, i, x, y):
        inBox = False
        box = self.getBox(i)
        if box is not None and box.contains(x,y):
            inBox = True
        return inBox
    
    def toInstant(self, i):
        return self.imgPos[0:self.getIndex(i)]
    
    def existsAtInstant(self, i):
        return self.obj.existsAtInstant(i)
    
    def getIndex(self, i):
        return i-self.getFirstInstant()
    
    def getFirstInstant(self):
        return self.obj.getFirstInstant()
    
    def getFeaturesAtInstant(self, i):
        feats = self.obj.getFeaturesAtInstant(i) if self.obj.features is not None else []
        for o in self.joinedWith:
            feats.extend(o.obj.getFeaturesAtInstant(i))
        return feats
    
    def getFeaturePositionsAtInstant(self, i):
        """Return the position of each feature (as a Point object) that exists at
           instant i, including features from joined objects."""
        # get this object's features
        featPositions = [getFeaturePositionAtInstant(f, i) for f in self.obj.getFeaturesAtInstant(i)]
        
        # then recurse into the joined objects (if there are any)
        for o in self.joinedWith:
            featPositions.extend([getFeaturePositionAtInstant(f, i) for f in o.getFeaturesAtInstant(i)])
        return featPositions
    
    def getFeatureNumbers(self):
        featureNumbers = []
        for o in self.getObjList():
            featureNumbers.append(o.featureNumbers)
        return featureNumbers
    
    def isJoined(self):
        return len(self.joinedWith) > 0
    
    def drawAsJoined(self):
        """
        Return if this object should be drawn to represent all objects it is
        joined with (true if it is the object with the lowest ID number).
        """
        draw = True
        for o in self.joinedWith:
            if self.getNum() > o.getNum():
                draw = False
        return draw
    
    def join(self, obj):
        if obj not in self.joinedWith:
            self.joinedWith.append(obj)
        self.computeBoundingTrajectory()
        if self.drawAsJoined():
            self.makeJoinedObject()
            
            self.prevImgPos.append(self.imgPos)
            self.imgPos = self.joinedObj.imgPos
    
    def unjoin(self, obj):
        if self.drawAsJoined() and len(self.prevImgPos) > 0:
            self.imgPos = self.prevImgPos.pop(0)
        if obj in self.joinedWith:
            self.joinedWith.pop(self.joinedWith.index(obj))
        self.computeBoundingTrajectory()
    
    def getJoinList(self):
        return [self] + self.joinedWith
        
    def makeJoinedObject(self):
        for o in self.joinedWith:
            if self.obj.num > o.obj.num:
                return []
        features = list(self.obj.features)
        for o in self.joinedWith:
            features.extend(o.obj.features)
        self.joinedObj = ImageObject(MovingObject.fromFeatures(self.obj.num, features), self.hom, self.invHom)
        
    def getObjList(self):
        """Create a list of all objects that this object contains."""
        if self.isJoined() and self.drawAsJoined():        # if the object has been joined with other objects, create the object from all the features, but only if this is the lowest object ID in the group
            self.makeJoinedObject()
            return [self.joinedObj.obj]
        elif self.isJoined() and not self.drawAsJoined():
            # forget about joined object
            return []
        elif self.isDeleted:
            # forget about deleted object
            return []
        elif len(self.subObjects) > 0:
            subObjs = []
            for s in self.subObjects:
                subObjs.extend(s.getObjList())          # call getObjList on all the subObjects to capture joined subObjects
            return subObjs
        else:
            return [self.obj]           # if it's just the one object, return the object in a list
    
    def groupFeatures(self, featureIds):
        """
        Group the listed feature IDs into a new subObject and remove them from
        the ungrouped features. Returns the ID of the new object.
        """
        feats = []
        for fid in featureIds:
            if fid in self.ungroupedFeatures:
                feats.append(self.ungroupedFeatures.pop(fid))
        oId = 10000*self.obj.num + len(self.subObjects)
        print "Grouping object {} from features {} ...".format(oId, featureIds)
        o = ImageObject(MovingObject.fromFeatures(oId, feats), self.hom, self.invHom)
        self.subObjects.append(o)
        return oId, o
    
    def _dropSubObject(self, oId):
        """
        Remove the subObject with the specified ID and return its features
        to the list of ungroupedFeatures.
        """
        di = None
        for i in range(len(self.subObjects)):
            if self.subObjects[i].obj.num == oId:
                o = self.subObjects.pop(i)
                for f in o.obj.features:
                    if f in self.obj.features:
                        self.ungroupedFeatures[f.num] = f
    
    def explode(self):
        self.isExploded = True
        self.ungroupedFeatures = {f.getNum(): f for f in self.obj.features}
    
    def unExplode(self):
        """Undo the explode by clearing the list of subObjects."""
        self.isExploded = False
        self.subObjects = []
        self.ungroupedFeatures = {}
        
    def getTimeInterval(self):
        """
        Return the time interval of the object. If the object is joined, the time 
        interval will include any time when any of the component objects is on screen.
        """
        if len(self.joinedWith) > 0:
            firstInstants, lastInstants = [], []
            for o in self.joinedWith:
                firstInstants.append(o.obj.getFirstInstant())
                lastInstants.append(o.obj.getLastInstant())
            return TimeInterval(min(firstInstants), max(lastInstants))
        else:
            return self.obj.timeInterval
        
    def computeBoundingTrajectory(self, imageSpace=True, worldSpace=True):
        """
        Compute the bounding box for the object at each instant in both image
        space and world space. The image space box is stored in (ImageObject)
        self.imgBoxes, while the world space box is stored in
        self.obj.boundingbox. Either operation can be turned off by setting
        imageSpace or worldSpace to False.
        """
        self.obj.boundingbox = []
        self.imgBoxes = []
        for i in self.getTimeInterval():
            # get all features at this instant
            feats = self.getFeaturesAtInstant(i)
            
            # get the minimum and maximum x and y coordinates in image space
            # and world space of all features at this instant
            imgPoints = []
            worldPoints = []
            for f in feats:
                if imageSpace:
                    imgPoints.append(getFeaturePositionAtInstant(f,i))
                if worldSpace:
                    worldPoints.append(f.getPositionAtInstant(i))
            
            if imageSpace:
                pMinImg, pMaxImg = getBoxCorners(imgPoints)
                self.imgBoxes.append(cvgeom.imagebox(pMin=pMinImg, pMax=pMaxImg, index=self.obj.getNum(), color=self.color, frameNumber=i))
            if worldSpace:
                pMinWorld, pMaxWorld = getBoxCorners(worldPoints)
                self.obj.boundingbox.append(box(pMinWorld, pMaxWorld))
            
    
