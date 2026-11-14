import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import { transformSync } from 'esbuild';

// esbuild is already supplied by Vite; no second compiler dependency is needed.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.jsx')) {
      const source = transformSync(readFileSync(new URL(url), 'utf8'), { loader: 'jsx', format: 'esm', jsx: 'transform' }).code;
      return { format: 'module', source, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});
