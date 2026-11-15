"""Read supplied catalogue metadata and approved manifest associations; no propagation."""
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from .fits_preview.reader import json_safe


def load_targets():
    # Exact metadata from the frontend teammate's catalogue, without new claims.
    return json.loads((Path(__file__).parent / "data" / "targets.json").read_text(encoding="utf-8"))


def public_links(values):
    result = []
    for item in values or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        parsed = urlsplit(url)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment:
            result.append({"label": item.get("label", "Reference"), "url": url})
    return result


def install(app, registry, error):
    targets = {t["id"]: t for t in load_targets()}

    @app.get('/api/local-products')
    def local_products():
        # Only public registry metadata; raw filesystem paths never leave the server.
        items = []
        for product_id, entry in list(registry.entries.items())[:100]:
            if entry.get('target_id'):
                continue
            try:
                registry.resolve(product_id)
                available = True
            except (KeyError, FileNotFoundError):
                available = False
            prefix = '/api/observations/' + quote(product_id, safe='')
            items.append({'product_id': product_id, 'target_id': None,
                'available': available, 'provisional': True,
                'association_status': 'No catalogue association established',
                'astrometry_status': 'unavailable', 'predicted_position': None,
                'sha256': entry.get('sha256'),
                'fits_url': prefix + '/fits' if available else None,
                'preview_url': prefix + '/preview' if available else None,
                'quality_url': prefix + '/quality' if available else None,
                'label': entry.get('label'), 'footprint_stcs': entry.get('footprint_stcs'),
                'observed_at': entry.get('observation', {}).get('observed_at'),
                'detector': entry.get('observation', {}).get('detector'),
                'file_wavelength_um': entry.get('observation', {}).get('file_wavelength_um'),
                'position_wavelength_um': entry.get('observation', {}).get('position_wavelength_um'),
                'references': public_links(entry.get('references'))})
        return json_safe({'observations': items})

    def target(target_id):
        if target_id not in targets:
            raise error(404, "target_not_found", "Target not found")
        return targets[target_id]

    @app.get("/api/targets")
    def list_targets():
        return {"targets": list(targets.values())}

    @app.get("/api/targets/{target_id}")
    def get_target(target_id: str):
        return target(target_id)

    @app.get("/api/targets/{target_id}/observations")
    def observations(target_id: str):
        target(target_id)
        items = []
        for product_id, entry in sorted(registry.entries.items(), key=lambda item: (
                item[1].get("observation", {}).get("observed_at") or "", item[0])):
            if entry.get("target_id") != target_id:
                continue
            info = entry.get("observation", {})
            try:
                registry.resolve(product_id)
                available = True
            except (FileNotFoundError, KeyError):
                available = False
            prefix = "/api/observations/" + quote(product_id, safe="")
            # Only an explicitly supplied per-observation prediction is exposed.
            # Never substitute static catalogue coordinates for a propagated position.
            prediction = entry.get("predicted_position")
            if prediction:
                from .fits_preview.routes import validate_position
                try:
                    prediction = validate_position(prediction)
                except ValueError:
                    prediction = None
            items.append({"product_id": product_id, "target_id": target_id,
                "observed_at": info.get("observed_at"), "detector": info.get("detector"),
                "file_wavelength_um": info.get("file_wavelength_um"),
                "position_wavelength_um": info.get("position_wavelength_um"),
                "file_wavelength": info.get("file_wavelength"),
                "time_scale": info.get("time_scale"),
                "footprint_stcs": entry.get("footprint_stcs"),
                "dataset": entry.get("dataset"),
                "sha256": entry.get("sha256"),
                "fits_url": prefix + "/fits" if available else None,
                "predicted_position": prediction,
                "astrometry_status": prediction["astrometry_status"] if prediction else "unavailable",
                "provisional": entry.get("provisional", True),
                "association_status": entry.get("provenance_status", "unconfirmed"),
                "available": available, "preview_url": prefix + "/preview" if available else None,
                "quality_url": prefix + "/quality" if available else None,
                "references": public_links(entry.get("references")),
                "evidence": public_links(entry.get("evidence")),
                "spectra": public_links(entry.get("spectra"))})
        return json_safe({"target_id": target_id, "status": "available" if items else "unavailable",
                          "observations": items,
                          "warnings": ["Manifest associations are supplied metadata, not source detections."]})
