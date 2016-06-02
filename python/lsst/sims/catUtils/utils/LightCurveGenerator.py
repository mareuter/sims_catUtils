from __future__ import print_function
import numpy as np

from lsst.sims.catUtils.utils import ObservationMetaDataGenerator
from  lsst.sims.catUtils.mixins import PhotometryStars, VariabilityStars
from lsst.sims.catalogs.measures.instance import InstanceCatalog, compound
from lsst.sims.utils import haversine

import time

class _stellarLightCurveCatalog(InstanceCatalog, VariabilityStars, PhotometryStars):

    column_outputs = ["uniqueId", "raJ2000", "decJ2000",
                      "lightCurveMag", "sigma_lightCurveMag"]

    _sedList_cache = None
    _sedList_to_use = None

    def _loadSedList(self, wavelen_match):
        if self._sedList_to_use is None:
            PhotometryStars._loadSedList(self, wavelen_match)
        else:
            self._sedList = self._sedList_to_use


    def iter_catalog(self, chunk_size=None, query_cache=None, sed_cache=None):
        """
        chunk_size (optional) is an int specifying the number of rows to return
        from the database at a time

        query_result (optional) is the result of calling db_obj.query_columns().
        DO NOT use this unless you know what you are doing.  It is an optional
        input for those who want to repeatedly examine the same patch of sky
        without actually querying the database over and over again.  If it is set
        to 'None' (default), this method will handle the database query.

        Returns an iterator over rows of the catalog.
        """

        if query_cache is None:
            yield InstanceCatalog.iter_catalog(self)

        if sed_cache is None:
            sed_cache = [None]*len(query_cache)

        for chunk, sed_list in zip(query_cache, sed_cache):
            self._set_current_chunk(chunk)
            self._sedList_to_use = sed_list
            chunk_cols = [self.transformations[col](self.column_by_name(col))
                          if col in self.transformations.keys() else
                          self.column_by_name(col)
                          for col in self.iter_column_names()]
            for line in zip(*chunk_cols):
                yield line


    @compound("lightCurveMag", "sigma_lightCurveMag")
    def get_lightCurvePhotometry(self):
        if len(self.obs_metadata.bandpass) != 1:
            raise RuntimeError("_stellarLightCurveCatalog cannot handle bandpass "
                               "%s" % str(self.obs_metadata.bandpass))

        mag = self.column_by_name("lsst_%s" % self.obs_metadata.bandpass)
        sigma = self.column_by_name("sigma_lsst_%s" % self.obs_metadata.bandpass)

        if self._sedList_cache is None and len(mag)>0:
            self._sedList_cache = []

        if self._sedList_to_use is None and len(mag)>0:
            self._sedList_cache.append(self._sedList)

        return np.array([mag, sigma])


class LightCurveGenerator(object):

    def __init__(self, catalogdb, opsimdb, opsimdriver="sqlite"):
        self._generator = ObservationMetaDataGenerator(database=opsimdb,
                                                       driver=opsimdriver)

        self._catalogdb = catalogdb


    def generate_light_curves(self, ra, dec, bandpass):
        obs_list = self._generator.getObservationMetaData(
                                     fieldRA=ra,
                                     fieldDec=dec,
                                     telescopeFilter=bandpass,
                                     boundLength=1.75)

        output_dict = {}

        if len(obs_list) == 0:
            print("No observations found matching your criterion")
            return None

        t_start = time.clock()
        print('starting light curve generation')

        tol = 1.0e-12
        obs_groups = []
        for iobs, obs in enumerate(obs_list):
            group_dex = -1

            for ix, obs_g in enumerate(obs_groups):
                dd = haversine(obs._pointingRA, obs._pointingDec,
                               obs_list[obs_g[0]]._pointingRA, obs_list[obs_g[0]]._pointingDec)
                if dd<tol:
                    group_dex = ix
                    break

            if group_dex == -1:
                obs_groups.append([iobs])
            else:
                obs_groups[group_dex].append(iobs)

        cat = None

        for grp in obs_groups:
            dataCache = None
            sedCache = None
            for ix in grp:
                obs = obs_list[ix]
                if cat is None:
                    cat = _stellarLightCurveCatalog(self._catalogdb, obs_metadata=obs)
                    db_required_columns = cat.db_required_columns()

                if dataCache is None:
                    query_result = cat.db_obj.query_columns(colnames=cat._active_columns,
                                                            obs_metadata=obs,
                                                            constraint=cat.constraint,
                                                            chunk_size=10)
                    dataCache = []
                    for chunk in query_result:
                       dataCache.append(chunk)

                cat.obs_metadata = obs
                cat._gamma_cache = {}

                for star_obj in cat.iter_catalog(query_cache=dataCache, sed_cache=sedCache):
                    if star_obj[0] not in output_dict:
                        output_dict[star_obj[0]] = []

                    output_dict[star_obj[0]].append((obs.mjd.TAI,
                                                     star_obj[3],
                                                     star_obj[4]))


                if cat._sedList_cache is not None:
                    sedCache = cat._sedList_cache

            cat._sedList_cache = None
            cat._sedList_to_use = None

        print('that took %e; grps %d' % (time.clock()-t_start, len(obs_groups)))
        print('len obs_list %d' % len(obs_list))
        return output_dict
