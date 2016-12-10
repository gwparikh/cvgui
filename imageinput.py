#!/usr/bin/python
"""Classes for taking input from images, based on the cvgui module."""

import os, sys, time, math, traceback
import rlcompleter, readline
import numpy as np
import shapely.geometry
from configobj import ConfigObj
import cvgui
import cv2

def box(p1, p2):
    xMin = min(p1.x, p2.x)
    xMax = max(p1.x, p2.x)
    yMin = min(p1.y, p2.y)
    yMax = max(p1.y, p2.y)
    return shapely.geometry.box(xMin, yMin, xMax, yMax)

class ObjectMover(cvgui.action):
    """An action for moving a list of objects. It calls the 'move' method of the objects, which must
       accept a single imagepoint object as an argument, containing the X and Y coordinates to move.."""
    def __init__(self, objects, d):
        self.objects = dict(objects)                    # make a copy of the dict so they can change the selected objects outside of here
        self.d = d
        self.name = "{}".format(self.objects)          # name is objects being moved (used in __repr__)
        
    def addObjects(self, objects):
        """Add more objects to be moved"""
        for i, o in objects.iteritems():
            self.objects[i] = o
        
    def do(self):
        """Move all objects in the list by d.x and d.y."""
        for p in self.objects.values():
            p.move(self.d)
        
    def undo(self):
        """Undo the move by moving all objects in the list by -d.x and -d.y."""
        for p in self.objects.values():
            p.move(-self.d)

class ObjectRenamer(cvgui.action):
    """An action for renaming an object.."""
    def __init__(self, objects, o, n):
        self.objects = objects
        self.o = o
        self.n = n
        self.i = o.index
        self.name = "{}".format(self.o)          # name is objects being moved (used in __repr__)
        
    def do(self):
        """Rename the object by setting o.name and o.index to n and moving it in the objects dictionary."""
        self.o.name = self.n
        self.o.index = self.n
        self.objects.pop(self.i)
        self.objects[self.n] = self.o
        
    def undo(self):
        """Undo the rename by setting everything back."""
        self.o.name = ''
        self.o.index = self.i
        self.objects.pop(self.n)
        self.objects[self.n] = self.o

class ObjectAdder(cvgui.action):
    """An action for adding a single IndexableObject to a dictionary keyed on its index."""
    def __init__(self, objects, o):
        self.o = o
        self.objects = objects                            # keep the reference to the original list so we can change it
        self.name = "{}".format(self.o)                      # name is point being added (used in __repr__)
        
    def do(self):
        """Add the object to the dict."""
        if self.o.getIndex() not in self.objects:
            self.objects[self.o.getIndex()] = self.o
        
    def undo(self):
        """Undo the add by removing the object from the dict (but keeping it in case we need it later)."""
        if self.o.getIndex() in self.objects:
            self.objects.pop(self.o.getIndex())

class ObjectDeleter(cvgui.action):
    """An action for deleting a list of objects."""
    def __init__(self, objects, dList):
        self.objectLists = [objects]                            # keep the reference to the original list so we can change it, make it a list so we can do more than one thing at a time
        self.dList = [dict(dList)]                        # copy the selected list though (but similarly putting it in a list)
        self.name = "{}".format(self.dList)                  # name is objects being deleted (used in __repr__)
        
    def addObjects(self, objects, dList):
        """Add more objects to be deleted"""
        self.objectLists.append(objects)
        self.dList.append(dict(dList))
        self.name = "{}".format(self.dList)                  # name is objects being deleted (used in __repr__)
    
    def do(self):
        """Delete the objects from the dict (but keep them in case they want to undo)."""
        for objects, dList in zip(self.objectLists, self.dList):
            for i in self.dList.keys():
                if i in objects:
                    self.dList[i] = objects.pop(i)
        
    def undo(self):
        """Undo the deletion by reinserting the objects in the dict."""
        for objects, dList in zip(self.objectLists, self.dList):
            for i, o in self.dList.iteritems():
                if o is not None:
                    objects[i] = o
    
class IndexableObject(object):
    """An indexable-object that can be selected."""
    def __init__(self):
        self.index = None
        self.selected = False
    
    def getIndex(self):
        return self.index
    
    def setIndex(self, i):
        self.index = i
    
    def select(self):
        self.selected = True
        
    def deselect(self):
        self.selected = False
        
    def toggleSelected(self):
        # call the methods so they can be overridden
        if self.selected:
            self.deselect()
        else:
            self.select()
    
class imageregion(IndexableObject):
    """A class representing a region of an image, defined as an ordered
       collection of points."""
    def __init__(self, index):
        self.index = index
        self.points = ObjectCollection()
        self.color = cvgui.randomColor()
        self.selected = False
        self.name = ""
        
    def __repr__(self):
        return "<imageregion {}: {}>".format(self.index, self.points)
    
    def distance(self, p):
        """Calculate the distance from the point to the boundary."""
        return self.boundary().distance(p.asShapely())            # gives distance from the point to the closest point on the boundary, whether it's inside or outside
    
    def move(self, dp):
        for p in self.points.values():
            p.move(dp)
    
    #def addPoint(self, x, y):
        ## TODO needs indexing, everything else just .values()
        #lastIndx = max(self.points.keys()) if len(self.points) > 0 else 0
        #i = lastIndx + 1
        #p = imagepoint(x, y, i)
        #self.points.append(p)
        
    def boundary(self):
        return shapely.geometry.LinearRing([p.asTuple() for p in self.points.values()])
        
    #def addPointXY(self, x, y):
        #p = imagepoint(x=x, y=y)
        #self.addPoint(p)
        
    def select(self):
        self.selected = True
        for p in self.points.values():
            p.select()
    
    def deselect(self):
        self.selected = False
        for p in self.points.values():
            p.deselect()
            
    def clickedOnPoint(self, cp, clickRadius):
        """Return whether the click cp was on a point of the region or not."""
        pt = None
        minDist = clickRadius
        for p in self.points.values():
            d = p.distance(cp)
            if d < minDist:
                minDist = d
                pt = p
        return pt
    
class imagepoint(IndexableObject):
    """A class representing a point selected on an image."""
    def __init__(self, x=None, y=None, index=None, color=None):
        self.x, self.y = x, y
        self.index = index
        self.selected = False
        self.setColor(color)
        
    def setColor(self, color):
        if isinstance(color, str) and color in cvgui.cvColorCodes:
            self.color = cvgui.cvColorCodes[color]
        elif isinstance(color, tuple) and len(color) == 3:
            self.color = color
        else:
            self.color = cvgui.cvColorCodes['blue']
    
    def __repr__(self):
        return "<imagepoint {}: ({}, {})>".format(self.index, self.x, self.y)
        
    def __add__(self, p):
        return imagepoint(self.x+p.x, self.y+p.y)

    def __sub__(self, p):
        return imagepoint(self.x-p.x, self.y-p.y)
    
    def __neg__(self):
        return imagepoint(-self.x, -self.y)
    
    def isNone(self):
        return self.x is None or self.y is None
        
    def asTuple(self):
        return (int(self.x), int(self.y))
    
    def asList(self):
        return [self.x, self.y]
    
    def asShapely(self):
        return shapely.geometry.Point(self.x, self.y)
    
    def pushBack(self):
        self.index += 1
        
    def pullForward(self):
        self.index -= 1
        
    def move(self, p):
        self.x += p.x
        self.y += p.y
        
    def moveTo(self, p):
        self.x = p.x
        self.y = p.y
    
    def rotate(self, o, dPhi):
        rho, phi = rabutils.cart2pol(self.x-o.x, self.y-o.y)
        self.x, self.y = rabutils.pol2cart(rho, phi + dPhi)
        
    def distance(self, p):
        """Calculates the distance between points self and p."""
        return math.sqrt((self.x-p.x)**2 + (self.y-p.y)**2)

class ObjectCollection(dict):
    """A collection of objects that have a distance method that
       accepts a single argument and returns the distance between
       the object and itself. Used to easily select the closest
       thing to a """
    def getClosestObject(self, cp):
        """Returns the key of the object that is closest to the point p"""
        minDist = np.inf
        minI = None
        for i, p in self.iteritems():
            d = p.distance(cp)
            if d < minDist:
                minDist = d
                minI = i
        return minI

class ImageInput(cvgui.cvImage):
    """A class for taking input from images displayed using OpenCV's highgui features.
    """
    def __init__(self, imageFilename, configFilename, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, color=None, lineThickness=1):
        # construct cvGUI object
        super(ImageInput, self).__init__(imageFilename=imageFilename, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents)
        
        # ImageInput-specific properties
        self.configFilename = configFilename
        self.clickRadius = clickRadius
        self.lineThickness = lineThickness
        self.color = cvgui.cvColorCodes[color] if color in cvgui.cvColorCodes else cvgui.cvColorCodes['blue']
        self.clickDown = imagepoint()
        self.clickUp = imagepoint()
        self.mousePos = imagepoint()
        self.lastMousePos = imagepoint()
        self.selectBox = None
        self.clickedOnObject = False
        self.creatingRegion = None
        #self.selectedPoints = {}
        
        # TODO - create lines and regions by using the imagepoint.next and .previous members to associate points, hold them in [[lineName]]/[[regionName]] subsection of [imageBasename]
        self.points = ObjectCollection()
        self.regions = ObjectCollection()
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        self.addKeyBindings([262244], 'deleteSelected')     # Ctrl + d - delete selected points
        self.addKeyBindings([262259], 'savePoints')         # Ctrl + s - save points to file
        self.addKeyBindings([114], 'createRegion')          # r - start creating region
        self.addKeyBindings([110], 'nameRegion')            # n - name the selected region
        self.addKeyBindings([10], 'enterFinish')            # Enter - finish action
        self.addKeyBindings([27], 'escapeCancel')           # Escape - cancel action
        
        self.addMouseBindings([cv2.EVENT_LBUTTONDOWN], 'leftClickDown')
        self.addMouseBindings([cv2.EVENT_LBUTTONUP], 'leftClickUp')
        self.addMouseBindings([cv2.EVENT_MOUSEMOVE], 'mouseMove')
        self.addMouseBindings([cv2.EVENT_LBUTTONDBLCLK], 'doubleClick')
        
    def open(self):
        """Open a window and image file and load the point config."""
        self.openWindow()
        self.openImage()
        self.points, self.regions = ImageInput.loadConfig(self.configFilename, self.imageBasename)
        
    @classmethod
    def loadConfig(cls, configFilename, imageBasename):
        pointConfig = ConfigObj(configFilename)
        points = ObjectCollection()
        regions = ObjectCollection()
        if imageBasename in pointConfig:
            print "Loading points and regions from file {} section {}".format(configFilename, imageBasename)
            imageDict = pointConfig[imageBasename]
            points, regions = ImageInput.loadDict(imageDict)
        return points, regions
        
    def savePoints(self):
        print "Saving points and regions to file {} section {}".format(self.configFilename, self.imageBasename)
        imageDict = self.saveDict()
        print imageDict
        self.pointConfig[self.imageBasename] = imageDict
        self.pointConfig.write()
        print "Changes saved!"
        
    @classmethod
    def loadDict(cls, imageDict):
        points = ObjectCollection()
        regions = ObjectCollection()
        if '_points' in imageDict:
            print "Loading {} points...".format(len(imageDict['_points']))
            for i, p in imageDict['_points'].iteritems():
                try:
                    indx = int(i)
                    points[indx] = imagepoint(int(p[0]), int(p[1]), index=indx)
                except:
                    print "An error was encountered while loading points. Please check your inputs."
                    break
        print "Loading {} regions".format(len(imageDict)-1)
        for n, r in imageDict.iteritems():
            if n == '_points':
                continue
            try:
                regions[n] = imageregion(n)
                for i, p in r.iteritems():
                    indx = int(i)
                    regions[n].points[indx] = imagepoint(int(p[0]), int(p[1]), index=indx)
            except:
                print "An error was encountered while loading regions. Please check your inputs."
                break
        return points, regions
    
    def saveDict(self):
        imageDict = {}
        
        # save the points to the _points section
        print "Saving {} points to file {} section {}".format(len(self.points), self.configFilename, self.imageBasename)
        imageDict['_points'] = {}
        for i, p in self.points.iteritems():
            imageDict['_points'][str(i)] = p.asList()
        
        # then add the regions
        print "Saving {} regions to file {} section {}".format(len(self.regions), self.configFilename, self.imageBasename)
        for n, r in self.regions.iteritems():
            # add each region to its own section
            imageDict[str(n)] = {}
            for i, p in r.points.iteritems():
                # then each point
                imageDict[str(n)][str(i)] = p.asList()
        return imageDict
        
    def checkXY(self, x, y):
        """Returns the point or polygon within clickRadius of (x,y) (if there is one)."""
        cp = imagepoint(x,y)
        i = self.points.getClosestObject(cp)                # look for the closest point
        if i is not None:
            p = self.points[i]
            if p.distance(cp) <= self.clickRadius:
                return p                                    # return the closest point if they clicked on one, otherwise check the regions
        i = self.regions.getClosestObject(cp)
        if i is not None:
            r = self.regions[i]
            if r.distance(cp) <= self.clickRadius:
                # return a single point if they clicked on a region's point, otherwise just the region
                rp = r.clickedOnPoint(cp, self.clickRadius)
                if rp is not None:
                    return rp
                else:
                    return r
        
    def enterFinish(self, key):
        """Finish whatever multi-step action we are currently performing (e.g.
           creating a polygon)."""
        if self.creatingRegion is not None:
            # if we are creating a polygon, finish it
            print "Finishing polygon number {}".format(self.creatingRegion.getIndex())
            self.finishRegion()
    
    def escapeCancel(self, key):
        """Cancel whatever multi-step action we are currently performing (e.g.
           creating a polygon)."""
        if self.creatingRegion is not None:
            # if we are creating a polygon, finish it
            print "Cancelling polygon number {}".format(self.creatingRegion.getIndex())
            self.creatingRegion = None
        self.update()
        
    def addPointToRegion(self, x, y):
        if self.creatingRegion is not None:
            # if the region has at least 3 points, check if this click was on the first point
            if len(self.creatingRegion.points) >= 3:
                d = self.creatingRegion.points[min(self.creatingRegion.points.keys())].distance(imagepoint(x, y))
                if d <= self.clickRadius:
                    # if it was, finish the region
                    self.finishRegion()
            if self.creatingRegion is not None:
                lastIndx = max(self.creatingRegion.points.keys()) if len(self.creatingRegion.points) > 0 else 0
                i = lastIndx + 1
                p = imagepoint(x, y, i)
                a = ObjectAdder(self.creatingRegion.points, p)
                self.do(a)
        
    def createRegion(self):
        lastIndx = len(self.regions)
        i = lastIndx + 1
        while i in self.regions:
            i += 1                  # make sure no duplicates
        print "Starting region {}".format(i)
        self.creatingRegion = imageregion(i)
        self.creatingRegion.select()
        self.update()
        
    def nameRegion(self, key=None):
        """Name the selected region."""
        rn = None
        name = ""
        for i, r in self.regions.iteritems():
            if r.selected:
                print "Renaming region {}".format(i)
                # call waitKey(0) in a while loop 
                k = 0
                while k != 10:
                    try:
                        k = cvgui.cv2.waitKey(0)
                        if k == 27:
                            print "Canelling..."
                            name = ""         # cancel
                            return
                        c = chr(k)
                        if str.isalnum(c):
                            name += c
                    except:
                        pass
                rn = r
                break
        if rn is not None:
            # remove the region under the old key and replace it with the name as the key
            a = ObjectRenamer(self.regions, rn, name)
            self.do(a)
            print "Region renamed to {}".format(name)
        
    def finishRegion(self):
        # before we add the region creation to the action buffer, forget that we added each of the points individually
        for p in self.creatingRegion.points.values():
            self.forget()
        
        # then add the whole region
        self.creatingRegion.deselect()              # make sure to deselect the region
        i = self.creatingRegion.index
        a = ObjectAdder(self.regions, self.creatingRegion)
        self.do(a)
        self.creatingRegion = None
        
    def addPoint(self, x, y):
        lastIndx = max(self.points.keys()) if len(self.points) > 0 else 0
        i = lastIndx + 1
        p = imagepoint(x, y, i)
        a = ObjectAdder(self.points, p)
        self.do(a)
        
    def selectedPoints(self):
        """Get a dict with the selected points."""
        return {i: p for i, p in self.points.iteritems() if p.selected}
        
    def selectedRegions(self):
        """Get a dict with the selected regions."""
        return {i: p for i, p in self.regions.iteritems() if p.selected}
        
    def clearSelected(self):
        """Clear all selected points and regions."""
        #self.selectedPoints = {}
        for p in self.points.values():
            p.deselect()
        for p in self.regions.values():
            p.deselect()
        self.update()
        
    def deleteSelected(self):
        """Delete the points from the list, in a way that can be undone."""
        selp = self.selectedPoints()
        a = ObjectDeleter(self.points, selp)
        selr = self.selectedRegions()
        a.addObjects(self.regions, selr)
        self.do(a)
        
    def updateSelection(self):
        """Update the list of selected points to include everything inside the rectangle
           made by self.clickDown and self.mousePos."""
        self.selectBox = box(self.clickDown, self.mousePos)
        for i, p in self.points.iteritems():
            if self.selectBox.contains(p.asShapely()):
                #self.selectPoint(i, p)
                p.select()
        
        # also add any regions that are completely selected
        for i, r in self.regions.iteritems():
            if self.selectBox.contains(r.boundary()):
                r.select()
        self.update()
        
    def moveRegions(self, d):
        """Move all selected regions by (d.x,d.y)."""
        for r in self.regions.values():
            if r.selected:
                r.move(d)
            else:
                # look at all the points and move any that are selected
                for p in r.points.values():
                    if p.selected:
                        p.move(d)
        
    def movePoints(self, d):
        """Move all selected points by (d.x,d.y)."""
        #for p in self.selectedPoints.values():
        for p in self.points.values():
            if p.selected:
                p.move(d)
       
    def drawPoint(self, p):
        """Draw the point on the image as a circle with crosshairs."""
        ct = 4*self.lineThickness if p.selected else self.lineThickness                 # highlight the circle if it is selected
        cv2.circle(self.img, p.asTuple(), self.clickRadius, p.color, thickness=ct)       # draw the circle
        
        # draw the line from p.x-self.clickRadius to p.x+clickRadius
        p1x, p2x = p.x - self.clickRadius, p.x + self.clickRadius
        cv2.line(self.img, (p1x, p.y), (p2x, p.y), p.color, thickness=1)
        
        # draw the line from p.x-self.clickRadius to p.x+clickRadius
        p1y, p2y = p.y - self.clickRadius, p.y + self.clickRadius
        cv2.line(self.img, (p.x, p1y), (p.x, p2y), p.color, thickness=1)
        
        # add the index of the point to the image
        cv2.putText(self.img, str(p.index), p.asTuple(), cv2.cv.CV_FONT_HERSHEY_PLAIN, 4.0, p.color, thickness=2)
        
    def drawRegion(self, reg):
        """Draw the region on the image as a closed linestring. If it is selected, 
           draw it as a closed linestring with a thicker line and points drawn as 
           selected points (which can be "grabbed")."""
        dlt = 2*self.lineThickness
        lt = 4*dlt if reg.selected else dlt
        p1, p2 = None, None
        for i in range(1, len(reg.points)):
            p1 = reg.points[i]
            p2 = reg.points[i+1]
            
            # draw the line between the two points (thick if selected)
            cv2.line(self.img, p1.asTuple(), p2.asTuple(), reg.color, thickness=lt)
            
            # and also draw the points if selected
            for p in reg.points.values():
                if reg.selected or p.selected:
                    self.drawPoint(p)
            
        # add the index at whatever the min point is
        if len(reg.points) > 0:
            p = reg.points[min(reg.points.keys())]
            cv2.putText(self.img, str(reg.index), p.asTuple(), cv2.cv.CV_FONT_HERSHEY_PLAIN, 4.0, reg.color, thickness=2)
            
        if p2 is not None and reg != self.creatingRegion:
            # draw the line to connect the first and last points
            cv2.line(self.img, p2.asTuple(), reg.points[min(reg.points.keys())].asTuple(), reg.color, thickness=lt)
    
    def drawFrame(self):
        """Show the image in the player with points, selectedPoints, and the selectBox drawn on it."""
        # draw the points on the frame
        for i, p in self.points.iteritems():
            self.drawPoint(p)
            
        # draw all the regions
        for i, p in self.regions.iteritems():
            #if p.selected:
                #print "{} is selected".format(p)
            self.drawRegion(p)
        
        # and the region we're drawing, if it exists
        if self.creatingRegion is not None:
            self.drawRegion(self.creatingRegion)
            
        # and the box (if there is one)
        if self.selectBox is not None:
            cv2.rectangle(self.img, self.clickDown.asTuple(), self.mousePos.asTuple(), cvgui.cvColorCodes['blue'], thickness=1)
        
        # then show the image
        cv2.imshow(self.windowName, self.img)
        
    def setMousePos(self, x, y):
        """Set the current and previous positions of the mouse cursor."""
        self.lastMousePos = self.mousePos
        self.mousePos = imagepoint(x, y)
        
    def isMovingObjects(self):
        """Whether or not we are currently moving objects (points or regions)."""
        if self.clickedOnObject:
            for p in self.points.values():
                if p.selected:
                    return True
            for r in self.regions.values():
                if r.selected:
                    return True
                for p in r.points.values():
                    if p.selected:
                        return True
        return False
        #return len(self.selectedPoints) > 0 and self.clickedOnObject
        
    def mouseMove(self, event, x, y, flags, param):
        """Process mouse movements."""
        self.setMousePos(x, y)
        if flags & cv2.EVENT_FLAG_LBUTTON:
            self.drag(event, x, y, flags, param)
        
    def drag(self, event, x, y, flags, param):
        """Process mouse movements when the left mouse button is held down (i.e. dragging)."""
        if self.isMovingObjects():
            # move the point(s)  each time we get a new move update, then after the button up event add an action to the buffer with the 2-point move so undo/redo jump (like in other things)
            
            # get the distance between the current mouse position and the last position
            d = self.mousePos - self.lastMousePos
            
            # move all of the selected points and regions by d.x and d.y
            self.movePoints(d)
            self.moveRegions(d)
        else:
            # we are drawing a selection rectangle, so we should update it
            self.updateSelection()
        # update the picture
        self.update()
        
    def leftClickDown(self, event, x, y, flags, param):
        """Process left clicks, which select points and start multi-selection."""
        # record where we click down
        self.clickDown = imagepoint(x, y)
        
        # if we are creating a region, add this point right to the selected region
        if self.creatingRegion:
            i = self.addPointToRegion(x, y)
        # check if the user clicked on a point, region, or region point
        p = self.checkXY(x, y)
        if p is not None:
            p.select()
            
            # now we record that we clicked on a point and wait until we get a move event or a click up event
            self.clickedOnObject = True      # this means we have "grabbed onto" the point(s), which will lead to a move if the mouse moves before the button is released
        else:
            # if they didn't click on a point, record it
            self.clickedOnObject = False
            
            # then check if modifiers were held down
            if not (flags & cv2.EVENT_FLAG_CTRLKEY) and not (flags & cv2.EVENT_FLAG_SHIFTKEY):
                # if ctrl or shift weren't held down, clear the selected points
                self.clearSelected()
        self.update()
                
    def leftClickUp(self, event, x, y, flags, param):
        """Process left click up events, which finish moves (recording the action
           for an undo/redo), and stops selection box drawing."""
        # record where we let off the mouse button
        self.clickUp = imagepoint(x, y)
        
        # if we were moving points
        if self.isMovingObjects():
            # we're done with the move, add the complete move to the action buffer so it can be undone
            d = imagepoint(x,y) - self.clickDown
            a = ObjectMover(self.selectedPoints(), d)
            self.did(a)
        # reset the clicked state (NOTE - we may want to add variable to check if the mouse button is down independently of clicking on a point)
        self.clickedOnObject = False
        
        # reset the select box
        self.selectBox = None
        
        # refresh the frame
        self.update()
        
    def doubleClick(self, event, x, y, flags, param):
        """Add a new point."""
        if self.creatingRegion is None:
            self.addPoint(x, y)
            self.update()
        