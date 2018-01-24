#!/usr/bin/env python

# inst: university of bristol
# auth: jeison sosa
# date: 29/apr/2017
# mail: sosa.jeison@gmail.com / j.sosa@bristol.ac.uk

import os
import sys
import subprocess
import ConfigParser
import getopt
import numpy as np
import shapefile as sf
from gdal_utils import *
from osgeo import osr
from scipy.spatial.distance import cdist
from scipy.optimize import fsolve


def getdepths(argv):

    opts, args = getopt.getopt(argv,"i:")
    for o, a in opts:
        if o == "-i": inifile  = a

    config = ConfigParser.SafeConfigParser()
    config.read(inifile)

    proj   = str(config.get('getdepths','proj'))
    netf   = str(config.get('getdepths','netf'))
    method = str(config.get('getdepths','method'))
    output = str(config.get('getdepths','output'))

    print "    runnning get_depths.py..."

    try:
        fdepth = str(config.get('getdepths','fdepth'))
        thresh = np.float64(config.get('getdepths','thresh'))
    except: pass

    try:
        wdtf = str(config.get('getdepths','wdtf'))
        r    = np.float64(config.get('getdepths','r'))
        p    = np.float64(config.get('getdepths','p'))
    except: pass

    try:
        n     = np.float64(config.get('getdepths','n'))
        wdtf  = str(config.get('getdepths','wdtf'))
        slpf  = str(config.get('getdepths','slpf'))
        qbnkf = str(config.get('getdepths','qbnkf'))
    except: pass

    fname = output

    w = sf.Writer(sf.POINT)
    w.field('x')
    w.field('y')
    w.field('depth')
    
    if method == "depth_raster":
        depth_raster(w,path,catchment,thresh)
    elif method == "depth_geometry":
        depth_geometry(w,r,p,wdtf)
    elif method == "depth_manning":
        depth_manning(w,n,qbnkf,slpf,wdtf)
    else:
        print "ESPECIFY A METHOD"
        sys.exit()

    # write final value in a shapefile
    w.save("%s.shp" % fname)

    # write .prj file
    prj = open("%s.prj" % fname, "w")
    srs = osr.SpatialReference()
    srs.ImportFromProj4(proj)
    prj.write(srs.ExportToWkt())
    prj.close()

    nodata = -9999
    fmt    = "GTiff"
    name1  = output+".shp"
    name2  = output+".tif"
    mygeo  = get_gdal_geo(netf)
    subprocess.call(["gdal_rasterize","-a_nodata",str(nodata),"-of",fmt,"-tr",str(mygeo[6]),str(mygeo[7]),"-a","depth","-a_srs",proj,"-te",str(mygeo[0]),str(mygeo[1]),str(mygeo[2]),str(mygeo[3]),name1,name2])

def depth_raster(w,fdepth,path,catchment,thresh):

    """
    NOT WORKING PATH AND CATCHMENT VARIABLES WERE MODIFIED
    """

    # Uses the river network file in each catchment (Ex. 276_net30.tif)
    net   = get_gdal_data(path+"/"+catchment+"/"+catchment+"_net30.tif")
    geo   = get_gdal_geo(path+"/"+catchment+"/"+catchment+"_net30.tif")
    iy,ix = np.where(net>0)
    x     = geo[8][ix]
    y     = geo[9][iy]

    for i in range(len(x)):

        print "getdepths.py - " + str(len(x)-i)
        
        xmin  = x[i] - thresh
        ymin  = y[i] - thresh
        xmax  = x[i] + thresh
        ymax  = y[i] + thresh

        depth,depth_geo = clip_raster(fdepth,xmin,ymin,xmax,ymax)

        mydepth = nearpixel(depth,depth_geo[8],depth_geo[9],np.array([[y[i],x[i]]])) # nearest pixel river
        
        w.point(x[i],y[i])
        w.record(x[i],y[i],mydepth)
    return w
 
def depth_geometry(w,r,p,wdtf):

    width = np.array(sf.Reader(wdtf).records(),dtype='float64')
    x     = width[:,0]
    y     = width[:,1]

    for i in range(width.shape[0]):

        print "getdepths.py - " + str(width.shape[0]-i)

        mydepth = r*width[i,2]**p

        w.point(x[i],y[i])
        w.record(x[i],y[i],mydepth)
    
    return w

def depth_manning(f,n,qbnkf,slpf,wdtf):

    # load width shapefile
    width = np.array(sf.Reader(wdtf).records(),dtype='float64')
    xw    = width[:,0]
    yw    = width[:,1]

    qbnk  = np.array(sf.Reader(qbnkf).records(),dtype='float64')
    xq    = qbnk[:,0]
    yq    = qbnk[:,1]

    slope = np.array(sf.Reader(slpf).records(),dtype='float64')
    xs    = slope[:,0]
    ys    = slope[:,1]

    # iterate over every width x-y pair in the shapefile
    for i in range(width.shape[0]):

        # get index for Q and S based on W coordinates
        iiq = near(yq,xq,np.array([[xw[i],yw[i]]]))
        iis = near(ys,xs,np.array([[xw[i],yw[i]]]))

        # DEBUG DEBUG DEBUG
        # print xw[i],yw[i]
        # print xq[iiq],yq[iiq]
        # print xs[iis],ys[iis]
        if (xw[i]!=xq[iiq]) | (xw[i]!=xs[iis]) | (yw[i]!=yq[iiq]) | (yw[i]!=ys[iis]):
            sys.exit("Coordinates are not equal")

        w = width[i,2]
        q = qbnk[iiq,2]
        s = slope[iis,2]

        data = (q,w,s,n)

        # # depth by using a full version of the mannings equation (solve numerically)
        # mydepth = fsolve(manning_depth,0,args=data)
        # f.point(xw[i],yw[i])
        # f.record(xw[i],yw[i],mydepth[0])

        # depth by using a simplified version of the mannings equation
        mydepth = manning_depth_simplified(data)
        # mydepth = 20 # DEBUG-DEBUG-DEBUG
        
        f.point(xw[i],yw[i])
        f.record(xw[i],yw[i],mydepth)
        # f.record(xw[i],yw[i],mydepth*10)
    
    return f

def nearpixel(array,ddsx,ddsy,XA):

    """
    Find nearest pixel

    array: array with sourcedata
    ddsx: 1-dim array with longitudes of array
    ddsy: 1-dim array with latitudes of array
    XA: point

    """
    _ds    = np.where(array>0)

    # if there are river pixels in the window
    if _ds[0].size >0 :
        XB  = np.vstack((ddsy[_ds[0]],ddsx[_ds[1]])).T
        ind = np.int(cdist(XA, XB, metric='euclidean').argmin())
        res = array[_ds[0][ind],_ds[1][ind]]
    else:
        res = -9999
    
    return res

def manning_depth(d,*data):
    q,w,s,n = data
    return q*n/s**0.5-w*d*(w*d/(2*d+w))**(2/3)

def manning_depth_simplified(data):
    q = data[0]
    w = data[1]
    s = data[2]
    n = data[3]
    return ((q*n)/(s**0.5*w))**(3/5.)

def near(ddsx,ddsy,XA):

    XB  = np.vstack((ddsy,ddsx)).T
    dis = cdist(XA, XB, metric='euclidean').argmin()

    return dis

if __name__ == '__main__':
    getdepths(sys.argv[1:])