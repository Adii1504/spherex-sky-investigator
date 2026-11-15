"""SPHEREx FITS Inspection Tool

Run this script on a real SPHEREx FITS file provided by Person 1 to inspect:
- HDU layout and names
- Shapes and data types of each extension
- Header metadata (timestamps, detector ID, wavelength information)
- WCS dimensionality, projection, and pixel scale
- Mask / Flag values and variance extensions

Usage:
    python backend/processing/inspect_fits.py <path_to_fits_file>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


def inspect_fits(filepath: str | Path, full_headers: bool = False) -> None:
    path = Path(filepath)
    if not path.is_file():
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)

    print("=" * 78)
    print(f"SPHEREx FITS INSPECTION: {path.name}")
    print(f"Full Path: {path.resolve()}")
    print(f"File Size: {path.stat().st_size / 1024:.2f} KB")
    print("=" * 78)

    with fits.open(path, memmap=False) as hdul:
        num_hdus = len(hdul)
        print(f"\nTotal HDUs: {num_hdus}\n")

        # Table of HDUs
        print(f"{'Idx':<4} {'Name':<15} {'Type':<18} {'Shape':<18} {'Dtype':<10} {'Details'}")
        print("-" * 78)
        for idx, hdu in enumerate(hdul):
            shape_str = str(hdu.data.shape) if hdu.data is not None else "None (Header only)"
            dtype_str = str(hdu.data.dtype) if hdu.data is not None else "N/A"
            name = hdu.name if hdu.name else "(UNNAMED)"
            hdu_type = type(hdu).__name__

            extra = []
            if hdu.is_image and hdu.data is not None:
                finite = np.isfinite(hdu.data)
                fin_pct = (np.count_nonzero(finite) / hdu.data.size) * 100
                extra.append(f"{fin_pct:.1f}% finite")
                if fin_pct > 0:
                    extra.append(f"min={np.nanmin(hdu.data):.3g}, max={np.nanmax(hdu.data):.3g}")
            elif isinstance(hdu, fits.TableHDU | fits.BinTableHDU):
                extra.append(f"{len(hdu.columns)} cols, {hdu.data.shape[0]} rows")

            details = "; ".join(extra) if extra else "-"
            print(f"{idx:<4} {name:<15} {hdu_type:<18} {shape_str:<18} {dtype_str:<10} {details}")

        print("=" * 78)

        # Inspect each HDU in detail
        for idx, hdu in enumerate(hdul):
            name = hdu.name if hdu.name else f"HDU_{idx}"
            print(f"\n>>> [HDU {idx}: {name}] ({type(hdu).__name__})")

            # Check WCS
            header = hdu.header
            try:
                wcs = WCS(header)
                if wcs.is_celestial:
                    print(f"  * Celestial WCS Detected:")
                    print(f"    - Axis types: {wcs.axis_type_names}")
                    print(f"    - CTYPE: {[header.get(f'CTYPE{i+1}', '') for i in range(wcs.naxis)]}")
                    print(f"    - CRVAL: {[header.get(f'CRVAL{i+1}', '') for i in range(wcs.naxis)]}")
                    print(f"    - CRPIX: {[header.get(f'CRPIX{i+1}', '') for i in range(wcs.naxis)]}")
                    try:
                        scales = wcs.proj_plane_pixel_scales()
                        scales_arcsec = [s.to_value('arcsec') for s in scales]
                        print(f"    - Pixel scale: {scales_arcsec} arcsec/pixel")
                    except Exception as e:
                        print(f"    - Pixel scale calculation: {e}")
                elif wcs.has_spectral:
                    print(f"  * Spectral coordinate detected in WCS:")
                    print(f"    - Axis types: {wcs.axis_type_names}")
                else:
                    print("  * WCS: No celestial WCS detected.")
            except Exception as e:
                print(f"  * WCS parsing note: {e}")

            # Inspect relevant SPHEREx keywords
            key_categories: dict[str, list[str]] = {
                "Time / Epoch": [
                    "DATE-OBS", "DATE-BEG", "DATE-END", "MJD-OBS", "MJD-BEG", "MJD-END", "OBSTIME", "TIME-OBS"
                ],
                "Detector / Instrument": [
                    "TELESCOP", "INSTRUME", "DETECTOR", "DET_ID", "BAND", "CHANNEL", "OBS_ID", "EXP_ID"
                ],
                "Wavelength / Filter": [
                    "FILTER", "WAVELEN", "CENTWAVE", "WAVELMIN", "WAVELMAX", "LAMBDA", "LVF_BAND"
                ],
                "Photometry / Units": [
                    "BUNIT", "PHOTFNU", "PHOTFLAM", "FLUXUNIT", "GAIN", "RDNOISE"
                ],
            }

            print("  * Key Header Attributes:")
            found_any = False
            for cat, kw_list in key_categories.items():
                found_kws = {k: header[k] for k in kw_list if k in header}
                if found_kws:
                    found_any = True
                    kvs = ", ".join(f"{k}='{v}'" if isinstance(v, str) else f"{k}={v}" for k, v in found_kws.items())
                    print(f"    - {cat}: {kvs}")
            if not found_any:
                print("    - (None of the standard SPHEREx/observational keywords found in this HDU header)")

            # Check flags if this appears to be a mask/flag HDU
            if any(term in name.upper() for term in ["FLAG", "MASK", "DQ", "STATUS"]):
                if hdu.data is not None:
                    flags_data = hdu.data
                    print("  * Flag / Mask Analysis:")
                    print(f"    - Shape: {flags_data.shape}, dtype: {flags_data.dtype}")
                    unique_vals = np.unique(flags_data)
                    if len(unique_vals) <= 20:
                        print(f"    - Unique flag values: {unique_vals.tolist()}")
                    else:
                        print(f"    - Unique flag count: {len(unique_vals)} (min={unique_vals.min()}, max={unique_vals.max()})")
                    zeros = np.count_nonzero(flags_data == 0)
                    pct_good = (zeros / flags_data.size) * 100
                    print(f"    - Pixels with flag==0: {zeros}/{flags_data.size} ({pct_good:.2f}%)")

            # Check variance / error if applicable
            if any(term in name.upper() for term in ["VAR", "ERR", "SIGMA", "UNCERT", "STD"]):
                if hdu.data is not None:
                    var_data = hdu.data
                    print("  * Variance / Uncertainty Analysis:")
                    print(f"    - Shape: {var_data.shape}, dtype: {var_data.dtype}")
                    print(f"    - Range: min={np.nanmin(var_data):.3g}, max={np.nanmax(var_data):.3g}")

            # Dump full header cards if requested
            if full_headers:
                print("\n  --- FULL HEADER CARDS ---")
                for key, val in header.items():
                    print(f"    {key:<8} = {val}")

    print("\n" + "=" * 78)
    print("CHECKLIST FOR PERSON 2 & PERSON 1:")
    print("1. Science Image HDU: Which HDU contains the primary 2D flux array?")
    print("2. Mask / Flags HDU: Is there a DQ/FLAGS extension? Which bit values mean 'bad'?")
    print("3. Variance HDU: Is there a VAR / ERR extension, or is variance absent?")
    print("4. Observation Timestamp: Which keyword provides the exact UTC time (e.g., DATE-OBS)?")
    print("5. Wavelength: Is wavelength in the header, or does it vary spatially across the detector (LVF)?")
    print("6. WCS: Is 2D celestial WCS (RA---TAN, DEC--TAN) properly recognized by astropy?")
    print("=" * 78)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a SPHEREx FITS cutout file.")
    parser.add_argument("fits_file", type=str, nargs="?", default=None, help="Path to FITS file")
    parser.add_argument("--full-headers", action="store_true", help="Print all header cards")
    args = parser.parse_args()

    if args.fits_file is None:
        # Default to checking sample_data directory
        sample_dir = Path(__file__).resolve().parent / "sample_data"
        fits_files = list(sample_dir.glob("*.fits")) + list(sample_dir.glob("*.fits.gz"))
        if fits_files:
            target = fits_files[0]
            print(f"No file specified. Using first file found in sample_data: {target}")
            inspect_fits(target, full_headers=args.full_headers)
        else:
            print("No FITS file specified and none found in backend/processing/sample_data/.")
            print("\nUsage:")
            print("  python backend/processing/inspect_fits.py <path_to_fits_file> [--full-headers]")
            sys.exit(1)
    else:
        inspect_fits(args.fits_file, full_headers=args.full_headers)


if __name__ == "__main__":
    main()
