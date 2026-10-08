import "@testing-library/jest-dom/vitest";

// jsdom не знает ResizeObserver (нужен Radix Slider из @fsp/ui).
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
