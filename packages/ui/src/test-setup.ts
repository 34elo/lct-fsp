import "@testing-library/jest-dom/vitest";

// jsdom не знает ResizeObserver (нужен Radix Slider).
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
