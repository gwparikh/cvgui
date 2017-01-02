#!/usr/bin/python
"""Classes for taking input from images, based on the cvgui module."""

import os, sys, time, math, traceback
import rlcompleter, readline
import numpy as np
import shapely.geometry
from configobj import ConfigObj
import cvgui, cvgeom
import cv2

def box(p1, p2):
    xMin = min(p1.x, p2.x)
    xMax = max(p1.x, p2.x)
    yMin = min(p1.y, p2.y)
    yMax = max(p1.y, p2.y)
    return shapely.geometry.box(xMin, yMin, xMax, yMax)

class ObjectMover(cvgui.action):
    """An action for moving a list of objects. It calls the 'move' method of the objects, which must
       accept a single cvgeom.imagepoint object as an argument, containing the X and Y coordinates to move.."""
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
        if self.i in self.objects:
            self.objects.pop(self.i)
        self.objects[self.n] = self.o
        
    def undo(self):
        """Undo the rename by setting everything back."""
        self.o.name = ''
        self.o.index = self.i
        self.objects.pop(self.n)
        self.objects[self.n] = self.o

class ObjectColorChanger(cvgui.action):
    """An action for changing the color of an object."""
    def __init__(self, o, color):
        self.o = o
        self.color = color
        self.oldColor = self.o.color
        self.name = "{}".format(self.o)          # name is objects being changed (used in __repr__)
        
    def do(self):
        """Change the color of the object by setting its color to self.color, saving the
           original color in case we need to undo."""
        self.oldColor = self.o.color
        self.o.setColor(self.color)
        
    def undo(self):
        """Undo the color change by setting it back to the old color."""
        self.o.setColor(self.oldColor)

class ObjectAdder(cvgui.action):
    """An action for adding a single cvgeom.IndexableObject to a dictionary keyed on its index."""
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
            for i in dList.keys():
                if i in objects:
                    dList[i] = objects.pop(i)
        
    def undo(self):
        """Undo the deletion by reinserting the objects in the dict."""
        for objects, dList in zip(self.objectLists, self.dList):
            for i, o in dList.iteritems():
                if o is not None:
                    objects[i] = o
    
class ImageInput(cvgui.cvImage):
    """A class for taking input from images displayed using OpenCV's highgui features.
    """
    def __init__(self, imageFilename, configFilename=None, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, color=None, lineThickness=1, operationTimeout=30):
        # construct cvGUI object
        super(ImageInput, self).__init__(imageFilename=imageFilename, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents, clickRadius=clickRadius, lineThickness=lineThickness)
        
        # ImageInput-specific properties
        self.configFilename = configFilename
        self.clickRadius = clickRadius
        self.lineThickness = lineThickness
        self.color = cvgui.cvColorCodes[color] if color in cvgui.cvColorCodes else cvgui.cvColorCodes['blue']
        self.operationTimeout = operationTimeout            # amount of time to wait for input when performing a blocking action before the operation times out
        self.clickDown = cvgeom.imagepoint()
        self.clickUp = cvgeom.imagepoint()
        self.mousePos = cvgeom.imagepoint()
        self.lastMousePos = cvgeom.imagepoint()
        self.selectBox = None
        self.clickedOnObject = False
        self.creatingRegion = None
        self.creatingObject = None
        self.userText = ''
        #self.selectedPoints = {}
        
        self.points = cvgeom.ObjectCollection()
        self.regions = cvgeom.ObjectCollection()
        self.objects = cvgeom.ObjectCollection()
        
        # key/mouse bindings
        self.addKeyBindings(['Ctrl + A'], 'selectAll')              # Ctrl + a - select all
        self.addKeyBindings(['DEL', 'Ctrl + D'], 'deleteSelected')  # Delete/Ctrl + d - delete selected points
        self.addKeyBindings(['Ctrl + T'], 'saveConfig')             # Ctrl + s - save points to file
        self.addKeyBindings(['R'], 'createRegion')                  # r - start creating region
        self.addKeyBindings(['N'], 'renameSelectedObject')          # n - (re)name the selected object
        self.addKeyBindings(['C'], 'changeSelectedObjectColor')     # C - change the color of the selected object
        self.addKeyBindings(['ENTER'], 'enterFinish')               # Enter - finish action
        self.addKeyBindings(['ESC'], 'escapeCancel')                # Escape - cancel action
        
        # we'll need these when we're getting text from the user
        self.keyCodeEnter = cvgui.KeyCode('ENTER')
        self.keyCodeEscape = cvgui.KeyCode('ESC')
        self.keyCodeBackspace = cvgui.KeyCode('BACKSPACE')
        
        self.addMouseBindings([cv2.EVENT_LBUTTONDOWN], 'leftClickDown')
        self.addMouseBindings([cv2.EVENT_LBUTTONUP], 'leftClickUp')
        self.addMouseBindings([cv2.EVENT_MOUSEMOVE], 'mouseMove')
        self.addMouseBindings([cv2.EVENT_LBUTTONDBLCLK], 'doubleClick')
        
    def open(self):
        """Open a window and image file and load the point config."""
        self.openWindow()
        self.openImage()
        self.loadConfig()
        
    def loadConfig(self):
        if self.configFilename is not None:
            self.pointConfig = ConfigObj(self.configFilename)
            if self.imageBasename in self.pointConfig:
                print "Loading points and regions from file {} section {}".format(self.configFilename, self.imageBasename)
                imageDict = self.pointConfig[self.imageBasename]
                try:
                    self.loadDict(imageDict)
                except:
                    print traceback.format_exc()
                    print "An error was encountered while loading points from file {}. Please check the formatting.".format(self.configFilename)
        
    def saveConfig(self):
        if self.configFilename is not None:
            print "Saving points and regions to file {} section {}".format(self.configFilename, self.imageBasename)
            imageDict = self.saveDict()
            print imageDict
            self.pointConfig[self.imageBasename] = imageDict
            self.pointConfig.write()
            print "Changes saved!"
        
    def loadDict(self, imageDict):
        self.points = cvgeom.ObjectCollection()
        self.objects = cvgeom.ObjectCollection()
        if '_points' in imageDict:
            print "Loading {} points...".format(len(imageDict['_points']))
            for i, p in imageDict['_points'].iteritems():
                indx = int(i)
                self.points[indx] = cvgeom.imagepoint(int(p[0]), int(p[1]), index=indx, color='default')
                    
        print "Loading {} objects".format(len(imageDict)-1)
        for objindx, objDict in imageDict.iteritems():
            if objindx == '_points':
                continue
            objname = objDict['name']
            objcolor = objDict['color']
            objtype = objDict['type']
            if hasattr(cvgeom, objtype):
                objconstr = getattr(cvgeom, objtype)
                obj = objconstr(index=objindx, name=objname, color=objcolor)
                obj.loadPointDict(objDict['_points'])
                self.objects[objindx] = obj
            else:
                print "Cannot construct object '{}' (name: '{}') of type '{}'".format(objindx, objname, objtype)
        
    def saveDict(self):
        imageDict = {}
        
        # save the points to the _points section
        print "Saving {} points to file {} section {}".format(len(self.points), self.configFilename, self.imageBasename)
        imageDict['_points'] = {}
        for i, p in self.points.iteritems():
            imageDict['_points'][str(i)] = p.asList()
        
        # then add the objects
        print "Saving {} objects to file {} section {}".format(len(self.objects), self.configFilename, self.imageBasename)
        for n, o in self.objects.iteritems():
            # add each object to its own section
            imageDict.update(o.getObjectDict())
        return imageDict
        
    def checkXY(self, x, y):
        """Returns the point or polygon within clickRadius of (x,y) (if there is one)."""
        cp = cvgeom.imagepoint(x,y)
        i = self.points.getClosestObject(cp)                # look for the closest point
        if i is not None:
            p = self.points[i]
            if p.distance(cp) <= self.clickRadius:
                return p                                    # return the closest point if they clicked on one, otherwise check the regions
        i = self.objects.getClosestObject(cp)
        if i is not None:
            r = self.objects[i]
            if r.distance(cp) <= self.clickRadius:
                # return a single point if they clicked on a region's point, otherwise just the region
                rp = r.clickedOnPoint(cp, self.clickRadius)
                if rp is not None:
                    return rp
                else:
                    return r
        
    def enterFinish(self, key=None):
        """Finish whatever multi-step action we are currently performing (e.g.
           creating a polygon, line, etc.)."""
        if self.creatingObject is not None:
            # if we are creating an object, finish it
            print "Finishing {}".format(self.creatingObject.getObjStr())
            self.finishCreatingObject()
        
    def escapeCancel(self, key=None):
        """Cancel whatever multi-step action we are currently performing (e.g.
           creating a polygon, line, etc.)."""
        if self.creatingObject is not None:
            # if we are creating a polygon, finish it
            print "Cancelling {}".format(self.creatingObject.getObjStr())
            self.forgetCreatingObjectPoints()
            self.creatingObject = None
        self.update()
        
    def addPointToObject(self, obj, x, y):
        if obj is not None:
            i = obj.getNextIndex()
            p = cvgeom.imagepoint(x, y, i, color=obj.color)
            a = ObjectAdder(obj.points, p)
            self.do(a)
        
    def addPointToRegion(self, x, y):
        if self.creatingObject is not None:
            # if the region has at least 3 points, check if this click was on the first point
            if len(self.creatingObject.points) >= 3:
                d = self.creatingObject.points[self.creatingObject.getFirstIndex()].distance(cvgeom.imagepoint(x, y))
                if d <= self.clickRadius:
                    # if it was, finish the object
                    self.finishCreatingObject()
            if self.creatingObject is not None:
                self.addPointToObject(self.creatingObject, x, y)
        
    def createRegion(self):
        lastIndx = len(self.regions)
        i = lastIndx + 1
        while i in self.regions:
            i += 1                  # make sure no duplicates
        print "Starting region {}".format(i)
        self.creatingObject = cvgeom.imageregion(i)
        self.creatingObject.select()
        self.update()
        
    def getUserText(self):
        # call waitKey(0) in a while loop to get user input
        self.userText = ""
        timeout = False
        key = 0
        tstart = time.time()
        while not timeout:
            if (time.time() - tstart) > self.operationTimeout:
                timeout = True
            try:
                key = cvgui.KeyCode.clearLocks(cvgui.cv2.waitKey(0))           # clear any modifier flags from NumLock/similar
                if key == self.keyCodeEscape:
                    print "Cancelling..."
                    self.userText = ''
                    return
                elif key == self.keyCodeBackspace:
                    self.userText = self.userText[:-1]          # remove the last character typed
                    self.update()
                elif key == self.keyCodeEnter:
                    break
                c = chr(key)
                if str.isalnum(c) or c in [',']:
                    tstart = time.time()        # restart the timeout counter every time we get input
                    self.userText += c
                    self.update()
            except:
                pass
        if timeout:
            text = None
        else:
            text = str(self.userText)
        self.userText = ''
        return text
        
    def renameObject(self, o, objList):
        print "Renaming {}".format(o.getObjStr())
        name = self.getUserText()
        if name is not None:
            # remove the object under the old key and replace it with the name as the key
            a = ObjectRenamer(objList, o, name)
            self.do(a)
            print "Renamed to {}".format(o.getObjStr())
        else:
            print "Rename cancelled..."
    
    def renameSelectedObject(self, key=None):
        """(Re)name the selected object."""
        for p in self.points.values():
            if p.selected:
                self.renameObject(p, self.points)
                return
        for o in self.objects.values():
            if o.selected:
                self.renameObject(o, self.objects)
                return
        
    def changeObjectColor(self, o):
        """Take input from the user to change an object's color."""
        print "Changing color of {}".format(o.getObjStr())
        color = self.getUserText()
        if color is not None:
            a = ObjectColorChanger(o, color)
            self.do(a)
            print "Changed color of {} to {}".format(o.getObjStr(), color)
        else:
            print "Color change cancelled..."
        
    def changeSelectedObjectColor(self, key=None):
        """Change the color of the selected object."""
        for p in self.points.values():
            if p.selected:
                self.changeObjectColor(p)
                return
        for o in self.objects.values():
            if o.selected:
                self.changeObjectColor(o)
                return
        
    def forgetCreatingObjectPoints(self):
        # before we add the region creation to the action buffer, forget that we added each of the points individually
        for p in self.creatingObject.points.values():
            self.forget()
        
    def finishCreatingObject(self):
        self.forgetCreatingObjectPoints()
        self.creatingObject.deselect()              # make sure to deselect the region
        a = ObjectAdder(self.objects, self.creatingObject)
        self.do(a)
        self.creatingObject = None
        
    def addPoint(self, x, y):
        lastIndx = max(self.points.keys()) if len(self.points) > 0 else 0
        i = lastIndx + 1
        p = cvgeom.imagepoint(x, y, i, color='default')
        a = ObjectAdder(self.points, p)
        self.do(a)
        
    def selectedPoints(self):
        """Get a dict with the selected points."""
        return {i: p for i, p in self.points.iteritems() if p.selected}
        
    def selectedObjects(self):
        """Get a dict with the selected objects."""
        return {i: p for i, p in self.objects.iteritems() if p.selected}
        
    def clearSelected(self):
        """Clear all selected points and regions."""
        #self.selectedPoints = {}
        for p in self.points.values():
            p.deselect()
        for p in self.objects.values():
            p.deselect()
        self.update()
        
    def deleteSelected(self):
        """Delete the points from the list, in a way that can be undone."""
        selp = self.selectedPoints()
        a = ObjectDeleter(self.points, selp)
        selr = self.selectedObjects()
        a.addObjects(self.objects, selr)
        self.do(a)
        
    def selectAll(self):
        """Select all points and regions in the image."""
        for p in self.points.values():
            p.select()
        for o in self.objects.values():
            o.select()
        
    def updateSelection(self):
        """Update the list of selected points to include everything inside the rectangle
           made by self.clickDown and self.mousePos."""
        self.selectBox = box(self.clickDown, self.mousePos)
        for i, p in self.points.iteritems():
            if self.selectBox.contains(p.asShapely()):
                #self.selectPoint(i, p)
                p.select()
        
        # also add any regions that are completely selected
        for i, o in self.objects.iteritems():
            if self.selectBox.contains(o.boundary()):
                o.select()
        self.update()
        
    def moveObjects(self, d):
        """Move all selected regions by (d.x,d.y)."""
        for o in self.objects.values():
            if o.selected:
                o.move(d)
            else:
                # look at all the points and move any that are selected
                for p in o.points.values():
                    if p.selected:
                        p.move(d)
        
    def movePoints(self, d):
        """Move all selected points by (d.x,d.y)."""
        #for p in self.selectedPoints.values():
        for p in self.points.values():
            if p.selected:
                p.move(d)
    
    def drawFrame(self):
        """Show the image in the player with points, selectedPoints, and the selectBox drawn on it."""
        # draw the points on the frame
        for i, p in self.points.iteritems():
            self.drawPoint(p)
            
        # draw all the regions
        for i, p in self.objects.iteritems():
            #if p.selected:
                #print "{} is selected".format(p)
            self.drawRegion(p)
        
        # and the region we're drawing, if it exists
        if self.creatingObject is not None:
            self.drawRegion(self.creatingObject)
            
        # and the box (if there is one)
        if self.selectBox is not None:
            cv2.rectangle(self.img, self.clickDown.asTuple(), self.mousePos.asTuple(), cvgui.cvColorCodes['blue'], thickness=1)
        
        # add any user text to the lower left corner of the window as it is typed in
        if len(self.userText) > 0:
            self.drawText(':' + self.userText, 0, self.imgHeight-10)
        
        # then show the image
        cv2.imshow(self.windowName, self.img)
        
    def setMousePos(self, x, y):
        """Set the current and previous positions of the mouse cursor."""
        self.lastMousePos = self.mousePos
        self.mousePos = cvgeom.imagepoint(x, y)
        
    def isMovingObjects(self):
        """Whether or not we are currently moving objects (points or regions)."""
        if self.clickedOnObject:
            for p in self.points.values():
                if p.selected:
                    return True
            for o in self.objects.values():
                if o.selected:
                    return True
                for p in o.points.values():
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
            self.moveObjects(d)
        else:
            # we are drawing a selection rectangle, so we should update it
            self.updateSelection()
        # update the picture
        self.update()
        
    def leftClickDown(self, event, x, y, flags, param):
        """Process left clicks, which select points and start multi-selection."""
        # record where we click down
        self.clickDown = cvgeom.imagepoint(x, y)
        
        # if we are creating a region, add this point right to the selected region
        if isinstance(self.creatingObject, cvgeom.imageregion):
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
            
            # ignore alt key because it overlaps with NumLock for some reason
            if flags & cv2.EVENT_FLAG_ALTKEY == cv2.EVENT_FLAG_ALTKEY:
                flags -= cv2.EVENT_FLAG_ALTKEY
            
            # then check if modifiers were held down
            if (flags & cv2.EVENT_FLAG_CTRLKEY != cv2.EVENT_FLAG_CTRLKEY) and (flags & cv2.EVENT_FLAG_SHIFTKEY != cv2.EVENT_FLAG_SHIFTKEY):
                # if ctrl or shift weren't held down, clear the selected points
                self.clearSelected()
        self.update()
                
    def leftClickUp(self, event, x, y, flags, param):
        """Process left click up events, which finish moves (recording the action
           for an undo/redo), and stops selection box drawing."""
        # record where we let off the mouse button
        self.clickUp = cvgeom.imagepoint(x, y)
        
        # if we were moving points
        if self.isMovingObjects():
            # we're done with the move, add the complete move to the action buffer so it can be undone
            d = cvgeom.imagepoint(x,y) - self.clickDown
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
        if self.creatingObject is None:
            self.addPoint(x, y)
            self.update()
        