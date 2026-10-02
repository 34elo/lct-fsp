import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <section className="flex flex-col gap-3 p-6">
      <h1 className="text-2xl font-bold">Страница не найдена</h1>
      <Link to="/" className="font-semibold text-brand">
        На главную
      </Link>
    </section>
  );
}
