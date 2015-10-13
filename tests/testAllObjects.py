import numpy
import sys
import traceback
import unittest
import lsst.utils.tests as utilsTests

from lsst.sims.catalogs.generation.db import CatalogDBObject
from lsst.sims.catalogs.measures.instance import InstanceCatalog
from lsst.sims.catUtils.exampleCatalogDefinitions import ObsStarCatalogBase
#The following is to get the object ids in the registry
import lsst.sims.catUtils.baseCatalogModels as bcm
import os, inspect

def failedOnFatboy(tracebackList):
    """
    Accepts a list generated by traceback.extract_tb; determines if the last
    point in the sims code in the traceback is _connect_to_engine (from
    sims_catalogs_generation/../db/dbConnection.py), in which case, the failure
    was probably due to fatboy connectivity.
    """
    if not isinstance(tracebackList, list):
        return False

    lastSimsDex = -1
    for ix, item in enumerate(tracebackList):
        if not isinstance(item, tuple):
            return False

        if 'sims' in item[0]:
            lastSimsDex = ix

    if lastSimsDex<0:
        return False

    if '_connect_to_engine' in tracebackList[lastSimsDex][2]:
        return True

    return False


class TestCat(InstanceCatalog):
    catalog_type = 'unit_test_catalog'
    column_outputs = ['raJ2000', 'decJ2000']


class basicAccessTest(unittest.TestCase):

    def testObjects(self):
        ct_connected = 0
        ct_failed_connection = 0

        for objname, objcls in CatalogDBObject.registry.iteritems():
            if not objcls.doRunTest or (objcls.testObservationMetaData is None):
                continue

            print "Running tests for", objname
            try:
                dbobj = objcls(verbose=False)
            except:
                trace = traceback.extract_tb(sys.exc_info()[2], limit=20)
                msg = sys.exc_info()[1].args[0]
                if 'Failed to connect' in msg or failedOnFatboy(trace):

                    # if the exception was due to a failed connection
                    # to fatboy, ignore it

                    ct_failed_connection += 1
                    continue
                else:
                    raise

            obs_metadata = dbobj.testObservationMetaData

            #Get results all at once
            try:
                result = dbobj.query_columns(obs_metadata=obs_metadata)
            except:

                # This is because the solar system object 'tables'
                # don't actually connect to tables on fatboy; they just
                # call methods stored on fatboy.  Therefore, the connection
                # failure will not be noticed until this part of the test

                ct_failed_connection += 1
                msg = sys.exc_info()[1].args[0]
                if 'DB-Lib error' in msg:
                    continue

            ct_connected += 1

            #Since there is only one chunck,
            try:
                result = result.next()
            except StopIteration:
                raise RuntimeError("No results for %s defined in %s"%(objname,
                       inspect.getsourcefile(dbobj.__class__)))
            if objname.startswith('galaxy'):
                TestCat.column_outputs = ['galid', 'raJ2000', 'decJ2000']
            else:
                TestCat.column_outputs = ['raJ2000', 'decJ2000']
            cat = dbobj.getCatalog('unit_test_catalog', obs_metadata)
            if os.path.exists('testCat.out'):
                os.unlink('testCat.out')
            try:
                cat.write_catalog('testCat.out')
            finally:
                if os.path.exists('testCat.out'):
                    os.unlink('testCat.out')

        print '\n================'
        print 'Do not worry about this message'
        print 'sometimes, connections to the UW database fail.'
        print 'It is expected.'
        print 'This is just a tally so that you know how often that happened.'
        print 'successful connections: ', ct_connected
        print 'failed connections: ', ct_failed_connection

    def testObsCat(self):
        objname = 'wdstars'

        try:
            dbobj = CatalogDBObject.from_objid(objname)
            obs_metadata = dbobj.testObservationMetaData
            # To cover the central ~raft
            obs_metadata.boundLength = 0.4
            opsMetadata = {'Opsim_rotskypos':(0., float),
                           'Unrefracted_RA':(numpy.radians(obs_metadata.unrefractedRA), float),
                           'Unrefracted_Dec':(numpy.radians(obs_metadata.unrefractedDec), float)}
            obs_metadata.phoSimMetaData = opsMetadata
            cat = dbobj.getCatalog('obs_star_cat', obs_metadata)
            if os.path.exists('testCat.out'):
                os.unlink('testCat.out')
            try:
                cat.write_catalog('testCat.out')
            finally:
                if os.path.exists('testCat.out'):
                    os.unlink('testCat.out')

            print '\ntestObsCat successfully connected to fatboy'

        except:
            trace = traceback.extract_tb(sys.exc_info()[2], limit=20)
            msg = sys.exc_info()[1].args[0]
            if 'Failed to connect' in msg or failedOnFatboy(trace):

                # if the exception was because of a failed connection
                # to fatboy, ignore it.

                print '\ntestObsCat failed to connect to fatboy'
                print 'Sometimes that happens.  Do not worry.'

                pass
            else:
                raise


def suite():
    utilsTests.init()
    suites = []
    suites += unittest.makeSuite(basicAccessTest)
    suites += unittest.makeSuite(utilsTests.MemoryTestCase)

    return unittest.TestSuite(suites)

def run(shouldExit = False):
    utilsTests.run(suite(), shouldExit)
if __name__ == "__main__":
    run(True)
