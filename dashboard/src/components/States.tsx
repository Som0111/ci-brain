export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <div className="state state--loading">{label}…</div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state state--error">
      <strong>Couldn't load data.</strong>
      <div className="state__detail">{message}</div>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state state--empty">{message}</div>;
}
