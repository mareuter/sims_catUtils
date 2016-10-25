import numpy as np
from lsst.sims.catalogs.db import DBObject
from lsst.sims.utils import ObservationMetaData

__all__ = ["ObservationMetaDataGenerator"]


class ObservationMetaDataGenerator(object):
    """
    A class that allows the user to generate instantiations of
    `lsst.sims.utils.ObservationMetaData` corresponding to OpSim pointings.
    The functionality includes:
    - getOpSimRecords : obtain OpSim records matching the intersection of user
        specified ranges on each column in the OpSim output database. The
        records are in the form of a `numpy.recarray`
    - ObservationMetaDataFromPointing : convert an OpSim record for a single
        OpSim Pointing to an instance of ObservationMetaData usable by catsim
        and PhoSim Instance Catalogs.
    - getObservationMetaData : Obtain a list of ObservationMetaData instances
        corresponding to OpSim pointings matching the intersection of user
        specified ranges on each column in the OpSim output database.

    The major method is ObservationMetaDataGenerator.getObservationMetaData()
    which accepts bounds on columns of the opsim summary table and returns
    a list of ObservationMetaData instantiations that fall within those
    bounds.
    """

    def _set_seeing_column(self, input_summary_columns):
        """
        input_summary_columns is a list of columns in the OpSim database schema

        This method sets the member variable self._seeing_column to a string
        denoting the name of the seeing column in the OpSimDatabase.  It also
        sets self._user_interface_to_opsim['seeing'] to the correct value.
        """

        if 'FWHMeff' in input_summary_columns:
            self._seeing_column = 'FWHMeff'
        else:
            self._seeing_column = 'finSeeing'

        self._user_interface_to_opsim['seeing'] = (self._seeing_column, None, float)

    def __init__(self, database=None, driver='sqlite', host=None, port=None):
        """
        Constructor for the class

        Parameters
        ----------
        database : string
            absolute path to the output of the OpSim database
        driver : string, optional, defaults to 'sqlite'
            driver/dialect for the SQL database
        host : hostName, optional, defaults to None,
            hostName, None is good for a local database
        port : hostName, optional, defaults to None,
            port, None is good for a local database

        Returns
        ------
        Instance of the ObserverMetaDataGenerator class

        ..notes : For testing purposes a small OpSim database is available at
        `os.path.join(getPackageDir('sims_data'), 'OpSimData/opsimblitz1_1133_sqlite.db')`
        """
        self.driver = driver
        self.host = host
        self.port = port
        self.database = database
        self._seeing_column = 'FWHMeff'

        # a dict keyed on the user interface names of the OpSimdata columns
        # (i.e. the args to getObservationMetaData).  Returns a tuple that is the
        # (name of data column in OpSim, transformation to go from user interface to OpSim units,
        # dtype in OpSim)
        #
        # Note: this dict will contain entries for every column (except propID) in the OpSim
        # summary table, not just those the ObservationMetaDataGenerator is designed to query
        # on.  The idea is that ObservationMetaData generated by this class will carry around
        # records of the values of all of the associated OpSim Summary columns so that users
        # can pass those values on to PhoSim/other tools and thier own discretion.
        self._user_interface_to_opsim = {'obsHistID': ('obsHistID', None, np.int64),
                                         'expDate': ('expDate', None, int),
                                         'fieldRA': ('fieldRA', np.radians, float),
                                         'fieldDec': ('fieldDec', np.radians, float),
                                         'moonRA': ('moonRA', np.radians, float),
                                         'moonDec': ('moonDec', np.radians, float),
                                         'rotSkyPos': ('rotSkyPos', np.radians, float),
                                         'telescopeFilter':
                                             ('filter', lambda x: '\'{}\''.format(x), (str, 1)),
                                         'rawSeeing': ('rawSeeing', None, float),
                                         'sunAlt': ('sunAlt', np.radians, float),
                                         'moonAlt': ('moonAlt', np.radians, float),
                                         'dist2Moon': ('dist2Moon', np.radians, float),
                                         'moonPhase': ('moonPhase', None, float),
                                         'expMJD': ('expMJD', None, float),
                                         'altitude': ('altitude', np.radians, float),
                                         'azimuth': ('azimuth', np.radians, float),
                                         'visitExpTime': ('visitExpTime', None, float),
                                         'airmass': ('airmass', None, float),
                                         'm5': ('fiveSigmaDepth', None, float),
                                         'skyBrightness': ('filtSkyBrightness', None, float),
                                         'sessionID': ('sessionID', None, int),
                                         'fieldID': ('fieldID', None, int),
                                         'night': ('night', None, int),
                                         'visitTime': ('visitTime', None, float),
                                         'finRank': ('finRank', None, float),
                                         'FWHMgeom': ('FWHMgeom', None, float),
                                         # do not include FWHMeff; that is detected by
                                         # self._set_seeing_column()
                                         'transparency': ('transparency', None, float),
                                         'vSkyBright': ('vSkyBright', None, float),
                                         'rotTelPos': ('rotTelPos', None, float),
                                         'lst': ('lst', None, float),
                                         'solarElong': ('solarElong', None, float),
                                         'moonAz': ('moonAz', None, float),
                                         'sunAz': ('sunAz', None, float),
                                         'phaseAngle': ('phaseAngle', None, float),
                                         'rScatter': ('rScatter', None, float),
                                         'mieScatter': ('mieScatter', None, float),
                                         'moonBright': ('moonBright', None, float),
                                         'darkBright': ('darkBright', None, float),
                                         'wind': ('wind', None, float),
                                         'humidity': ('humidity', None, float),
                                         'slewDist': ('slewDist', None, float),
                                         'slewTime': ('slewTime', None, float),
                                         'ditheredRA': ('ditheredRA', None, float),
                                         'ditheredDec': ('ditheredDec', None, float)}

        if self.database is None:
            return

        self.opsimdb = DBObject(driver=self.driver, database=self.database,
                                host=self.host, port=self.port)

        # 27 January 2016
        # Detect whether the OpSim db you are connecting to uses 'finSeeing'
        # as its seeing column (deprecated), or FWHMeff, which is the modern
        # standard
        self._summary_columns = self.opsimdb.get_column_names('Summary')
        self._set_seeing_column(self._summary_columns)

        # Set up self.dtype containg the dtype of the recarray we expect back from the SQL query.
        # Also setup baseQuery which is just the SELECT clause of the SQL query
        #
        # self.active_columns will be a list containing the subset of OpSim database columns
        # (specified in self._user_interface_to_opsim) that actually exist in this opsim database
        dtypeList = []
        self.baseQuery = 'SELECT'
        self.active_columns = []
        for column in self._user_interface_to_opsim:
            rec = self._user_interface_to_opsim[column]
            if rec[0] in self._summary_columns:
                self.active_columns.append(column)
                dtypeList.append((rec[0], rec[2]))
                if self.baseQuery != 'SELECT':
                    self.baseQuery += ','
                self.baseQuery += ' ' + rec[0]

        self.dtype = np.dtype(dtypeList)

    def getOpsimRecordsFromQuery(self, query):
        """
        Perform an arbitrary SQL query on the Opsim database Summary table.
        Return the results as a numpy recarray.

        Parameters
        ----------
        A string containing the SQL query to be executed

        Returns
        -------
        `numpy.recarray` with OpSim records. The column names may be obtained as
        res.dtype.names
        """
        return self.opsimdb.execute_arbitrary(query, dtype=self.dtype)

    def getOpSimRecords(self, obsHistID=None, expDate=None, night=None, fieldRA=None,
                        fieldDec=None, moonRA=None, moonDec=None,
                        rotSkyPos=None, telescopeFilter=None, rawSeeing=None,
                        seeing=None, sunAlt=None, moonAlt=None, dist2Moon=None,
                        moonPhase=None, expMJD=None, altitude=None,
                        azimuth=None, visitExpTime=None, airmass=None,
                        skyBrightness=None, m5=None, boundType='circle',
                        boundLength=1.75, limit=None):
        """
        This method will query the summary table in the `self.opsimdb` database
        according to constraints specified in the input ranges and return a
        `numpy.recarray` containing the records that match those constraints. If limit
        is used, the first N records will be returned in the list.

        Parameters
        ----------
        obsHistID, expDate, night, fieldRA, fieldDec, moonRa, moonDec, rotSkyPos,
        telescopeFilter, rawSeeing, seeing, sunAlt, moonAlt, dist2Moon,
        moonPhase, expMJD, altitude, azimuth, visitExpTime, airmass,
        skyBrightness, m5 : tuples of length 2, optional, defaults to None
            each of these variables represent a single column (perhaps through
            an alias) in the OpSim database, and potentially in a different unit.
            if not None, the variable self.columnMapping is used to constrain
            the corresponding column in the OpSim database to the ranges specified
            in the tuples, after a unit transformation if necessary.

            The ranges must be specified in the tuple in degrees for all angles in this
            (moonRa, moonDec, rotSkyPos, sunAlt, moonAlt, dist2Moon, altitude,
            azimuth). The times in  (expMJD, are in units of MJD). visitExpTime has
            units of seconds since the start of the survey. moonPhase is a number
            from 0., to 100.
        boundType : `sims.utils.ObservationMetaData.boundType`, optional, defaults to 'circle'
            {'circle', 'box'} denoting the shape of the pointing. Further
            documentation `sims.catalogs.generation.db.spatialBounds.py``
        boundLength : float, optional, defaults to 0.1
            sets `sims.utils.ObservationMetaData.boundLenght`
        limit : integer, optional, defaults to None
            if not None, denotes max number of records returned by the query

        Returns
        -------
        `numpy.recarray` with OpSim records. The column names may be obtained as
        res.dtype.names

        .. notes:: The `limit` argument should only be used if a small example
        is required. The angle ranges in the argument should be specified in degrees.
        """

        self._set_seeing_column(self._summary_columns)

        query = self.baseQuery + ' FROM SUMMARY'

        nConstraints = 0  # the number of constraints in this query

        for column in self._user_interface_to_opsim:
            transform = self._user_interface_to_opsim[column]

            # this try/except block is because there will be columns in the OpSim Summary
            # table (and thus in self._user_interface_to_opsim) which the
            # ObservationMetaDataGenerator is not designed to query on
            try:
                value = eval(column)
            except:
                value = None

            if value is not None:
                if column not in self.active_columns:
                    raise RuntimeError("You have asked ObservationMetaDataGenerator to SELECT pointings on"
                                       "%s; that column does not exist in your OpSim database" % column)
                if nConstraints > 0:
                    query += ' AND'
                else:
                    query += ' WHERE '

                if isinstance(value, tuple):
                    if len(value) > 2:
                        raise RuntimeError('Cannot pass a tuple longer than 2 elements ' +
                                           'to getObservationMetaData: %s is len %d'
                                           % (column, len(value)))

                    # perform any necessary coordinate transformations
                    if transform[1] is not None:
                        vmin = transform[1](value[0])
                        vmax = transform[1](value[1])
                    else:
                        vmin = value[0]
                        vmax = value[1]

                    query += ' %s >= %s AND %s <= %s' % \
                             (transform[0], vmin, transform[0], vmax)
                else:
                    # perform any necessary coordinate transformations
                    if transform[1] is not None:
                        vv = transform[1](value)
                    else:
                        vv = value
                    query += ' %s == %s' % (transform[0], vv)

                nConstraints += 1

        query += ' GROUP BY expMJD'

        if limit is not None:
            query += ' LIMIT %d' % limit

        if nConstraints == 0 and limit is None:
            raise RuntimeError('You did not specify any contraints on your query;' +
                               ' you will just return ObservationMetaData for all poitnings')

        return self.getOpsimRecordsFromQuery(query)

    def ObservationMetaDataFromPointing(self, OpSimPointingRecord, OpSimColumns=None,
                                        boundLength=1.75, boundType='circle'):
        """
        Return instance of ObservationMetaData for an OpSim Pointing record
        from OpSim.

        Parameters
        ----------
        OpSimPointingRecord : Dictionary, mandatory
            Dictionary of values with keys corresponding to certain columns of
            the Summary table in the OpSim database. The minimal list of keys
            required for catsim to work is 'fiveSigmaDepth',
            'filtSkyBrightness', and at least one of ('finSeeing', 'FWHMeff').
            More keys defined in columnMap may be necessary for PhoSim to work.
        OpSimColumns : tuple of strings, optional, defaults to None
            The columns corresponding to the OpSim records. If None, attempts
            to obtain these from the OpSimRecord as OpSimRecord.dtype.names
        boundType : {'circle', 'box'}, optional, defaults to 'circle'
            Shape of the observation
        boundLength : scalar float, optional, defaults to 1.75
            'characteristic size' of observation field, in units of degrees.
            For boundType='circle', this is a radius, for boundType='box', this
            is a size of the box
        """

        pointing = OpSimPointingRecord
        pointing_column_names = pointing.dtype.names
        # Decide what is the name of the column in the OpSim database
        # corresponding to the Seeing. For older OpSim outputs, this is
        # 'finSeeing'. For later OpSim outputs this is 'FWHMeff'
        if OpSimColumns is None:
            OpSimColumns = pointing_column_names

        self._set_seeing_column(OpSimColumns)

        # check to make sure the OpSim pointings being supplied contain
        # the minimum required information
        for required_column in ('fieldRA', 'fieldDec', 'expMJD', 'filter'):
            if required_column not in OpSimColumns:
                raise RuntimeError("ObservationMetaDataGenerator requires that the database of "
                                   "pointings include the coluns:\nfieldRA (in radians)"
                                   "\nfieldDec (in radians)\nexpMJD\nfilter")

        # construct a raw dict of all of the OpSim columns associated with this pointing
        raw_dict = dict([(col, pointing[col]) for col in pointing_column_names])

        obs = ObservationMetaData(pointingRA=np.degrees(pointing['fieldRA']),
                                  pointingDec=np.degrees(pointing['fieldDec']),
                                  mjd=pointing['expMJD'],
                                  bandpassName=pointing['filter'],
                                  boundType=boundType,
                                  boundLength=boundLength)

        if 'fiveSigmaDepth' in pointing_column_names:
            obs.m5 = pointing['fiveSigmaDepth']
        if 'filtSkyBrightness' in pointing_column_names:
            obs.skyBrightness = pointing['filtSkyBrightness']
        if self._seeing_column in pointing_column_names:
            obs.seeing = pointing[self._seeing_column]
        if 'rotSkyPos' in pointing_column_names:
            obs.rotSkyPos = np.degrees(pointing['rotSkyPos'])

        obs.OpsimMetaData = raw_dict

        return obs

    def ObservationMetaDataFromPointingArray(self, OpSimPointingRecords,
                                             OpSimColumns=None,
                                             boundLength=1.75,
                                             boundType='circle'):
        """
        Static method to get a list of instances of ObservationMetaData
        corresponding to the records in `numpy.recarray`, where it uses
        the dtypes of the recArray for ObservationMetaData attributes that
        require the dtype.

        Parameters
        ----------
        OpSimPointingRecords : `numpy.recarray` of OpSim Records
        OpSimColumns : a tuple of strings, optional, defaults to None
            tuple of column Names of the data in the `numpy.recarray`. If
            None, these names are extracted from the recarray.
        boundType : {'circle' or 'box'}
            denotes the shape of the pointing
        boundLength : float, optional, defaults to 1.75
            the bound length of the Pointing in units of degrees. For boundType
            'box', this is the length of the side of the square box. For boundType
            'circle' this is the radius.
        """

        if OpSimColumns is None:
            OpSimColumns = OpSimPointingRecords.dtype.names

        out = list(self.ObservationMetaDataFromPointing(OpSimPointingRecord,
                                                        OpSimColumns=OpSimColumns,
                                                        boundLength=boundLength,
                                                        boundType=boundType)
                   for OpSimPointingRecord in OpSimPointingRecords)

        return out

    def getObservationMetaData(self, obsHistID=None, expDate=None, night=None, fieldRA=None, fieldDec=None,
                               moonRA=None, moonDec=None, rotSkyPos=None, telescopeFilter=None,
                               rawSeeing=None, seeing=None, sunAlt=None, moonAlt=None, dist2Moon=None,
                               moonPhase=None, expMJD=None, altitude=None, azimuth=None,
                               visitExpTime=None, airmass=None, skyBrightness=None,
                               m5=None, boundType='circle', boundLength=1.75, limit=None):

        """
        This method will query the OpSim database summary table according to user-specified
        constraints and return a list of of ObservationMetaData instantiations consistent
        with those constraints.

        @param [in] limit is an integer denoting the maximum number of ObservationMetaData to
        be returned

        @param [in] boundType is the boundType of the ObservationMetaData to be returned

        @param [in] boundLength is the boundLength of the ObservationMetaData to be
        returned

        See the docstring for ObservationMetaData for a clearer explanation of
        boundType and boundLength.

        All other input parameters are constraints to be placed on the SQL query of the
        opsim output db.  These contraints can either be tuples of the form (min, max)
        or an exact value the user wants returned.

        Parameters that can be constrained are:

        @param [in] fieldRA in degrees
        @param [in] fieldDec in degrees
        @param [in] altitude in degrees
        @param [in] azimuth in degrees

        @param [in] moonRA in degrees
        @param [in] moonDec in degrees
        @param [in] moonAlt in degrees
        @param [in] moonPhase (a value from 1 to 100 indicating how much of the moon is illuminated)
        @param [in] dist2Moon the distance between the telescope pointing and the moon in degrees

        @param [in] sunAlt in degrees

        @param [in[ rotSkyPos (the angle of the sky with respect to the camera coordinate system) in degrees
        @param [in] telescopeFilter a string that is one of u,g,r,i,z,y

        @param [in] airmass
        @param [in] rawSeeing (this is an idealized seeing at zenith at 500nm in arcseconds)
        @param [in] seeing (this is the OpSim column 'FWHMeff' or 'finSeeing' [deprecated] in arcseconds)

        @param [in] visitExpTime the exposure time in seconds
        @param [in] obsHistID the integer used by OpSim to label pointings
        @param [in] expDate is the date of the exposure (units????)
        @param [in] expMJD is the MJD of the exposure
        @param [in] night is the night (an int starting at zero) on which the observation took place
        @param [in] m5 is the five sigma depth of the observation
        @param [in] skyBrightness
        """

        OpSimPointingRecords = self.getOpSimRecords(obsHistID=obsHistID,
                                                    expDate=expDate,
                                                    night=night,
                                                    fieldRA=fieldRA,
                                                    fieldDec=fieldDec,
                                                    moonRA=moonRA,
                                                    moonDec=moonDec,
                                                    rotSkyPos=rotSkyPos,
                                                    telescopeFilter=telescopeFilter,
                                                    rawSeeing=rawSeeing,
                                                    seeing=seeing,
                                                    sunAlt=sunAlt,
                                                    moonAlt=moonAlt,
                                                    dist2Moon=dist2Moon,
                                                    moonPhase=moonPhase,
                                                    expMJD=expMJD,
                                                    altitude=altitude,
                                                    azimuth=azimuth,
                                                    visitExpTime=visitExpTime,
                                                    airmass=airmass,
                                                    skyBrightness=skyBrightness,
                                                    m5=m5, boundType=boundType,
                                                    boundLength=boundLength,
                                                    limit=limit)

        output = self.ObservationMetaDataFromPointingArray(OpSimPointingRecords,
                                                           OpSimColumns=None,
                                                           boundType=boundType,
                                                           boundLength=boundLength)
        return output
