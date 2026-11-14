// Populate only after the team supplies verified coordinates and field sizes.
export const targetPresets = [
  "Barnard's Star", 'Epsilon Indi B', 'WISE 0855', 'RW Aurigae', 'R Draconis',
].map(name => ({ name, ra_deg: null, dec_deg: null, fov_arcmin: null }));
