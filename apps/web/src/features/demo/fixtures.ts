/** Демо-кластер для экрана «новая профессия», когда ночной рост ещё не нашёл настоящих (E34-3). */
export interface ClusterView {
  skills: string[];
  support: number;
  covered: number;
}

export const SAMPLE_CLUSTER: ClusterView = {
  skills: ["unity", "csharp", "shaders", "game-physics"],
  support: 7,
  covered: 0.1,
};
