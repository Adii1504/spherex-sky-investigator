// Aladin Lite 3.8.2 assigns window.self to GUI instances. Three captures `self`
// as its animation context at construction, including when disposing a renderer
// that uses our own RAF loop. Bind the browser context during that synchronous
// construction only; restore Aladin's value without modifying either library.
export function createRenderer(THREE, options) {
  const previous = window.self;
  try {
    window.self = window;
    return new THREE.WebGLRenderer(options);
  } finally {
    window.self = previous;
  }
}
