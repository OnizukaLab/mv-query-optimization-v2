export default function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <div className="p-8">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-zinc-500">{note}</p>
    </div>
  );
}
