import weakref
from robofab.pens.pointPen import BasePointToSegmentPen, AbstractPointPen
from robofab.objects.objectsBase import addPt, subPt, mulPt, BaseGlyph

"""
to do:
X anchors
- components
  - identifiers
- contours
  - identifiers
- points
  - identifiers
- guidelines
- height

- is there any cruft that can be removed?
- why is divPt here? move all of those to the math functions and get rid of the robofab dependency.
"""


def divPt(pt, factor):
    if not isinstance(factor, tuple):
        f1 = factor
        f2 = factor
    else:
        f1, f2 = factor
    return pt[0] / f1, pt[1] / f2


class MathGlyphPen(AbstractPointPen):

    """
    Point pen for building MathGlyph data structures.
    """

    def __init__(self):
        self.contours = []
        self.components = []
        self._points = []

    def _flushContour(self):
        points = self._points
        self.contours.append([])
        prevOnCurve = None
        offCurves = []
        # deal with the first point
        segmentType, pt, smooth, name = points[0]
        # if it is an offcurve, add it to the offcurve list
        if segmentType is None:
            offCurves.append((segmentType, pt, smooth, name))
        # if it is a line, change the type to curve and add it to the contour
        # create offcurves corresponding with the last oncurve and
        # this point and add them to the points list
        elif segmentType == "line":
            prevOnCurve = pt
            self.contours[-1].append(("curve", pt, False, name))
            lastPoint = points[-1][1]
            points.append((None, lastPoint, False, None))
            points.append((None, pt, False, None))
        # a move, curve or qcurve. simple append the data.
        else:
            self.contours[-1].append((segmentType, pt, smooth, name))
            prevOnCurve = pt
        # now go through the rest of the points
        for segmentType, pt, smooth, name in points[1:]:
            # store the off curves
            if segmentType is None:
                offCurves.append((segmentType, pt, smooth, name))
                continue
            # make off curve corresponding the the previous
            # on curve an dthis point
            if segmentType == "line":
                segmentType = "curve"
                offCurves.append((None, prevOnCurve, False, None))
                offCurves.append((None, pt, False, None))
            # add the offcurves to the contour
            for offCurve in offCurves:
                self.contours[-1].append(offCurve)
            # add the oncurve to the contour
            self.contours[-1].append((segmentType, pt, smooth, name))
            # reset the stored data
            prevOnCurve = pt
            offCurves = []
        # catch offcurves that belong to the first
        if len(offCurves) != 0:
            self.contours[-1].extend(offCurves)

    def beginPath(self):
        self._points = []

    def addPoint(self, pt, segmentType=None, smooth=False, name=None, **kwargs):
        self._points.append((segmentType, pt, smooth, name))

    def endPath(self):
        self._flushContour()

    def addComponent(self, baseGlyph, transformation, identifier=None, **kwargs):
        self.components.append(dict(baseGlyph=baseGlyph, transformation=transformation, identifier=identifier))


class FilterRedundantPointPen(AbstractPointPen):

    def __init__(self, anotherPointPen):
        self._pen = anotherPointPen
        self._points = []

    def _flushContour(self):
        points = self._points
        prevOnCurve = None
        offCurves = []
            
        pointsToDraw = []
            
        # deal with the first point
        pt, segmentType, smooth, name = points[0]
        # if it is an offcurve, add it to the offcurve list
        if segmentType is None:
            offCurves.append((pt, segmentType, smooth, name))
        else:
            # potential redundancy
            if segmentType == "curve":
                # gather preceding off curves
                testOffCurves = []
                lastPoint = None
                for i in xrange(len(points)):
                    i = -i - 1
                    testPoint = points[i]
                    testSegmentType = testPoint[1]
                    if testSegmentType is not None:
                        lastPoint = testPoint[0]
                        break
                    testOffCurves.append(testPoint[0])
                # if two offcurves exist we can test for redundancy
                if len(testOffCurves) == 2:
                    if testOffCurves[1] == lastPoint and testOffCurves[0] == pt:
                        segmentType = "line"
                        # remove the last two points
                        points = points[:-2]
            # add the point to the contour
            pointsToDraw.append((pt, segmentType, smooth, name))
            prevOnCurve = pt
        for pt, segmentType, smooth, name in points[1:]:
            # store offcurves
            if segmentType is None:
                offCurves.append((pt, segmentType, smooth, name))
                continue
            # curves are a potential redundancy
            elif segmentType == "curve":
                if len(offCurves) == 2:
                    # test for redundancy
                    if offCurves[0][0] == prevOnCurve and offCurves[1][0] == pt:
                        offCurves = []
                        segmentType = "line"
            # add all offcurves
            for offCurve in offCurves:
                pointsToDraw.append(offCurve)
            # add the on curve
            pointsToDraw.append((pt, segmentType, smooth, name))
            # reset the stored data
            prevOnCurve = pt
            offCurves = []
        # catch any remaining offcurves
        if len(offCurves) != 0:
            for offCurve in offCurves:
                pointsToDraw.append(offCurve)
        # draw to the pen
        for pt, segmentType, smooth, name in pointsToDraw:
            self._pen.addPoint(pt, segmentType, smooth, name)

    def beginPath(self):
        self._points = []
        self._pen.beginPath()

    def addPoint(self, pt, segmentType=None, smooth=False, name=None, **kwargs):
        self._points.append((pt, segmentType, smooth, name))

    def endPath(self):
        self._flushContour()
        self._pen.endPath()

    def addComponent(self, baseGlyph, transformation, identifier=None, **kwargs):
        self._pen.addComponent(baseGlyph, transformation, identifier)


class MathGlyph(object):

    """
    A very shallow glyph object for rapid math operations.

    This glyph differs from a standard RGlyph in many ways.
    Most notably "line" segments do not exist. This is done
    to make contours more compatible.

    Notes about glyph math:
    -   absolute contour compatibility is required
    -   absolute comoponent and anchor compatibility is NOT required. in cases
        of incompatibility in this data, only compatible data is processed and
        returned. becuase of this, anchors and components may not be returned
        in the same order as the original.

    If a MathGlyph is created by another glyph that is not another MathGlyph instance,
    a weakref that points to the original glyph is maintained.
    """

    def __init__(self, glyph):
        self._structure = None
        if glyph is None:
            self.contours = []
            self.components = []
            self.anchors = []
            self.lib = {}
            #
            self.name = None
            self.unicodes = None
            self.width = None
            self.note = None
            self.generationCount = 0
        else:
            p = MathGlyphPen()
            glyph.drawPoints(p)
            self.contours = p.contours
            self.components = p.components
            self.lib = {}
            #
            self.name = glyph.name
            self.unicodes = glyph.unicodes
            self.width = glyph.width
            self.note = glyph.note
            self.anchors = [dict(anchor) for anchor in glyph.anchors]
            #
            for k, v in glyph.lib.items():
                self.lib[k] = v
            #
            # set a weakref for the glyph
            # ONLY if it is not a MathGlyph.
            # this could happen as a result
            # of a MathGlyph.copy()
            if not isinstance(glyph, MathGlyph):
                self.getRef = weakref.ref(glyph)
                self.generationCount = 0
            else:
                self.generationCount = glyph.generationCount + 1

    def getRef(self):
        """
        return the original glyph that self was built from.
        this will return None if self was built from
        another MathGlyph instance
        """
        # overriden by weakref.ref if present
        return None

    def _get_structure(self):
        if self._structure is not None:
            return self._structure
        contourStructure = []
        for contour in self.contours:
            contourStructure.append([segmentType for segmentType, pt, smooth, name in contour])
        componentStructure = [baseName for baseName, transformation, identifier in self.components]
        anchorStructure = [anchor["name"] for anchor in self.anchors]
        return contourStructure, componentStructure, anchorStructure

    structure = property(_get_structure, doc="returns a tuple of (contour structure, component structure, anchor structure)")

    def _get_box(self):
        from fontTools.pens.boundsPen import BoundsPen
        bP = BoundsPen(None)
        self.draw(bP)
        return bP.bounds

    box = property(_get_box, doc="Bounding rect for self. Returns None is glyph is empty. This DOES NOT measure components.")

    def copy(self):
        """return a new MathGlyph containing all data in self"""
        return MathGlyph(self)

    def copyWithoutIterables(self):
        """
        return a new MathGlyph containing all data except:
        contours
        components
        anchors
        
        this is used mainly for internal glyph math.
        """
        n = MathGlyph(None)
        n.generationCount = self.generationCount + 1
        #
        n.name = self.name
        n.unicodes = self.unicodes
        n.width = self.width
        n.note = self.note
        #
        for k, v in self.lib.items():
            n.lib[k] = v
        return n

    # math with other glyph

    def __add__(self, otherGlyph):
        copiedGlyph = self.copyWithoutIterables()
        self._processMathOne(copiedGlyph, otherGlyph, addPt)
        copiedGlyph.width = self.width + otherGlyph.width
        return copiedGlyph

    def __sub__(self, otherGlyph):
        copiedGlyph = self.copyWithoutIterables()
        self._processMathOne(copiedGlyph, otherGlyph, subPt)
        copiedGlyph.width = self.width - otherGlyph.width
        return copiedGlyph

    def _processMathOne(self, copiedGlyph, otherGlyph, funct):
        # contours
        copiedGlyph.contours = []
        if len(self.contours) > 0:
            for contourIndex in range(len(self.contours)):
                copiedGlyph.contours.append([])
                selfContour = self.contours[contourIndex]
                otherContour = otherGlyph.contours[contourIndex]
                for pointIndex in range(len(selfContour)):
                    segType, pt, smooth, name = selfContour[pointIndex]
                    newX, newY = funct(selfContour[pointIndex][1], otherContour[pointIndex][1])
                    copiedGlyph.contours[-1].append((segType, (newX, newY), smooth, name))
        # anchors
        copiedGlyph.anchors = []
        if len(self.anchors) > 0:
            anchorTree1 = _anchorTree(self.anchors)
            anchorTree2 = _anchorTree(otherGlyph.anchors)
            anchorPairs = _pairAnchors(anchorTree1, anchorTree2)
            copiedGlyph.anchors = _processMathOneAnchors(anchorPairs)
        # components
        copiedGlyph.components = []
        if len(self.components) > 0:
            componentPairs = _pairComponents(self.components, other.components)
            copiedGlyph.components = _processMathOneComponents(componentPairs)

    # math with factor

    def __mul__(self, factor):
        if not isinstance(factor, tuple):
            factor = (factor, factor)
        copiedGlyph = self.copyWithoutIterables()
        self._processMathTwo(copiedGlyph, factor, mulPt)
        copiedGlyph.width = self.width * factor[0]
        return copiedGlyph

    __rmul__ = __mul__

    def __div__(self, factor):
        if not isinstance(factor, tuple):
            factor = (factor, factor)
        copiedGlyph = self.copyWithoutIterables()
        self._processMathTwo(copiedGlyph, factor, divPt)
        copiedGlyph.width = self.width / factor[0]
        return copiedGlyph

    __rdiv__ = __div__

    def _processMathTwo(self, copiedGlyph, factor, funct):
        # contours
        copiedGlyph.contours = []
        if len(self.contours) > 0:
            for selfContour in self.contours:
                copiedGlyph.contours.append([])
                for segType, pt, smooth, name in selfContour:
                    newX, newY = funct(pt, factor)
                    copiedGlyph.contours[-1].append((segType, (newX, newY), smooth, name))
        # anchors
        copiedGlyph.anchors = []
        if len(self.anchors) > 0:
            copiedGlyph.anchors = _processMathTwoAnchors(anchor, factor, funct)
        # components
        copiedGlyph.components = []
        if len(self.components) > 0:
            copiedGlyph.components = _processMathTwoComponents(self.components, factor, funct)



    def __repr__(self):
        return "<MathGlyph %s>" % self.name

    def __cmp__(self, other):
        flag = False
        if self.name != other.name:
            flag = True
        if self.unicodes != other.unicodes:
            flag = True
        if self.width != other.width:
            flag = True
        if self.note != other.note:
            flag = True
        if self.lib != other.lib:
            flag = True
        if self.contours != other.contours:
            flag = True
        if self.components != other.components:
            flag = True
        if self.anchors != other.anchors:
            flag = True
        return flag

    def drawPoints(self, pointPen):
        """draw self using pointPen"""
        for contour in self.contours:
            pointPen.beginPath()
            for segmentType, pt, smooth, name in contour:
                pointPen.addPoint(pt=pt, segmentType=segmentType, smooth=smooth, name=name)
            pointPen.endPath()
        for baseName, transformation in self.components:
            pointPen.addComponent(baseName, transformation)

    def draw(self, pen):
        """draw self using pen"""
        from robofab.pens.adapterPens import PointToSegmentPen
        pointPen = PointToSegmentPen(pen)
        self.drawPoints(pointPen)

    def extractGlyph(self, glyph, pointPen=None):
        """
        "rehydrate" to a glyph. this requires
        a glyph as an argument. if a point pen other
        than the type of pen returned by glyph.getPointPen()
        is required for drawing, send this the needed point pen.
        """
        if pointPen is None:
            pointPen = glyph.getPointPen()
        glyph.clearContours()
        glyph.clearComponents()
        glyph.clearAnchors()
        glyph.lib.clear()
        #
        cleanerPen = FilterRedundantPointPen(pointPen)
        self.drawPoints(cleanerPen)
        #
        glyph.name = self.name
        glyph.unicodes = self.unicodes
        glyph.width = self.width
        glyph.note = self.note
        glyph.anchors = self.anchors
        #
        for k, v in self.lib.items():
            glyph.lib[k] = v
        return glyph

    def isCompatible(self, otherGlyph, testContours=True, testComponents=False, testAnchors=False):
        """
        returns a True if otherGlyph is compatible with self.

        because absolute compatibility is not required for
        anchors and components in glyph math operations
        this method does not test compatibility on that data
        by default. set the flags to True to test for that data.
        """
        other = otherGlyph
        selfContourStructure, selfComponentStructure, selfAnchorStructure = self.structure
        otherContourStructure, otherComponentStructure, otherAnchorStructure = other.structure
        result = True
        if testContours:
            if selfContourStructure != otherContourStructure:
                result = False
        if testComponents:
            if selfComponentStructure != otherComponentStructure:
                result = False
        if testAnchors:
            if selfAnchorStructure != otherAnchorStructure:
                result = False
        return result


# -------
# Support
# -------

# anchors

def _anchorTree(anchors):
    """
    >>> anchors = [
    ...     dict(identifier="1", name="test", x=1, y=2, color=None),
    ...     dict(name="test", x=1, y=2, color=None),
    ...     dict(name="test", x=3, y=4, color=None),
    ...     dict(name="test", x=2, y=3, color=None),
    ...     dict(name="test 2", x=1, y=2, color=None),
    ... ]
    >>> expected = {
    ...     "test" : [
    ...         ("1", 1, 2, None),
    ...         (None, 1, 2, None),
    ...         (None, 3, 4, None),
    ...         (None, 2, 3, None),
    ...     ],
    ...     "test 2" : [
    ...         (None, 1, 2, None)
    ...     ]
    ... }
    >>> _anchorTree(anchors) == expected
    True
    """
    tree = {}
    for anchor in anchors:
        x = anchor["x"]
        y = anchor["y"]
        name = anchor.get("name")
        identifier = anchor.get("identifier")
        color = anchor.get("color")
        if name not in tree:
            tree[name] = []
        tree[name].append((identifier, x, y, color))
    return tree

def _pairAnchors(anchorDict1, anchorDict2):
    """
    Anchors are paired using the following rules:


    Matching Identifiers
    --------------------
    >>> anchors1 = {
    ...     "test" : [
    ...         (None, 1, 2, None),
    ...         ("identifier 1", 3, 4, None)
    ...      ]
    ... }
    >>> anchors2 = {
    ...     "test" : [
    ...         ("identifier 1", 1, 2, None),
    ...         (None, 3, 4, None)
    ...      ]
    ... }
    >>> expected = [
    ...     (
    ...         dict(name="test", identifier=None, x=1, y=2, color=None),
    ...         dict(name="test", identifier=None, x=3, y=4, color=None)
    ...     ),
    ...     (
    ...         dict(name="test", identifier="identifier 1", x=3, y=4, color=None),
    ...         dict(name="test", identifier="identifier 1", x=1, y=2, color=None)
    ...     )
    ... ]
    >>> _pairAnchors(anchors1, anchors2) == expected
    True

    Mismatched Identifiers
    ----------------------
    >>> anchors1 = {
    ...     "test" : [
    ...         ("identifier 1", 3, 4, None)
    ...      ]
    ... }
    >>> anchors2 = {
    ...     "test" : [
    ...         ("identifier 2", 1, 2, None),
    ...      ]
    ... }
    >>> expected = [
    ...     (
    ...         dict(name="test", identifier="identifier 1", x=3, y=4, color=None),
    ...         dict(name="test", identifier="identifier 2", x=1, y=2, color=None)
    ...     )
    ... ]
    >>> _pairAnchors(anchors1, anchors2) == expected
    True
    """
    pairs = []
    for name, anchors1 in anchorDict1.items():
        if name not in anchorDict2:
            continue
        anchors2 = anchorDict2[name]
        # align with matching identifiers
        removeFromAnchors1 = []
        for anchor1 in anchors1:
            match = None
            identifier = anchor1[0]
            for anchor2 in anchors2:
                if anchor2[0] == identifier:
                    match = anchor2
                    break
            if match is not None:
                anchor2 = match
                anchors2.remove(anchor2)
                removeFromAnchors1.append(anchor1)
                a1 = dict(name=name, identifier=identifier)
                a1["x"], a1["y"], a1["color"] = anchor1[1:]
                a2 = dict(name=name, identifier=identifier)
                a2["x"], a2["y"], a2["color"] = anchor2[1:]
                pairs.append((a1, a2))
        for anchor1 in removeFromAnchors1:
            anchors1.remove(anchor1)
        if not anchors1 or not anchors2:
            continue
        # align by index
        while 1:
            anchor1 = anchors1.pop(0)
            anchor2 = anchors2.pop(0)
            a1 = dict(name=name)
            a1["identifier"], a1["x"], a1["y"], a1["color"] = anchor1
            a2 = dict(name=name, identifier=identifier)
            a2["identifier"], a2["x"], a2["y"], a2["color"] = anchor2
            pairs.append((a1, a2))
            if not anchors1:
                break
            if not anchors2:
                break
    return pairs

def _processMathOneAnchors(anchorPairs, funct):
    """
    >>> anchorPairs = [
    ...     (
    ...         dict(x=100, y=-100, name="foo", identifier="1", color="0,0,0,0"),
    ...         dict(x=200, y=-200, name="bar", identifier="2", color="1,1,1,1")
    ...     )
    ... ]
    >>> expected = [
    ...     dict(x=300, y=-300, name="foo", identifier="1", color="0,0,0,0")
    ... ]
    >>> _processMathOneAnchors(anchorPairs, addPt) == expected
    True
    """
    result = []
    for anchor1, anchor2 in anchorPairs:
        anchor = dict(anchor1)
        pt1 = (anchor1["x"], anchor1["y"])
        pt2 = (anchor2["x"], anchor2["y"])
        anchor["x"], anchor["y"] = funct(pt1, pt2)
        result.append(anchor)
    return result

def _processMathTwoAnchors(anchors, factor, funct):
    """
    >>> anchors = [
    ...     dict(x=100, y=-100, name="foo", identifier="1", color="0,0,0,0")
    ... ]
    >>> expected = [
    ...     dict(x=200, y=-150, name="foo", identifier="1", color="0,0,0,0")
    ... ]
    >>> _processMathTwoAnchors(anchors, (2, 1.5), mulPt) == expected
    True
    """
    result = []
    for anchor in anchors:
        anchor = dict(anchor)
        pt = (anchor["x"], anchor["y"])
        anchor["x"], anchor["y"] = funct(pt, factor)
        result.append(anchor)
    return result

# components

def _pairComponents(components1, components2):
    """
    >>> components1 = [
    ...     dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier="1"),
    ...     dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier="1"),
    ...     dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None)
    ... ]
    >>> components2 = [
    ...     dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None),
    ...     dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier="1"),
    ...     dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier="1")
    ... ]
    >>> expected = [
    ...     (
    ...         dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier="1"),
    ...         dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier="1")
    ...     ),
    ...     (
    ...         dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier="1"),
    ...         dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier="1")
    ...     ),
    ...     (
    ...         dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None),
    ...         dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None)
    ...     ),
    ... ]
    >>> _pairComponents(components1, components2) == expected
    True

    >>> components1 = [
    ...     dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None),
    ...     dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier=None)
    ... ]
    >>> components2 = [
    ...     dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier=None),
    ...     dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None)
    ... ]
    >>> expected = [
    ...     (
    ...         dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None),
    ...         dict(baseGlyph="A", transformation=(0, 0, 0, 0, 0, 0), identifier=None)
    ...     ),
    ...     (
    ...         dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier=None),
    ...         dict(baseGlyph="B", transformation=(0, 0, 0, 0, 0, 0), identifier=None)
    ...     ),
    ... ]
    >>> _pairComponents(components1, components2) == expected
    True
    """
    components1 = list(components1)
    components2 = list(components2)
    pairs = []
    # align with matching identifiers
    removeFromComponents1 = []
    for component1 in components1:
        baseGlyph = component1["baseGlyph"]
        identifier = component1["identifier"]
        match = None
        for component2 in components2:
            if component2["baseGlyph"] == baseGlyph and component2["identifier"] == identifier:
                match = component2
                break
        if match is not None:
            component2 = match
            removeFromComponents1.append(component1)
            components2.remove(component2)
            pairs.append((component1, component2))
    for component1 in removeFromComponents1:
        components1.remove(component1)
    # align with index
    for component1 in components1:
        baseGlyph = component1["baseGlyph"]
        for component2 in components2:
            if component2["baseGlyph"] == baseGlyph:
                components2.remove(component2)
                pairs.append((component1, component2))
                break
    return pairs

def _processMathOneComponents(componentPairs, funct):
    """
    >>> components = [
    ...    (
    ...        dict(baseGlyph="A", transformation=( 1,  3,  5,  7,  9, 11), identifier="1"),
    ...        dict(baseGlyph="A", transformation=(12, 14, 16, 18, 20, 22), identifier=None)
    ...    )
    ... ]
    >>> expected = [
    ...     dict(baseGlyph="A", transformation=(13, 17, 21, 25, 29, 33), identifier="1")
    ... ]
    >>> _processMathOneComponents(components, addPt) == expected
    True
    """
    result = []
    for component1, component2 in componentPairs:
        component = dict(component1)
        xScale1, xyScale1, yxScale1, yScale1, xOffset1, yOffset1 = component1["transformation"]
        xScale2, xyScale2, yxScale2, yScale2, xOffset2, yOffset2 = component2["transformation"]
        xScale, yScale = funct((xScale1, yScale1), (xScale2, yScale2))
        xyScale, yxScale = funct((xyScale1, yxScale1), (xyScale2, yxScale2))
        xOffset, yOffset = funct((xOffset1, yOffset1), (xOffset2, yOffset2))
        component["transformation"] = (xScale, xyScale, yxScale, yScale, xOffset, yOffset)
        result.append(component)
    return result

def _processMathTwoComponents(components, factor, funct):
    """
    >>> components = [
    ...     dict(baseGlyph="A", transformation=(1, 2, 3, 4, 5, 6), identifier="1"),
    ... ]
    >>> expected = [
    ...     dict(baseGlyph="A", transformation=(2, 4, 4.5, 6, 10, 9), identifier="1")
    ... ]
    >>> _processMathTwoComponents(components, (2, 1.5), mulPt) == expected
    True
    """
    result = []
    for component in components:
        component = dict(component)
        xScale, xyScale, yxScale, yScale, xOffset, yOffset = component["transformation"]
        xScale, yScale = funct((xScale, yScale), factor)
        xyScale, yxScale = funct((xyScale, yxScale), factor)
        xOffset, yOffset = funct((xOffset, yOffset), factor)
        component["transformation"] = (xScale, xyScale, yxScale, yScale, xOffset, yOffset)
        result.append(component)
    return result


if __name__ == "__main__":
    import doctest
    doctest.testmod()
