# SPHEREx target dataset

21 validated Level 2 FITS cutouts for 5 targets.

## Contents
- fits/                      validated FITS cutouts
- metadata/clean_dataset_manifest_final.csv  one row per FITS file
- metadata/target_astrometry_master.csv      adopted astrometry
- metadata/rw_aur_component_reference.csv    RW Aur A/B details
- metadata/target_coordinates_per_observation.csv  position at each DATE-OBS
- metadata/fits_coverage_validation.csv     pixel position / edge checks
- metadata/duplicate_audit_final.csv, excluded_files_final.csv
- SHA256SUMS.txt

## Targets and astrometry
- Barnard's Star (Barnards_Star): Gaia DR3 4472832130942575872, epoch 2016.0, flag GOOD_GAIA_SOLUTION
- Epsilon Indi B (Epsilon_Indi_B): Gaia DR3 6412596012146801152, epoch 2016.0, flag PROVISIONAL_HIGH_RUWE
- WISE 0855-0714 (WISE_0855): CatWISE2020 1342m076_b0-054325, epoch 2015.405, flag PROVISIONAL_CATWISE2020
- RW Aurigae A (RW_Aurigae): Gaia DR3 156430822114424576, epoch 2016.0, flag GAIA_RUWE_1.50_WARNING
- R Draconis (R_Draconis): Gaia DR3 1648328016354496384, epoch 2016.0, flag GAIA_OK_RV_ASSUMED_ZERO

## Assumptions and limitations
- Cutouts are centred on the target position propagated to each observation date (proper motion; parallax and RV where available).
- WISE 0855 uses CatWISE2020 J085508.34-071439.2 at epoch 2015.405; position uncertainty is ~2 arcsec by 2026.
- Epsilon Indi B is provisional (high Gaia RUWE); Ba/Bb are treated as one combined source.
- RW Aur A and B are ~1.5 arcsec apart and unresolved by SPHEREx.
- Missing radial velocities (Epsilon Indi B, R Draconis) are set to zero; the effect is far below one pixel.
- Being inside an image does not prove the source was detected; see detection_check.csv if it was produced.
- 'bandpass' is derived from the DETECTOR header value.
- Pipeline version(s) in filenames: v27; 17 distinct processing-batch suffixes (probably year-day-of-year of processing; not confirmed against IRSA docs).

## Coverage summary
- EDGE: 1, INSIDE_IMAGE: 20

## Detection check (detection_check.csv)
Brightest-pixel SNR at the predicted position, compared with random control positions in the same image. A coarse screen, not photometry.
- Barnards_Star: DETECTED_CANDIDATE=5
- Epsilon_Indi_B: ABOVE_THRESHOLD_NOT_UNUSUAL=2, DETECTED_CANDIDATE=1
- RW_Aurigae: DETECTED_CANDIDATE=4
- R_Draconis: DETECTED_CANDIDATE=4
- WISE_0855: ABOVE_THRESHOLD_NOT_UNUSUAL=4, NOT_DETECTED=1
- DETECTED_CANDIDATE = clearly above random positions; ABOVE_THRESHOLD_NOT_UNUSUAL = not distinguishable from field noise or neighbouring stars (not a detection); NOT_DETECTED = SNR below 5.
