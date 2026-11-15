import { ApiError, request } from './api.js';

export async function loadTargetObservations(targetId, signal) {
  const result = await request(`/targets/${encodeURIComponent(targetId)}/observations`, undefined, signal, {prefix: '/api'});
  if (result?.target_id !== targetId || !Array.isArray(result.observations)
    || result.observations.some(item => item.target_id !== targetId || typeof item.product_id !== 'string')) {
    throw new ApiError('Target observation response does not match the selected target.', {code: 'invalid_response'});
  }
  return result;
}

export function loadProduct(productId, type, signal) {
  // Construct routes from IDs; never fetch arbitrary metadata URLs or filesystem paths.
  return request(`/observations/${encodeURIComponent(productId)}/${type}`, undefined, signal,
    {prefix: '/api', responseType: type === 'preview' ? 'blob' : 'text'});
}
