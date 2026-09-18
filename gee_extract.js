// gee_extract.js — Code Editor fallback for gee_extract.py (BSS2026 provenance PoC).
// Same math/stages as gee_extract.py, computed here instead of via earthengine-api
// because notebook/gcloud OAuth for this Google account kept hitting
// "incompatible OAuth2 Client configuration" / blocked-scope errors.
//
// RUN:
//   1. Paste into https://code.earthengine.google.com/, click Run.
//   2. Open the Tasks tab, click RUN on each of the 3 export tasks that
//      appear (ee_samples, ee_stage_scalars, ee_scene_ids).
//   3. Download the 3 resulting CSVs from Google Drive into this project
//      folder (same names: ee_samples.csv, ee_stage_scalars.csv,
//      ee_scene_ids.csv).
//   4. python3 load_real_episode_from_csv.py
//   5. python3 load_real_episode.py --in real_episode_data.json

var PARAMS = {alpha: 0.5, beta: 0.3, lambda: 0.2, tau: 0.4, scale_val: 100};
var AOI = ee.Geometry.Point([76.9455, 43.1575]).buffer(10000).bounds();

var P1_START = '2023-06-01', P1_END = '2023-08-31';
var P2_START = '2024-06-01', P2_END = '2024-08-31';
var FULL_START = '2023-01-01', FULL_END = '2024-12-31';

var N_SAMPLES = 200;
var SAMPLE_SEED = 42;
var SCALE = PARAMS.scale_val;

function maskS2clouds(image) {
  var qa = image.select('QA60');
  var mask = qa.bitwiseAnd(1 << 10).eq(0).and(qa.bitwiseAnd(1 << 11).eq(0));
  return image.updateMask(mask).divide(10000).copyProperties(image, ['system:time_start']);
}

function getS2Ndvi(aoi, start, end) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(aoi)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
    .map(maskS2clouds)
    .map(function(img) {
      return img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        .copyProperties(img, ['system:time_start', 'system:index']);
    });
}

function getS1Sar(aoi, start, end) {
  function addRatio(img) {
    var ratio = img.select('VV').divide(img.select('VH')).rename('VVVH');
    return img.addBands(ratio).select('VVVH').copyProperties(img, ['system:time_start', 'system:index']);
  }
  return ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(aoi)
    .filterDate(start, end)
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .map(addRatio);
}

function getData(aoi, start, end) {
  var ndvi = getS2Ndvi(aoi, start, end);
  var sar = getS1Sar(aoi, start, end);
  var joined = ee.Join.inner().apply(ndvi, sar, ee.Filter.maxDifference({
    difference: 15 * 24 * 60 * 60 * 1000,
    leftField: 'system:time_start',
    rightField: 'system:time_start'
  }));
  return ee.ImageCollection(joined.map(function(f) {
    return ee.Image(f.get('primary')).addBands(ee.Image(f.get('secondary')));
  }));
}

function idsToFeatures(collectionLabel, imgColl) {
  var ids = imgColl.aggregate_array('system:index');
  return ee.FeatureCollection(ids.map(function(id) {
    return ee.Feature(null, {collection: collectionLabel, scene_index: id});
  }));
}

// ---- accumulate rows for the 3 output tables ----
var sampleRows = [];
var scalarRows = [];

function addSamples(stageLabel, image, band) {
  var samples = image.sample({region: AOI, scale: SCALE, numPixels: N_SAMPLES, seed: SAMPLE_SEED, geometries: true})
    .map(function(f) {
      var coords = f.geometry().coordinates();
      return ee.Feature(null, {
        stage: stageLabel,
        lon: coords.get(0),
        lat: coords.get(1),
        val: f.get(band)
      });
    });
  sampleRows.push(samples);
}

function addScalar(stageLabel, image, band, changedPixels) {
  var meanVal = image.reduceRegion({reducer: ee.Reducer.mean(), geometry: AOI, scale: SCALE, maxPixels: 1e9, bestEffort: true}).get(band);
  scalarRows.push(ee.Feature(null, {stage: stageLabel, mean: meanVal, changed_pixels_est: changedPixels}));
}

// ---- data acquisition ----
print('Building data-acquisition leaves...');
var s2P1P2 = getS2Ndvi(AOI, P1_START, P2_END);
var s1P1P2 = getS1Sar(AOI, P1_START, P2_END);
var allSceneIds = idsToFeatures('data_acquisition_s2', s2P1P2)
  .merge(idsToFeatures('data_acquisition_s1', s1P1P2));

// ---- correlations ----
print('Computing period-1 / period-2 correlation...');
var series1 = getData(AOI, P1_START, P1_END);
var series2 = getData(AOI, P2_START, P2_END);
var corr1 = series1.reduce(ee.Reducer.pearsonsCorrelation()).select('correlation');
var corr2 = series2.reduce(ee.Reducer.pearsonsCorrelation()).select('correlation');

addSamples('pearson_corr_period1', corr1, 'correlation');
addScalar('pearson_corr_period1', corr1, 'correlation', null);
addSamples('pearson_corr_period2', corr2, 'correlation');
addScalar('pearson_corr_period2', corr2, 'correlation', null);

var deltaCorr = corr2.subtract(corr1).rename('delta_corr');
addSamples('delta_corr', deltaCorr, 'delta_corr');
addScalar('delta_corr', deltaCorr, 'delta_corr', null);

print('Computing full-period r_t (2 years of data, may be slow)...');
var rT = getData(AOI, FULL_START, FULL_END).reduce(ee.Reducer.pearsonsCorrelation())
  .select('correlation').rename('r_t');
addSamples('r_t', rT, 'r_t');
addScalar('r_t', rT, 'r_t', null);

print("Computing Moran's I and risk index...");
var weights = [[1, 1, 1], [1, 0, 1], [1, 1, 1]];
var meanDelta = deltaCorr.reduceRegion({reducer: ee.Reducer.mean(), geometry: AOI, scale: SCALE}).get('delta_corr');
var moran = deltaCorr.subtract(ee.Number(meanDelta))
  .convolve(ee.Kernel.fixed(3, 3, weights)).rename('moran_index');
addSamples('moran_index', moran, 'moran_index');
addScalar('moran_index', moran, 'moran_index', null);

var riskIndex = deltaCorr.abs().multiply(PARAMS.alpha)
  .add(moran.abs().multiply(PARAMS.beta))
  .add(rT.abs().multiply(PARAMS.lambda))
  .rename('risk_index');
addSamples('risk_index', riskIndex, 'risk_index');
addScalar('risk_index', riskIndex, 'risk_index', null);

var changeMask = riskIndex.gt(PARAMS.tau).rename('change_mask');
var changedCount = changeMask.reduceRegion({reducer: ee.Reducer.sum(), geometry: AOI, scale: SCALE, maxPixels: 1e9, bestEffort: true}).get('change_mask');
addSamples('change_mask', changeMask, 'change_mask');
addScalar('change_mask', changeMask, 'change_mask', changedCount);

// ---- merge & export ----
var allSamples = sampleRows[0];
for (var i = 1; i < sampleRows.length; i++) {
  allSamples = allSamples.merge(sampleRows[i]);
}
var allScalars = ee.FeatureCollection(scalarRows);

Export.table.toDrive({collection: allSamples, description: 'ee_samples', fileFormat: 'CSV', selectors: ['stage', 'lon', 'lat', 'val']});
Export.table.toDrive({collection: allScalars, description: 'ee_stage_scalars', fileFormat: 'CSV', selectors: ['stage', 'mean', 'changed_pixels_est']});
Export.table.toDrive({collection: allSceneIds, description: 'ee_scene_ids', fileFormat: 'CSV', selectors: ['collection', 'scene_index']});

print('3 export tasks queued — open the Tasks tab and click RUN on each.');
