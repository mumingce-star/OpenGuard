import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import ts from "typescript";
const require = createRequire(import.meta.url);
export function runtime(env = {}) {
  const cache = new Map(),
    storage = new Map();
  let transport = () => {
    throw new TypeError("offline");
  };
  const shared = {
    console,
    URL,
    URLSearchParams,
    AbortController,
    DOMException,
    FormData,
    Response,
    Error,
    TypeError,
    Date,
    crypto: globalThis.crypto,
    setTimeout,
    clearTimeout,
    window: { setTimeout, clearTimeout },
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
    fetch: (...args) => transport(...args),
  };
  function load(relative) {
    const filename = path.resolve(
      fileURLToPath(new URL("../src/", import.meta.url)),
      relative,
    );
    // URL.fileURLToPath handles Windows usernames and spaces correctly.
    return fromFile(filename);
  }
  function fromFile(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const module = { exports: {} };
    cache.set(filename, module.exports);
    const source = fs
      .readFileSync(filename, "utf8")
      .replaceAll("import.meta.env", JSON.stringify(env));
    const output = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    vm.runInNewContext(
      output,
      {
        ...shared,
        module,
        exports: module.exports,
        require: (specifier) =>
          specifier.startsWith(".")
            ? fromFile(path.resolve(path.dirname(filename), specifier + ".ts"))
            : require(specifier),
      },
      { filename },
    );
    return module.exports;
  }
  return {
    load,
    storage,
    shared,
    setFetch: (fn) => {
      transport = fn;
    },
  };
}
