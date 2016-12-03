#!/usr/bin/python
"""Classes for taking input from images, based on the cvgui module."""

import os, sys, time, math, traceback
import rlcompleter, readline
import numpy as np
import threading
from shapely.geometry import Point as shapelyPoint
from configobj import ConfigObj
import cvgui
import cv2

class Box(object):
    """A class representing a box."""
    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2
        self.xMin = min(p1.x, p2.x)
        self.xMax = max(p1.x, p2.x)
        self.yMin = min(p1.y, p2.y)
        self.yMax = max(p1.y, p2.y)
    
    def contains(self, p):
        return (p.x >= self.xMin and p.x <= self.xMax) and (p.y >= self.yMin and p.y <= self.yMax)

class PointMover(cvgui.action):
    """An action for moving a list of points."""
    def __init__(self, points, d):
        self.points = dict(points)                    # make a copy of the dict so they can change the selected objects outside of here
        self.d = d
        self.name = "{}".format(self.points)          # name is points being moved (used in __repr__)
        
    def do(self):
        """Move all points in the list by d.x and d.y."""
        for p in self.points.values():
            p.move(self.d)
        
    def undo(self):
        """Undo the move by moving all points in the list by -d.x and -d.y."""
        for p in self.points.values():
            p.move(-self.d)

class PointAdder(cvgui.action):
    """An action for adding a single point."""
    def __init__(self, points, x, y, i):
        self.i = i
        self.p = imagepoint(x, y, index=i)              # create the point and save it
        self.points = points                            # keep the reference to the original list so we can change it
        self.name = "{}".format(self.p)                      # name is point being added (used in __repr__)
        
    def do(self):
        """Add the point to the point dict."""
        if self.i not in self.points:
            self.points[self.i] = self.p
        
    def undo(self):
        """Undo the add by removing the point from the dict (but keeping it in case we need it later)."""
        if self.i in self.points:
            self.points.pop(self.i)

class PointDeleter(cvgui.action):
    """An action for deleting a list of points."""
    def __init__(self, points, dList):
        self.points = points                            # keep the reference to the original list so we can change it
        self.dList = dict(dList)                        # copy the selected list though
        self.name = "{}".format(dList)                  # name is points being deleted (used in __repr__)
        
    def do(self):
        """Delete the points from the point dict (but keep them in case they want to undo)."""
        for i in self.dList.keys():
            if i in self.points:
                self.dList[i] = self.points.pop(i)
        
    def undo(self):
        """Undo the deletion by reinserting the points in the dict."""
        for i, p in self.dList.iteritems():
            if p is not None:
                self.points[p.index] = p
    
class imagepoint(object):
    """A class representing a point selected on an image."""
    def __init__(self, x=None, y=None, index=None):
        self.x, self.y = x, y
        self.index = index
        self.selected = False
        self.next = None
        self.previous = None
    
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
        return shapelyPoint(self.x, self.y)
    
    # TODO - follow path of next point(s) to select polygons all at once
    def select(self):
        self.selected = True
        
    def deselect(self):
        self.selected = False
        
    def toggleSelected(self):
        self.selected = not self.selected
        
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
        
    def dist(self, p):
        """Calculates the distance between points self and p."""
        return math.sqrt((self.x-p.x)**2 + (self.y-p.y)**2)

class ImageInput(cvgui.cvImage):
    """A class for taking input from images displayed using OpenCV's highgui features.
    """
    def __init__(self, imageFilename, pointFilename, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, color=None, circleThickness=1):
        # construct cvGUI object
        super(ImageInput, self).__init__(imageFilename=imageFilename, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents)
        
        # ImageInput-specific properties
        self.pointFilename = pointFilename
        self.clickRadius = clickRadius
        self.circleThickness = circleThickness
        self.color = cvgui.cvColorCodes[color] if color in cvgui.cvColorCodes else cvgui.cvColorCodes['red']
        self.clickDown = imagepoint()
        self.clickUp = imagepoint()
        self.mousePos = imagepoint()
        self.lastMousePos = imagepoint()
        self.selectBox = None
        self.clickedOnPoint = False
        #self.selectedPoints = {}
        
        # TODO - create lines and polygons by using the imagepoint.next and .previous members to associate points, hold them in [[lineName]]/[[regionName]] subsection of [imageBasename]
        self.lines = {}         # new line with l/L ?
        self.polygons = {}      # new polygon with  p/P ?
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        self.addKeyBindings([262244], 'deleteSelected')     # Ctrl + d - delete selected points
        self.addKeyBindings([262259], 'savePoints')         # Ctrl + s - save points to file
        
        self.addMouseBindings([cv2.EVENT_LBUTTONDOWN], 'leftClickDown')
        self.addMouseBindings([cv2.EVENT_LBUTTONUP], 'leftClickUp')
        self.addMouseBindings([cv2.EVENT_MOUSEMOVE], 'mouseMove')
        self.addMouseBindings([cv2.EVENT_LBUTTONDBLCLK], 'doubleClick')
        
    def open(self):
        """Open a window and image file and load the point config."""
        self.openWindow()
        self.openImage()
        self.loadPoints()
        
    def loadPoints(self):
        """Loads the point configuration file (list of corresponding points)."""
        # look for the image file basename in the file
        self.points = {}
        self.pointConfig = ConfigObj(self.pointFilename)
        if self.imageBasename in self.pointConfig:
            # if we found it, load the points in this section
            print "Loading {} points from file {}".format(len(self.pointConfig[self.imageBasename]), self.pointFilename)
            
            for i, p in self.pointConfig[self.imageBasename].iteritems():
                try:
                    indx = int(i)
                    self.points[indx] = imagepoint(int(p[0]), int(p[1]), index=indx)
                except:
                    print "An error was encountered while processing the configuration file {}. Please check the formatting.".format(self.pointFilename)
                    break
        self.pIndex = max(self.points.keys()) if len(self.points) > 0 else 0
    
    def savePoints(self):
        """Saves the list of points into the config file provided."""
        # clear the old section
        self.pointConfig[self.imageBasename] = {}
        
        # fill it with new points
        print "Saving {} points to file {}".format(len(self.points), self.pointFilename)
        for i, p in self.points.iteritems():
            self.pointConfig[self.imageBasename][str(i)] = p.asList()
        
        # write the changes
        self.pointConfig.write()
        
    def checkXY(self, x, y):
        """Returns the index of the point within clickRadius of (x,y) (if it exists)."""
        cp = imagepoint(x,y)
        minDist = self.clickRadius
        minI = None
        for i, p in self.points.iteritems():
            d = cp.dist(p)
            if d < minDist:
                minDist = d
                minI = i
        return minI
    
    def checkPoint(self, p):
        return self.checkXY(p.x, p.y)
    
    #def toggleSelectPoint(self, i, p=None):
        #"""Toggle a point's selection status, selecting it if it's not
           #selected, and de-selecting it if it's selected."""
        #if i in self.selectedPoints:
            #self.selectedPoints.pop(i)
        #else:
            #self.selectPoint(i, p)
            
    #def selectPoint(self, i=None, p=None):
        #"""Select a point, adding the point to the list if it's not selected already."""
        #if i is not None and p is None:
            #p = self.points[i]
        #elif i is None and p is not None:
            #i = p.index
        #if i is not None and p is not None:
            #self.selectedPoints[i] = p
        #self.update()
        
    def addPoint(self, x, y):
        lastIndx = max(self.points.keys()) if len(self.points) > 0 else 0
        i = lastIndx + 1
        a = PointAdder(self.points, x, y, i)
        self.do(a)
        
    def selectedPoints(self):
        """Get a dict with the selected points."""
        return {i: p for i, p in self.points.iteritems() if p.selected}
        
    def clearSelected(self):
        """Clear all selected points."""
        #self.selectedPoints = {}
        for p in self.points.values():
            p.deselect()
        
    def deleteSelected(self):
        """Delete the points from the list, in a way that can be undone."""
        a = PointDeleter(self.points, self.selectedPoints())
        self.do(a)
        
    def updateSelection(self):
        """Update the list of selected points to include everything inside the rectangle
           made by self.clickDown and self.mousePos."""
        self.selectBox = Box(self.clickDown, self.mousePos)
        for i, p in self.points.iteritems():
            if self.selectBox.contains(p):
                #self.selectPoint(i, p)
                p.select()
        self.update()
        
    def movePoints(self, d):
        """Move all selected points by (d.x,d.y)."""
        #for p in self.selectedPoints.values():
        for p in self.points.values():
            if p.selected:
                p.move(d)
        
    def drawPoint(self, i, p):
        """Draw the point on the image as a circle with crosshairs."""
        #isSelected = i in self.selectedPoints
        ct = 4*self.circleThickness if p.selected else self.circleThickness                 # highlight the circle if it is selected
        cv2.circle(self.img, p.asTuple(), self.clickRadius, self.color, thickness=ct)       # draw the circle
        
        # draw the line from p.x-self.clickRadius to p.x+clickRadius
        p1x, p2x = p.x - self.clickRadius, p.x + self.clickRadius
        cv2.line(self.img, (p1x, p.y), (p2x, p.y), self.color, thickness=1)
        
        # draw the line from p.x-self.clickRadius to p.x+clickRadius
        p1y, p2y = p.y - self.clickRadius, p.y + self.clickRadius
        cv2.line(self.img, (p.x, p1y), (p.x, p2y), self.color, thickness=1)
        
    def drawFrame(self):
        """Show the image in the player with points, selectedPoints, and the selectBox drawn on it."""
        # draw the points on the frame
        for i, p in self.points.iteritems():
            self.drawPoint(i, p)
            
        # and the box (if there is one)
        if self.selectBox is not None:
            cv2.rectangle(self.img, self.selectBox.p1.asTuple(), self.selectBox.p2.asTuple(), cvgui.cvColorCodes['blue'], thickness=1)
        
        # then show the image
        cv2.imshow(self.windowName, self.img)
        
    def setMousePos(self, x, y):
        """Set the current and previous positions of the mouse cursor."""
        self.lastMousePos = self.mousePos
        self.mousePos = imagepoint(x, y)
        
    def isMovingPoints(self):
        """Whether or not we are currently moving points."""
        if self.clickedOnPoint:
            for p in self.points.values():
                if p.selected:
                    return True
        return False
        #return len(self.selectedPoints) > 0 and self.clickedOnPoint
        
    def mouseMove(self, event, x, y, flags, param):
        """Process mouse movements."""
        self.setMousePos(x, y)
        if flags & cv2.EVENT_FLAG_LBUTTON:
            self.drag(event, x, y, flags, param)
        
    def drag(self, event, x, y, flags, param):
        """Process mouse movements when the left mouse button is held down (i.e. dragging)."""
        if self.isMovingPoints():
            # move the point(s)  each time we get a new move update, then after the button up event add an action to the buffer with the 2-point move so undo/redo jump (like in other things)
            
            # get the distance between the current mouse position and the last position
            d = self.mousePos - self.lastMousePos
            
            # move all of the selected points by d.x and d.y
            self.movePoints(d)
        else:
            # we are drawing a selection rectangle, so we should update it
            self.updateSelection()
        # update the picture
        self.update()
        
    def leftClickDown(self, event, x, y, flags, param):
        """Process left clicks, which select points and start multi-selection."""
        # record where we click down
        self.clickDown = imagepoint(x, y)
        
        # check if the user clicked on a point
        i = self.checkXY(x, y)
        if i is not None:
            # if they clicked on a point, make sure this point is in the selected points
            #self.selectPoint(i=i)
            self.points[i].select()
            
            # now we record that we clicked on a point and wait until we get a move event or a click up event
            self.clickedOnPoint = True      # this means we have "grabbed onto" the point(s), which will lead to a move if the mouse moves before the button is released
        else:
            # if they didn't click on a point, record it
            self.clickedOnPoint = False
            
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
        if self.isMovingPoints():
            # we're done with the move, add the complete move to the action buffer so it can be undone
            d = imagepoint(x,y) - self.clickDown
            a = PointMover(self.selectedPoints(), d)
            self.did(a)
        # reset the clicked state (NOTE - we may want to add variable to check if the mouse button is down independently of clicking on a point)
        self.clickedOnPoint = False
        
        # reset the select box
        self.selectBox = None
        
        # refresh the frame
        self.update()
        
    def doubleClick(self, event, x, y, flags, param):
        """Add a new point."""
        self.addPoint(x, y)
        self.update()
    