// Static, source-backed reference positions checked on 2026-11-14.
// SIMBAD's displayed ICRS coordinates at ep=J2000 are preserved below.
// Decimal conversion is only a change of units; no proper-motion propagation,
// source detection, component-resolution, or SPHEREx association is performed.
// Source: SIMBAD/CDS, https://simbad.cds.unistra.fr/ (ODbL).
// Database reference: Wenger et al. 2000, A&AS 143, 9 (2000A&AS..143....9W).

function position(hours, minutes, seconds, sign, degrees, arcminutes, arcseconds) {
  return {
    ra_deg: 15 * (hours + minutes / 60 + seconds / 3600),
    dec_deg: sign * (degrees + arcminutes / 60 + arcseconds / 3600),
  };
}

const shared = {
  coordinate_frame: 'ICRS',
  reference_epoch: 'J2000',
  source: 'SIMBAD / CDS',
  source_checked_on: '2026-11-14',
  astrometry_status: 'Catalogued reference position; SPHEREx association unverified',
  provisional: true,
  fov_arcmin: null,
  observation_association_verified: false,
};

export const targetCatalogue = [
  {
    ...shared,
    id: 'barnards-star', name: "Barnard's Star", object_type: 'BY Draconis variable star',
    source_identifier: "NAME Barnard's star", aliases: ['GJ 699', 'HIP 87937', 'V2500 Oph'],
    ...position(17, 57, 48.4984700685, 1, 4, 41, 36.113879676),
    coordinate_sexagesimal: '17 57 48.4984700685 +04 41 36.113879676',
    coordinate_reference: '2020yCat.1350....0G',
    astrometry_note: 'A static J2000 reference position. Barnard’s Star has high proper motion, so this marker is not its propagated position at SPHEREx observing dates. Archive coverage here does not confirm detection of the star.',
    references: [{ label: "SIMBAD: Barnard’s star (ICRS, ep=J2000)", url: 'https://simbad.cds.unistra.fr/simbad/sim-id?Ident=Barnard%27s+star' }],
  },
  {
    ...shared,
    id: 'epsilon-indi-b', name: 'Epsilon Indi B', object_type: 'Brown dwarf system',
    source_identifier: '* eps Ind B', aliases: ['eps Ind B', 'GJ 845 B', 'WDS J22034-5647Ba,Bb'],
    ...position(22, 4, 10.5951812451, -1, 56, 46, 58.239102418),
    coordinate_sexagesimal: '22 04 10.5951812451 -56 46 58.239102418',
    coordinate_reference: '2020yCat.1350....0G',
    astrometry_note: 'This is the SIMBAD epsilon Indi B catalogue entry for the brown-dwarf system. It is not a separately measured Ba or Bb position and is not asserted to be a barycentre. No orbital or proper-motion propagation is applied.',
    references: [{ label: 'SIMBAD: epsilon Indi B (ICRS, ep=J2000)', url: 'https://simbad.cds.unistra.fr/simbad/sim-id?Ident=%2A+eps+Ind+B' }],
  },
  {
    ...shared,
    id: 'wise-0855', name: 'WISE 0855', object_type: 'Brown dwarf',
    source_identifier: 'WISEA J085510.74-071442.5', aliases: ['WISE J085510.83-071442.5', 'CNS5 2194'],
    ...position(8, 55, 16.53798, -1, 7, 14, 49.3728),
    coordinate_sexagesimal: '08 55 16.53798 -07 14 49.3728',
    coordinate_reference: '2021ApJS..253....7K',
    astrometry_note: 'The marker uses the cited SIMBAD ICRS position displayed at J2000, not coordinates inferred from the WISE identifier. This high-proper-motion object is not propagated to the SPHEREx observation epoch; its association with any preview remains unverified.',
    references: [{ label: 'SIMBAD: WISE J085510.83−071442.5 (ICRS, ep=J2000)', url: 'https://simbad.cds.unistra.fr/simbad/sim-id?Ident=WISE+J085510.83-071442.5' }],
  },
  {
    ...shared,
    id: 'rw-aurigae', name: 'RW Aurigae', object_type: 'T Tauri star',
    source_identifier: 'V* RW Aur', aliases: ['RW Aur', 'HD 240764', 'HIP 23873'],
    ...position(5, 7, 49.5662483, 1, 30, 24, 5.177426),
    coordinate_sexagesimal: '05 07 49.5662483 +30 24 05.177426',
    coordinate_reference: '2007A&A...474..653V',
    astrometry_note: 'The marker follows the SIMBAD RW Aur catalogue entry, cross-identified as HD 240764. It does not resolve the stellar components or identify a source in a SPHEREx image. No coordinate propagation is applied.',
    references: [{ label: 'SIMBAD: RW Aur / HD 240764 (ICRS, ep=J2000)', url: 'https://simbad.cds.unistra.fr/simbad/sim-id?Ident=HD+240764' }],
  },
  {
    ...shared,
    id: 'r-draconis', name: 'R Draconis', object_type: 'Mira variable star',
    source_identifier: 'V* R Dra', aliases: ['R Dra', 'HD 149880', 'HIP 81014'],
    ...position(16, 32, 40.2265999080, 1, 66, 45, 17.925901992),
    coordinate_sexagesimal: '16 32 40.2265999080 +66 45 17.925901992',
    coordinate_reference: '2020yCat.1350....0G',
    astrometry_note: 'A static SIMBAD J2000 reference position, with no propagation to an observation date. Search results describe observations covering the field, not a confirmed detection or variability measurement of R Draconis.',
    references: [{ label: 'SIMBAD: R Dra (ICRS, ep=J2000)', url: 'https://simbad.cds.unistra.fr/simbad/sim-id?Ident=R+Dra' }],
  },
];

export function hasCatalogueCoordinates(target) {
  return target?.coordinate_frame === 'ICRS' && Number.isFinite(target.ra_deg)
    && target.ra_deg >= 0 && target.ra_deg < 360 && Number.isFinite(target.dec_deg)
    && target.dec_deg >= -90 && target.dec_deg <= 90;
}

export function getCatalogueTarget(id) {
  return targetCatalogue.find(target => target.id === id) || null;
}

// Unknown links are not resolved to a different target and never trigger a query.
export function targetIdFromSearch(search) {
  return getCatalogueTarget(new URLSearchParams(search).get('target'))?.id || null;
}

export function searchWithTarget(search, id) {
  const params = new URLSearchParams(search);
  if (getCatalogueTarget(id)) params.set('target', id);
  else params.delete('target');
  return params.size ? `?${params.toString()}` : '';
}
