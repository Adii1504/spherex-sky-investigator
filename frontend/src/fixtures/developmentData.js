export const FIXTURE_LABEL = 'Development fixture — not real SPHEREx data';

// Fictional identifiers, dates and science values; shaped like the actual API.
const observations = [
  {
    id: 'demo_obs_1', exposure_id: 'demo_exposure_1', observed_at: '2000-01-01T00:00:00Z',
    release: 'DEVELOPMENT ONLY', product_id: 'demo_product_1', detector: null,
    provenance: { archive: 'Fictional development archive', source_url: 'https://example.invalid/development-fixture', citation: null },
    file_wavelength_um: null, position_wavelength_um: null, quality: null,
  },
  {
    id: 'demo_obs_2', exposure_id: 'demo_exposure_2', observed_at: '2000-01-02T00:00:00Z',
    release: 'DEVELOPMENT ONLY', product_id: 'demo_product_2', detector: '1',
    provenance: { archive: 'Fictional development archive', source_url: 'https://example.invalid/development-fixture', citation: null },
    file_wavelength_um: [1, 2], position_wavelength_um: 1.5, quality: { usable: null, flagged_fraction: 0 },
  },
  {
    id: 'demo_obs_3', exposure_id: 'demo_exposure_3', observed_at: '2000-01-03T00:00:00Z',
    release: 'DEVELOPMENT ONLY', product_id: 'demo_product_3', detector: '2',
    provenance: { archive: 'Fictional development archive', source_url: 'https://example.invalid/development-fixture', citation: null },
    file_wavelength_um: [2, 3], position_wavelength_um: null, quality: { calibration_level: 2 },
  },
];

export async function fixtureSearch(scenario, signal, delayMs = 450) {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  await new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, delayMs);
    signal?.addEventListener('abort', abort, { once: true });
  });
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  if (scenario === 'error') {
    const error = new Error('Development fixture: simulated archive failure. Choose another fixture scenario or retry.');
    error.code = 'demo_archive_unavailable'; error.status = 502;
    throw error;
  }
  if (!['success', 'empty', 'partial', 'job-error', 'image-error'].includes(scenario)) throw new Error('Unknown development fixture scenario.');
  return {
    search_id: `demo_search_${scenario}`,
    observations: scenario === 'empty' ? [] : structuredClone(observations),
    coverage_summary: { count: scenario === 'empty' ? 0 : observations.length, complete: true },
    warnings: [FIXTURE_LABEL, 'All fixture dates, products, wavelengths and quality values are fictional.'],
  };
}

const jobs = new Map();
let nextJob = 0;

export function createFixtureSequence(selection, scenario, sourceObservations) {
  const chosen = sourceObservations.filter(item => selection.observation_ids.includes(item.id))
    .sort((a, b) => new Date(a.observed_at) - new Date(b.observed_at));
  const shown = scenario === 'partial' && chosen.length > 1 ? chosen.slice(0, -1) : chosen;
  const result = {
    search_id: selection.search_id, observation_ids: [...selection.observation_ids],
    previews: shown.map((observation, index) => ({
      observation: structuredClone(observation),
      preview_url: scenario === 'image-error' && index === 0 ? '/fixtures/missing-demo-image.png' : `/fixtures/demo-frame-${index % 3 + 1}.png`,
      metadata: { valid_fraction: index === 0 ? 0 : null, position_wavelength_um: observation.position_wavelength_um, fixture: true },
    })),
    processing_version: 'development-fixture-only',
    processing_settings: { alignment: 'Synthetic test charts on a shared pixel grid; no astronomical processing' },
    shared_display_settings: { stretch: 'Fictional calibration charts only' }, measurements: {},
    warnings: [FIXTURE_LABEL, 'Geometric test charts are not astronomical imagery or motion evidence.',
      ...(shown.length < chosen.length ? ['Development fixture: one selected preview intentionally omitted.'] : [])],
  };
  const job_id = `demo_job_${++nextJob}`;
  if (jobs.size >= 20) jobs.delete(jobs.keys().next().value);
  jobs.set(job_id, { step: 0, result, fail: scenario === 'job-error' });
  return { job_id };
}

export async function getFixtureJob(id, signal) {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  const job = jobs.get(id);
  if (!job) throw new Error('Development fixture job expired. Generate a new sequence.');
  const status = ['queued', 'running', job.fail ? 'failed' : 'succeeded'][Math.min(job.step++, 2)];
  return {
    job_id: id, status, progress: null,
    result: status === 'succeeded' ? structuredClone(job.result) : null,
    error: status === 'failed' ? { code: 'demo_processing_failed', message: 'Development fixture: simulated sequence failure. Choose another scenario and search again.' } : null,
  };
}
