"""Offline, geocentric educational ephemerides; never archive detections."""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache

from astropy.coordinates import get_body, get_body_barycentric, get_body_barycentric_posvel
from astropy.time import Time
from astropy import units as u
from astropy.constants import GM_sun
import numpy as np


BODIES = (
    ('sun', 'Sun', 'Star', '#ffd166', 'Our nearest star supplies the light and energy that shape the Solar System.'),
    ('mercury', 'Mercury', 'Rocky planet', '#b9aba0', 'The smallest planet orbits closest to the Sun and has a heavily cratered surface.'),
    ('venus', 'Venus', 'Rocky planet', '#edc781', 'A thick atmosphere traps heat around this cloud-covered rocky world.'),
    ('earth', 'Earth', 'Our observing world', '#6abce8', 'Our ocean-covered home is the viewpoint for this sky map, so it has no sky marker.'),
    ('moon', 'Moon', 'Natural satellite', '#d5dbe5', 'Earth’s natural satellite has a cratered surface and changes its illuminated appearance through the month.'),
    ('mars', 'Mars', 'Rocky planet', '#e58b64', 'The red planet has volcanoes, canyons, and evidence of ancient water.'),
    ('jupiter', 'Jupiter', 'Gas giant', '#dcad87', 'The largest planet has cloud bands and powerful atmospheric storms.'),
    ('saturn', 'Saturn', 'Gas giant', '#e9d39b', 'This gas giant is surrounded by a prominent system of icy rings.'),
    ('uranus', 'Uranus', 'Ice giant', '#8bd8d7', 'An ice giant with an unusually tilted rotation axis.'),
    ('neptune', 'Neptune', 'Ice giant', '#719bf1', 'The most distant planet from the Sun is a cold world with strong winds.'),
)


@lru_cache(maxsize=2)
def positions(minute):
    instant = datetime.fromtimestamp(minute * 60, timezone.utc)
    time = Time(instant)
    bodies = []
    for key, name, kind, color, description in BODIES:
        body = dict(id=key, name=name, kind=kind, color=color, description=description,
                    reference_url=f'https://science.nasa.gov/{key}/', ra_deg=None,
                    dec_deg=None, distance_au=None)
        if key != 'earth':
            # Explicit builtin avoids ephemeris downloads and mutable defaults.
            coordinate = get_body(key, time, ephemeris='builtin')
            body.update(ra_deg=float(coordinate.ra.deg), dec_deg=float(coordinate.dec.deg),
                        distance_au=float(coordinate.distance.to_value(u.au)))
        bodies.append(body)
    return dict(observed_at=instant.isoformat().replace('+00:00', 'Z'), bodies=bodies,
                observer='Earth center', frame='GCRS (ICRS-aligned axes)',
                ephemeris='Astropy / ERFA builtin',
                note='Approximate geocentric positions for exploration, not local visibility or precision pointing. Markers are enlarged symbols, not survey detections or surface images.')


def install(app):
    @app.get('/api/solar-system')
    def solar_system():
        return deepcopy(positions(int(datetime.now(timezone.utc).timestamp() // 60)))

    @app.get('/api/solar-system/scene')
    def solar_scene():
        day = int(datetime.now(timezone.utc).timestamp() // 86400)
        return deepcopy(scene_data(day))


@lru_cache(maxsize=2)
def scene_data(day):
    """One year of ephemeris samples; heliocentric positions in ICRS axes, AU."""
    epoch = Time(datetime.fromtimestamp(day*86400, timezone.utc))
    times = epoch + np.arange(367) * u.day
    sun = get_body_barycentric('sun', times, ephemeris='builtin').xyz.to_value(u.au)
    sun_pos, sun_vel = get_body_barycentric_posvel('sun', epoch, ephemeris='builtin')
    mu = GM_sun.to_value(u.au**3 / u.day**2)
    items = []
    for key, name, kind, color, description in BODIES:
        xyz = np.zeros_like(sun) if key == 'sun' else get_body_barycentric(key,times,ephemeris='builtin').xyz.to_value(u.au)-sun
        orbit = []
        if key not in ('sun','moon'):
            pos, vel = get_body_barycentric_posvel(key,epoch,ephemeris='builtin')
            r=(pos.xyz-sun_pos.xyz).to_value(u.au)
            v=(vel.xyz-sun_vel.xyz).to_value(u.au/u.day)
            h=np.cross(r,v); evec=np.cross(v,h)/mu-r/np.linalg.norm(r)
            e=np.linalg.norm(evec); axis=evec/e
            normal=h/np.linalg.norm(h); other=np.cross(normal,axis)
            a=1/(2/np.linalg.norm(r)-np.dot(v,v)/mu)
            theta=np.linspace(0,2*np.pi,161)
            radius=a*(1-e*e)/(1+e*np.cos(theta))
            orbit=(radius[:,None]*(np.cos(theta)[:,None]*axis+np.sin(theta)[:,None]*other)).tolist()
        items.append(dict(id=key,name=name,kind=kind,color=color,description=description,
                          samples_au=xyz.T.tolist(),orbit_au=orbit))
    return dict(epoch=epoch.utc.isot+'Z', step_days=1, duration_days=365,
                frame='Heliocentric, ICRS-aligned axes', units='AU', bodies=items,
                note='Positions: interpolated daily Astropy / ERFA builtin ephemeris samples. Orbit curves: approximate two-body paths at the starting epoch. Planet sizes enlarged; surface spin is illustrative, not an exact longitude prediction.')
