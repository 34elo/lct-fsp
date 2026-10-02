import { Route, Routes } from "react-router-dom";

function Landing() {
  return <h1>ФСП Карьера</h1>;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
    </Routes>
  );
}
