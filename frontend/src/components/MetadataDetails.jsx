import React from 'react';
import { formatUtc, formatWavelength, safeProvenanceUrl } from '../search.js';

export function MetadataDetails({ observation, metadata = {}, fixture = false, compact = false }) {
  if (!observation) return <p className="muted">Generate a sequence to inspect a dated observation.</p>;

  const provenance = observation.provenance;
  const sourceUrl = safeProvenanceUrl(provenance?.source_url);
  const quality = observation.quality;
  const supplied = quality?.dataset;
  const prediction = quality?.predicted_position;
  const positionWavelength = Object.hasOwn(metadata, 'position_wavelength_um')
    ? metadata.position_wavelength_um : observation.position_wavelength_um;
  const qualityAssessment = typeof quality?.usable === 'boolean'
    ? (quality.usable ? 'Backend reports usable' : 'Backend reports not usable') : 'Not assessed';
  const wavelengthRange = observation.file_wavelength_um;

  return <>
    <dl className="metadata-list">
      <div><dt>Observed / UTC</dt><dd>{formatUtc(observation.observed_at)}</dd></div>
      <div><dt>Detector</dt><dd>{observation.detector ?? 'Unavailable'}</dd></div>
      <div><dt>Release</dt><dd>{observation.release ?? 'Unavailable'}</dd></div>
      <div><dt>File wavelength coverage</dt><dd>{wavelengthRange == null ? 'Unavailable' : `${wavelengthRange.join(' – ')} µm`}</dd></div>
      <div><dt>Wavelength at search position</dt><dd>{formatWavelength(positionWavelength)}</dd></div>
      <div><dt>Quality assessment</dt><dd>{qualityAssessment}</dd></div>
      {metadata.valid_fraction != null && <div><dt>Valid preview coverage</dt><dd>{(metadata.valid_fraction * 100).toFixed(1)}%</dd></div>}
      {!compact && metadata.orientation && <div><dt>Backend orientation</dt><dd>{metadata.orientation}</dd></div>}
      <div><dt>Archive provenance</dt><dd>{!fixture && sourceUrl
        ? <a href={sourceUrl} target="_blank" rel="noreferrer">{provenance.archive} ↗<span className="sr-only"> (opens in a new tab)</span></a>
        : provenance?.archive ?? 'Unavailable'}</dd></div>
    </dl>
    {supplied && <section className="supplied-observation-metadata"><h4>Supplied observation metadata</h4><dl className="metadata-list">
      <div><dt>Source catalogue</dt><dd>{supplied.adopted_astrometry?.source_catalogue} · {supplied.adopted_astrometry?.source_id}</dd></div>
      <div><dt>Reference epoch</dt><dd>{supplied.adopted_astrometry?.ref_epoch_jyear ?? 'Unavailable'}</dd></div>
      <div><dt>Position at observation</dt><dd>{prediction ? `RA ${prediction.ra_deg}°, Dec ${prediction.dec_deg}°` : 'Unavailable'}</dd></div>
      <div><dt>Supplied coverage</dt><dd>{supplied.coverage?.status ?? 'Unavailable'} · coverage is not detection</dd></div>
      <div><dt>Detection screen</dt><dd>{supplied.detection_screen?.verdict ?? 'Unavailable'} · peak SNR {supplied.detection_screen?.snr_peak ?? 'Unavailable'}</dd></div>
    </dl><p>{supplied.propagation?.note}</p><p>{supplied.detection_screen?.method_note}</p></section>}
    <details className="metadata-extra">
      <summary>Product identity and quality metadata</summary>
      <dl className="metadata-list">
        <div><dt>Product ID</dt><dd>{observation.product_id}</dd></div>
        <div><dt>Observation ID</dt><dd>{observation.id}</dd></div>
        <div><dt>Canonical exposure ID</dt><dd>{observation.exposure_id}</dd></div>
      </dl>
      {quality == null ? <p className="muted">Quality metadata unavailable.</p> : <pre>{JSON.stringify(quality, null, 2)}</pre>}
      {provenance?.citation && <p>{provenance.citation}</p>}
      {!compact && Object.keys(metadata).length > 0 && <details>
        <summary>Supplied preview metadata</summary>
        <pre>{JSON.stringify(metadata, null, 2)}</pre>
      </details>}
    </details>
  </>;
}
