# Game Zone

Open **Game Zone** in the main navigation at http://127.0.0.1:8010/.
The arcade has Canvas 2D games and a Three.js 3D mission, loaded on demand. It does not
need archive access or backend requests once the application assets are loaded.
It is fictional entertainment, separate from astronomical evidence.

## Games

- **Starship Intercept (3D):** a medium-difficulty, finite mission against exactly
  three blue/orange hostile craft. Pilot a gray twin-engine fighter, dodge aimed
  red laser bursts, and fire twin cyan blasters. Models are original, inspired by
  the supplied reference silhouettes: image 1 for enemies, images 2/3 for the player.
  A moving depth starfield and periodically passing small planets/stars provide
  flight motion. Planets are background scenery, not obstacles or real ephemerides.
  Destroy all three hostiles for the retro **MISSION ACCOMPLISHED** screen with
  three stars, score, and accuracy. Losing all five hull points produces failure
  and a replay action. This mission requires WebGL2; the 2D games remain available
  on the arcade page.

- **Nebula Patrol:** shoot alien formations, dodge their fire, and face a boss
  every fifth wave. Waves get faster and harder as the run continues.
- **Asteroid Run:** shoot and dodge drifting rocks. Asteroids have more health
  than the initial patrol enemies and do not fire back.

Both 2D modes have three hull points, three limited pulses, score tracking, particle
effects, shield repairs, and an eight-second twin-laser upgrade. Clear a wave to
advance. Runs continue until the ship loses all health; restart creates a fresh run.
Changing modes resets the current run and saves its score locally.

## Controls

For **Starship Intercept**, use WASD/arrows to fly in two axes, hold Space to fire,
P/Escape to pause, and R to restart. Drag and hold in the playfield to move and fire
with a mouse or touch screen; touch buttons provide the same flight/fire actions.
Aim assistance engages only when the fighter lines up with a living target.
Enemy gun glow warns of the next burst. Brief post-hit invulnerability prevents a
single burst from instantly consuming the whole hull. There are no pulses or
power-up drops in this mission. **Back to arcade** ends the mission and returns to
the other games. Its animation, event listeners, audio, and GPU resources are
released when leaving.

The controls below apply to the 2D games:

| Control | Action |
| --- | --- |
| WASD / arrow keys | Move in the playfield |
| Hold Space | Fire lasers |
| Q | Pulse: removes hostile shots and damages visible targets |
| P / Escape | Pause or resume |
| R | Restart |
| Touch or mouse drag in the canvas | Move toward the pointer and fire while held |
| Touch buttons | Move left/right, hold fire, or trigger a pulse |

Click **Launch mission** to start and focus the playfield. Launch scrolls the
canvas into view. The canvas retains its aspect ratio and fits the desktop viewport.
Keyboard controls are scoped to the playfield; the rest of the application keeps
normal navigation. Moving focus outside the console, changing browser tabs, or
losing window focus pauses the game. Leaving Game Zone unmounts the game and ends
the run, removing its animation frame and event listeners.

Sound defaults off. **Sound on** enables short locally synthesized effects after
a user gesture. No audio files, remote assets, paid service, or new dependency is
required. Unsupported audio leaves the game playable without sound.

High scores are stored per mode in this browser's localStorage, with guarded
read/write operations. Browser storage restrictions or clearing localStorage can
remove scores; there is no account or shared leaderboard.

## Implementation and checks

- `frontend/src/gameEngine.js`: simulation, collision detection, waves, pickups,
  bosses, scoring, and drawing. Simulation time steps are capped to limit jumps
  after stalls. Collisions consume each laser once and give the ship a brief
  invulnerability period after damage.
- `frontend/src/components/GameZone.jsx`: game selection, keyboard/pointer/touch
  controls, HUD, pause/restart, audio, high scores, and lifecycle cleanup.
- `frontend/src/gameZone.css`: responsive arcade presentation.

Regression tests cover bounded movement, pause, collision scoring, damage
immunity, game over, restarting state, wave progression, bosses, asteroid rules,
power-ups and pulse limits. An application test covers navigation into Game Zone
while the backend is unavailable and returning to the science interface.

The 3D mission uses `starshipMission.js` for independent simulation and swept
collision checks, `starshipModels.js` for reference-inspired geometry, and
`StarshipMission.jsx` for rendering, HUD, input, and retro result screens.
Tests verify exactly three targets, bounded movement, high-speed collisions,
aimed fire, hit protection, failure/restart, and victory without respawning.
Scripted full-run checks exercise both stationary defeat and moving/firing victory.
