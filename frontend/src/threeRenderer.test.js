import test from 'node:test';
import assert from 'node:assert/strict';
import {createRenderer} from './threeRenderer.js';

test('renderer cleanup uses Window even after Aladin replaces self with a GUI instance', () => {
  const previousWindow = globalThis.window;
  const gui = {name:'Aladin HiPS selector'};
  let cancelled = false;
  globalThis.window = {self:gui, cancelAnimationFrame:() => {cancelled=true;}};
  try {
    class Renderer {
      constructor() {this.animationContext=window.self;}
      dispose() {this.animationContext.cancelAnimationFrame(null);}
    }
    const renderer=createRenderer({WebGLRenderer:Renderer}, {});
    assert.equal(window.self, gui);
    renderer.dispose(); assert.equal(cancelled,true);
    assert.throws(() => createRenderer({WebGLRenderer:class {constructor(){throw new Error('No WebGL');}}}, {}));
    assert.equal(window.self,gui);
  } finally {globalThis.window=previousWindow;}
});
