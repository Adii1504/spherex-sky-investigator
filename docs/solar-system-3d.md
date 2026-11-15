# Interactive Solar System and rotating globes

Click a planet label on the sky map, a body card, or the Earth observer badge to
open the 3D dialog. The camera moves into a textured globe. The ten selectors
include all eight planets, the Sun, and the Moon. Saturn has a separate ring mesh.

Catalogue stars are also selectable from gold points and labels in the 3D view,
the **Catalogue stars** selector row, and the target detail panel's **View in 3D**
button. Sky-map star markers select the search/details panel without opening a
modal. Selecting a star inside the 3D viewer replaces the planet close-up with
a rotating procedural illustration and the original catalogue identity and
coordinates. Brown dwarfs, including WISE 0855 and Epsilon Indi B, use a distinct
illustrative palette. Their surface, visible color, physical size, rotation,
component structure, and distances are not inferred or claimed as measured.
The close-up does not place these distant objects inside the Solar System.
Stellar illustrations and the Sun have a bright surface and additive glow halo;
brown-dwarf illustrations remain dimmer. This is a visual treatment, not calibrated
luminosity. Closing the dialog restores page position and focus without scrolling
the background. The long catalogue-details panel scrolls independently within
the viewport, and search/3D actions appear above its metadata.

- Drag to orbit the camera; use the wheel or plus/minus buttons to zoom.
- **Solar System overview** shows the planets around the Sun at their computed
  positions. **Inner planets** provides a closer camera without altering distances.
- **Pause orbits** freezes the simulation date. **Pause spin** stops surface spin
  independently. Orbit speed is selectable at 1, 5, or 30 simulated days per second.
- The timestamp identifies the simulated date. **Starting epoch** returns to the
  beginning of the displayed year-long playback; it does not claim to be live time.
- Escape or the close button returns to the sky. The renderer, controls, textures,
  event listeners, and animation frame are disposed when the dialog closes.

## Position and scale conventions

`GET /api/solar-system/scene` returns a cached, daily-sampled year of heliocentric
positions. Astropy's builtin ephemeris supplies barycentric positions; subtracting
the Sun produces heliocentric vectors with ICRS-aligned axes. AU distances remain
linear. The renderer maps `(X,Y,Z)` to `(X,Z,-Y)` to keep a right-handed scene with
celestial north upward. Daily positions are interpolated for animation; the
playback loops after 365 days. No external ephemeris download is needed.

Orbit lines are two-body osculating curves calculated from initial heliocentric
position and velocity with the solar gravitational parameter. They approximate
the orbital path; the moving body positions use the ephemeris samples instead.
They are not precision long-term orbit predictions.

Overview globes have enlarged radii so they can be selected. The Moon's true
separation would be hidden within the enlarged Earth, so the Moon is available as
a close-up and omitted from the overview. Close-ups recenter one body at the
origin and are distinct from the Earth-view sky map. Sunward lighting is based
on the current body's heliocentric direction. Axial tilt, surface rotation phase,
and the Saturn ring model are illustrative; this is not an exact IAU pole or
surface-longitude solution. Spin is an independent visual animation.

Gold background points use the supplied catalogue star directions in ICRS. Their
display radius is arbitrary; it does not represent stellar distances. Labels
separate in screen space without moving their astronomical anchors.

## Textures and distribution

The 2k maps are local JPEGs in `frontend/public/textures/solar/`, copied by Vite
into the served build. The viewer therefore needs no third-party texture requests.
Fresh source checkouts can restore the licensed files with:

```powershell
.\.venv\Scripts\python scripts/download_solar_textures.py
npm.cmd run build --prefix frontend
```

Maps are by [Solar System Scope / INOVE](https://www.solarsystemscope.com/textures/),
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), based on NASA
imagery. The provider enhances colors and fills unmapped gaps with inferred
terrain. These are mapped globes, not live footage or complete topographic models.
Attribution is displayed in the viewer and included alongside the image files.

## Verification

Backend tests check heliocentric Sun/Earth coordinates, Earth/Sun distance,
Moon/Earth separation, outer-planet distance, finite ephemeris samples, motion,
and closed orbital curves. Frontend tests check AU-preserving interpolation,
ICRS handedness, body selection, layer independence, label separation, and retry
behavior. Earth and Saturn close-ups and the orbital overview were exercised in
Opera. WebGL2 is required; a rendering failure leaves a closeable error dialog
and preserves the underlying sky and descriptions.

Reference: [Astropy Solar System coordinates](https://docs.astropy.org/en/stable/coordinates/solarsystem.html).
