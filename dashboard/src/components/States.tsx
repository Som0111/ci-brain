import { apiConfigHint } from "../lib/api";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state state--loading" role="status">
      {label}…
    </div>
  );
}

function describe(status: number | null | undefined): { title: string; hint: string | null } {
  if (status === 0) {
    return {
      title: "Can't reach the API.",
      hint: apiConfigHint() ?? "Check that the backend is running and reachable from this browser.",
    };
  }
  if (status != null && status >= 500) {
    return { title: `The API had a problem (HTTP ${status}).`, hint: "Try again in a moment." };
  }
  if (status != null && status >= 400) {
    return { title: `The API rejected the request (HTTP ${status}).`, hint: null };
  }
  return { title: "Couldn't load data.", hint: null };
}

export function ErrorState({
  message,
  status,
  onRetry,
}: {
  message: string;
  status?: number | null;
  onRetry?: () => void;
}) {
  const { title, hint } = describe(status);
  return (
    <div className="state state--error" role="alert">
      <strong>{title}</strong>
      {hint && <div className="state__detail">{hint}</div>}
      <div className="state__detail">{message}</div>
      {onRetry && (
        <button type="button" className="state__retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state state--empty">{message}</div>;
}
