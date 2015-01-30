import os
import unittest
import numpy
from collections import OrderedDict
import lsst.utils.tests as utilsTests
from lsst.sims.catUtils.utils import ObservationMetaDataGenerator
from lsst.sims.catalogs.generation.db import CatalogDBObject, CircleBounds, BoxBounds
from lsst.sims.catUtils.baseCatalogModels import GalaxyBulgeObj, GalaxyDiskObj, GalaxyAgnObj, StarObj
from lsst.sims.catUtils.exampleCatalogDefinitions import PhoSimCatalogSersic2D
from lsst.sims.catalogs.generation.utils import makePhoSimTestDB

#28 January 2015
#SearchReversion and testGalaxyBulge are duplicated from testPhoSimCatalogs.py
#There is already a pull request outstanding that will move
#these classes to a testUtils.py file in sims_catUtils/../utils/
#Once that pull request is merged, I will clean this file up
#and remove the duplicated code.
class SearchReversion(CatalogDBObject):
    """
    This is a mixin which is used below to force the galaxy CatalogDBObjects created for
    this unittest to use the methods defined in the CatalogDBObject class.  This is because
    we are using classes which inherit from GalaxyTileObj but do not actually want to use
    the tiled query routines.

    We also use this mixin for our stellar database object.  This is because StarObj
    implements a query search based on htmid, which the test database for this unit
    test will not have.
    """

    def _get_column_query(self, *args, **kwargs):
        return CatalogDBObject._get_column_query(self,*args, **kwargs)

    def _final_pass(self, *args, **kwargs):
        return CatalogDBObject._final_pass(self,*args, **kwargs)

    def query_columns(self, *args, **kwargs):
        return CatalogDBObject.query_columns(self, *args, **kwargs)

class testGalaxyBulge(SearchReversion, GalaxyBulgeObj):
    """
    A class for storing galaxy bulges
    """
    objid = 'phoSimTestBulges'
    objectTypeId = 88

    #The code below makes sure that we can store RA, Dec in degrees
    #in the database but use radians in our calculations.
    #We had to overwrite the original columns list because
    #GalaxyTileObject daughter classes assume that RA and Dec are stored
    #in radians in the database.  This is a side effect of the tiling
    #scheme used to cover the whole sky.

    columns = GalaxyBulgeObj.columns
    _to_remove = []
    for entry in columns:
        if entry[0] == 'raJ2000' or entry[0] == 'decJ2000':
            _to_remove.append(entry)
    for target in _to_remove:
        columns.remove(target)

    columns.append(('raJ2000','ra*PI()/180.'))
    columns.append(('decJ2000','dec*PI()/180.'))

class ObservationMetaDataGeneratorTest(unittest.TestCase):

    def testExceptions(self):
        """
        Make sure that RuntimeErrors get raised when they should
        """
        gen = ObservationMetaDataGenerator()
        self.assertRaises(RuntimeError, gen.getObservationMetaData)
        self.assertRaises(RuntimeError, gen.getObservationMetaData,fieldRA=(1.0, 2.0, 3.0))

    def testQueryOnRanges(self):
        """
        Test that ObservationMetaData objects returned by queries of the form
        min < value < max
        are, in fact, within that range.

        Test when querying on both a single and two columns.
        """
        gen = ObservationMetaDataGenerator()

        #An ordered dict containign the bounds of our queries
        #This was generated with a separate script which printed
        #the median and maximum values of all of the quantities
        #in our test opsim database
        bounds = OrderedDict()
        bounds['obsHistID'] = (5973, 11080)
        bounds['expDate'] = (1220779, 1831593)
        bounds['fieldRA'] = (numpy.degrees(1.370916), numpy.degrees(1.5348635))
        bounds['fieldDec'] = (numpy.degrees(-0.456238), numpy.degrees(0.0597905))
        bounds['moonRA'] = (numpy.degrees(2.914132), numpy.degrees(4.5716525))
        bounds['moonDec'] = (numpy.degrees(0.06305), numpy.degrees(0.2216745))
        bounds['rotSkyPos'] = (numpy.degrees(3.116656), numpy.degrees(4.6974265))
        bounds['rawSeeing'] = (0.728562, 1.040495)
        bounds['sunAlt'] = (numpy.degrees(-0.522905), numpy.degrees(-0.366073))
        bounds['moonAlt'] = (numpy.degrees(0.099096), numpy.degrees(0.5495415))
        bounds['dist2Moon'] = (numpy.degrees(1.570307), numpy.degrees(2.347868))
        bounds['moonPhase'] = (52.2325, 76.0149785)
        bounds['expMJD'] = (49367.129396, 49374.1990025)
        bounds['altitude'] = (numpy.degrees(0.781015), numpy.degrees(1.1433785))
        bounds['azimuth'] = (numpy.degrees(3.470077), numpy.degrees(4.8765995))
        bounds['airmass'] = (1.420459, 2.0048075)
        bounds['skyBrightness'] = (19.017605, 20.512553)
        bounds['m5'] = (22.815249, 24.0047695)

        #test querying on a single column
        for tag in bounds:
            args = {}
            args[tag] = bounds[tag]
            results = gen.getObservationMetaData(**args)

            name = gen.columnMapping[tag][1]
            if name is not None:
                if gen.columnMapping[tag][3] is not None:
                    xmin = gen.columnMapping[tag][3](bounds[tag][0])
                    xmax = gen.columnMapping[tag][3](bounds[tag][1])
                else:
                    xmin = bounds[tag][0]
                    xmax = bounds[tag][1]
                ct = 0
                for obs_metadata in results:
                    ct += 1
                    self.assertTrue(obs_metadata.phoSimMetadata[name][0]<xmax)
                    self.assertTrue(obs_metadata.phoSimMetadata[name][0]>xmin)
                    if tag == 'm5':
                        self.assertTrue(obs_metadata.m5('i')<xmax)
                        self.assertTrue(obs_metadata.m5('i')>xmin)

                #make sure that we did not accidentally choose values such that
                #no ObservationMetaData were ever returned
                self.assertTrue(ct>0)

        #test querying on two columns at once
        ct = 0
        for ii in range(len(bounds)):
            tag1 = bounds.keys()[ii]
            name1 = gen.columnMapping[tag1][1]
            if gen.columnMapping[tag1][3] is not None:
                xmin = gen.columnMapping[tag1][3](bounds[tag1][0])
                xmax = gen.columnMapping[tag1][3](bounds[tag1][1])
            else:
                xmin = bounds[tag1][0]
                xmax = bounds[tag1][1]
            for jj in range(ii+1, len(bounds)):
                tag2 = bounds.keys()[jj]
                name2 = gen.columnMapping[tag2][1]
                if gen.columnMapping[tag2][3] is not None:
                    ymin = gen.columnMapping[tag2][3](bounds[tag2][0])
                    ymax = gen.columnMapping[tag2][3](bounds[tag2][1])
                else:
                    ymin = bounds[tag2][0]
                    ymax = bounds[tag2][1]
                args = {}
                args[tag1] = bounds[tag1]
                args[tag2] = bounds[tag2]
                results = gen.getObservationMetaData(**args)
                if name1 is not None or name2 is not None:
                    for obs_metadata in results:
                        ct += 1
                        if name1 is not None:
                            self.assertTrue(obs_metadata.phoSimMetadata[name1][0]>xmin)
                            self.assertTrue(obs_metadata.phoSimMetadata[name1][0]<xmax)
                        if name2 is not None:
                            self.assertTrue(obs_metadata.phoSimMetadata[name2][0]>ymin)
                            self.assertTrue(obs_metadata.phoSimMetadata[name2][0]<ymax)

        #Make sure that we didn't choose values such that no ObservationMetaData were
        #ever returned
        self.assertTrue(ct>0)

    def testQueryExactValues(self):
        """
        Test that ObservationMetaData returned by a query demanding an exact value do,
        in fact, adhere to that requirement.
        """
        gen = ObservationMetaDataGenerator()

        bounds = OrderedDict()
        bounds['obsHistID'] = 5973
        bounds['expDate'] = 1220779
        bounds['fieldRA'] = numpy.degrees(1.370916)
        bounds['fieldDec'] = numpy.degrees(-0.456238)
        bounds['moonRA'] = numpy.degrees(2.914132)
        bounds['moonDec'] = numpy.degrees(0.06305)
        bounds['rotSkyPos'] = numpy.degrees(3.116656)
        bounds['rawSeeing'] = 0.728562
        bounds['sunAlt'] = numpy.degrees(-0.522905)
        bounds['moonAlt'] = numpy.degrees(0.099096)
        bounds['dist2Moon'] = numpy.degrees(1.570307)
        bounds['moonPhase'] = 52.2325
        bounds['expMJD'] = 49367.129396
        bounds['altitude'] = numpy.degrees(0.781015)
        bounds['azimuth'] = numpy.degrees(3.470077)
        bounds['airmass'] = 1.420459
        bounds['skyBrightness'] = 19.017605
        bounds['m5'] = 22.815249

        for tag in bounds:
            name = gen.columnMapping[tag][1]
            args = {}
            args[tag] = bounds[tag]
            results = gen.getObservationMetaData(**args)

            if gen.columnMapping[tag][3] is not None:
                value = gen.columnMapping[tag][3](bounds[tag])
            else:
                value = bounds[tag]

            if name is not None:
                ct = 0
                for obs_metadata in results:
                    self.assertAlmostEqual(value, obs_metadata.phoSimMetadata[name][0],10)
                    ct += 1

                #Make sure that we did not choose a value which returns zero ObservationMetaData
                self.assertTrue(ct>0)

    def testQueryLimit(self):
        """
        Test that, when we specify a limit on the number of ObservationMetaData we want returned,
        that limit is respected
        """
        gen = ObservationMetaDataGenerator()
        results = gen.getObservationMetaData(fieldRA=(numpy.degrees(1.370916), numpy.degrees(1.5348635)),
                                             limit=20)
        self.assertEqual(len(results),20)

    def testQueryOnFilter(self):
        """
        Test that queries on the filter work.
        """
        gen = ObservationMetaDataGenerator()
        results = gen.getObservationMetaData(fieldRA=numpy.degrees(1.370916), telescopeFilter='i')
        ct = 0
        for obs_metadata in results:
            self.assertAlmostEqual(obs_metadata.phoSimMetadata['Unrefracted_RA'][0],1.370916)
            self.assertEqual(obs_metadata.phoSimMetadata['Opsim_filter'][0],'i')
            ct += 1

        #Make sure that more than zero ObservationMetaData were returned
        self.assertTrue(ct>0)

    def testObsMetaDataBounds(self):
        """
        Make sure that the bound specifications (i.e. a circle or a box on the sky) are correctly
        passed through to the resulting ObservationMetaData
        """

        gen = ObservationMetaDataGenerator()

        #Test a cirlce with a specified radius
        results = gen.getObservationMetaData(fieldRA=numpy.degrees(1.370916), telescopeFilter='i', boundLength=0.9)
        ct = 0
        for obs_metadata in results:
            self.assertTrue(isinstance(obs_metadata.bounds,CircleBounds))
            self.assertAlmostEqual(obs_metadata.bounds.radiusdeg,0.9,10)
            self.assertAlmostEqual(obs_metadata.bounds.RA,obs_metadata.phoSimMetadata['Unrefracted_RA'][0],10)
            self.assertAlmostEqual(obs_metadata.bounds.DEC,obs_metadata.phoSimMetadata['Unrefracted_Dec'][0],10)
            ct += 1

        #Make sure that some ObservationMetaData were tested
        self.assertTrue(ct>0)

        #test a square
        results = gen.getObservationMetaData(fieldRA=numpy.degrees(1.370916), telescopeFilter='i',
                                             boundType='box', boundLength=1.2)
        ct = 0
        for obs_metadata in results:
            RAdeg = numpy.degrees(obs_metadata.phoSimMetadata['Unrefracted_RA'][0])
            DECdeg = numpy.degrees(obs_metadata.phoSimMetadata['Unrefracted_Dec'][0])
            self.assertTrue(isinstance(obs_metadata.bounds,BoxBounds))

            self.assertAlmostEqual(obs_metadata.bounds.RAminDeg,RAdeg-1.2,10)
            self.assertAlmostEqual(obs_metadata.bounds.RAmaxDeg,RAdeg+1.2,10)
            self.assertAlmostEqual(obs_metadata.bounds.DECminDeg,DECdeg-1.2,10)
            self.assertAlmostEqual(obs_metadata.bounds.DECmaxDeg,DECdeg+1.2,10)

            self.assertAlmostEqual(obs_metadata.bounds.RA,obs_metadata.phoSimMetadata['Unrefracted_RA'][0],10)
            self.assertAlmostEqual(obs_metadata.bounds.DEC,obs_metadata.phoSimMetadata['Unrefracted_Dec'][0],10)

            ct += 1

        #Make sure that some ObservationMetaData were tested
        self.assertTrue(ct>0)

        #test a rectangle
        results = gen.getObservationMetaData(fieldRA=numpy.degrees(1.370916), telescopeFilter='i',
                                             boundType='box', boundLength=(1.2,0.6))
        ct = 0
        for obs_metadata in results:
            RAdeg = numpy.degrees(obs_metadata.phoSimMetadata['Unrefracted_RA'][0])
            DECdeg = numpy.degrees(obs_metadata.phoSimMetadata['Unrefracted_Dec'][0])
            self.assertTrue(isinstance(obs_metadata.bounds,BoxBounds))

            self.assertAlmostEqual(obs_metadata.bounds.RAminDeg,RAdeg-1.2,10)
            self.assertAlmostEqual(obs_metadata.bounds.RAmaxDeg,RAdeg+1.2,10)
            self.assertAlmostEqual(obs_metadata.bounds.DECminDeg,DECdeg-0.6,10)
            self.assertAlmostEqual(obs_metadata.bounds.DECmaxDeg,DECdeg+0.6,10)

            self.assertAlmostEqual(obs_metadata.bounds.RA,obs_metadata.phoSimMetadata['Unrefracted_RA'][0],10)
            self.assertAlmostEqual(obs_metadata.bounds.DEC,obs_metadata.phoSimMetadata['Unrefracted_Dec'][0],10)

            ct += 1

        #Make sure that some ObservationMetaData were tested
        self.assertTrue(ct>0)

    def testCreationOfPhoSimCatalog(self):
        """
        Make sure that we can create PhoSim input catalogs using the returned ObservationMetaData.
        This test will just make sure that the process runs.  It will not validate the output
        in any way.
        """

        dbName = 'obsMetaDataGeneratorTest.db'
        catName = 'testPhoSimFromObsMetaDataGenerator.txt'
        if os.path.exists(dbName):
            os.unlink(dbName)
        junk_obs_metadata = makePhoSimTestDB(filename=dbName)
        bulgeDB = testGalaxyBulge(address='sqlite:///'+dbName)

        gen = ObservationMetaDataGenerator()
        results = gen.getObservationMetaData(fieldRA=numpy.degrees(1.370916),telescopeFilter='i')
        testCat = PhoSimCatalogSersic2D(bulgeDB, obs_metadata=results[0])
        testCat.write_catalog(catName)

        if os.path.exists(catName):
            os.unlink(catName)

        if os.path.exists(dbName):
            os.unlink(dbName)



def suite():
    utilsTests.init()
    suites = []
    suites += unittest.makeSuite(ObservationMetaDataGeneratorTest)

    return unittest.TestSuite(suites)

def run(shouldExit = False):
    utilsTests.run(suite(), shouldExit)
if __name__ == "__main__":
    run(True)
