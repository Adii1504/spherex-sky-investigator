import test from 'node:test';
import assert from 'node:assert/strict';
import { getCatalogueTarget, hasCatalogueCoordinates, searchWithTarget, targetCatalogue, targetIdFromSearch } from './data/targetCatalogue.js';

test('five stable targets keep source-backed coordinates, epochs and provenance', () => {
  assert.deepEqual(targetCatalogue.map(target => target.id), ['barnards-star', 'epsilon-indi-b', 'wise-0855', 'rw-aurigae', 'r-draconis']);
  assert.equal(new Set(targetCatalogue.map(target => target.id)).size, 5);
  for (const target of targetCatalogue) {
    assert.ok(hasCatalogueCoordinates(target));
    assert.equal(target.coordinate_frame, 'ICRS');
    assert.equal(target.reference_epoch, 'J2000');
    assert.equal(target.observation_association_verified, false);
    assert.equal(target.provisional, true);
    assert.equal(target.fov_arcmin, null); // A UI field size is not a source-backed target property.
    assert.match(target.coordinate_reference, /^(19|20)\d\d/);
    assert.ok(target.coordinate_sexagesimal);
    assert.ok(target.astrometry_note);
    assert.ok(target.references.every(reference => new URL(reference.url).hostname === 'simbad.cds.unistra.fr'));
  }
});

test('sexagesimal catalogue positions convert RA hours to degrees without epoch propagation', () => {
  const expected = {
    'barnards-star': [269.45207695861876, 4.693364966576667],
    'epsilon-indi-b': [331.04414658852124, -56.78284419511611],
    'wise-0855': [133.81890825, -7.247048],
    'rw-aurigae': [76.95652603458333, 30.401438173888888],
    'r-draconis': [248.16761083295, 66.75497941722],
  };
  for (const target of targetCatalogue) {
    assert.equal(target.ra_deg, expected[target.id][0]);
    assert.equal(target.dec_deg, expected[target.id][1]);
  }
  assert.match(getCatalogueTarget('wise-0855').astrometry_note, /not coordinates inferred from the WISE identifier/);
  assert.match(getCatalogueTarget('epsilon-indi-b').astrometry_note, /not asserted to be a barycentre/);
});

test('missing, nonfinite, wrong-frame or invalid positions cannot become markers', () => {
  for (const target of [null, {}, {ra_deg: 0, dec_deg: 0}, {coordinate_frame: 'FK4', ra_deg: 0, dec_deg: 0},
    {coordinate_frame: 'ICRS', ra_deg: null, dec_deg: 1}, {coordinate_frame: 'ICRS', ra_deg: 360, dec_deg: 1},
    {coordinate_frame: 'ICRS', ra_deg: 1, dec_deg: NaN}, {coordinate_frame: 'ICRS', ra_deg: 1, dec_deg: 91}]) {
    assert.equal(hasCatalogueCoordinates(target), false);
  }
});

test('URL target parsing is stable and rejects unknown IDs without a fallback target', () => {
  assert.equal(targetIdFromSearch('?target=wise-0855'), 'wise-0855');
  assert.equal(targetIdFromSearch('?target=unknown'), null);
  assert.equal(targetIdFromSearch('?ra=1'), null);
  assert.equal(searchWithTarget('?mode=explore', 'r-draconis'), '?mode=explore&target=r-draconis');
  assert.equal(searchWithTarget('?mode=explore&target=wise-0855', null), '?mode=explore');
  assert.equal(searchWithTarget('?target=wise-0855', 'unrecognised'), '');
});
