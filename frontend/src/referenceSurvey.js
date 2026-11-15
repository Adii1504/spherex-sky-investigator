// Alternate services for the same CDS/P/DSS2/color survey, not substitute data.
export const DSS_MIRRORS = [
  'https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color',
  'https://skies.esac.esa.int/DSSColor',
  'https://alasky.cds.unistra.fr/DSS/DSSColor',
];

export function createSurveyLoader(A, aladin, { urls = DSS_MIRRORS, onStatus,
  timeoutMs = 8000, schedule = setTimeout, cancel = clearTimeout } = {}) {
  let generation = 0, timer, disposed = false;
  function load() {
    if (disposed) return;
    const run = ++generation;
    cancel(timer);
    const candidates = [...new Set(urls)];
    function attempt(index) {
      if (disposed || generation !== run) return;
      if (index >= candidates.length) {
        onStatus?.('error', 'The DSS reference sky could not load from its available mirrors. Retry or use the offline snapshot. SPHEREx searches use a separate backend.');
        return;
      }
      onStatus?.('loading');
      let settled = false;
      function finish(success) {
        if (settled || disposed || generation !== run) return;
        settled = true;
        cancel(timer);
        if (success) onStatus?.('ready');
        else attempt(index + 1);
      }
      timer = schedule(() => finish(false), timeoutMs);
      try {
        const survey = A.HiPS(candidates[index], {
          name: 'DSS2 colour', imgFormat: 'jpeg',
          successCallback: () => finish(true), errorCallback: () => finish(false),
        });
        aladin.setBaseImageLayer(survey);
      } catch { finish(false); }
    }
    attempt(0);
  }
  return { load, dispose() { disposed = true; generation++; cancel(timer); } };
}
