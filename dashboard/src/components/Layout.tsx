import { NavLink, Outlet } from "react-router-dom";
import { useRepos } from "../lib/useRepos";
import { ErrorState, LoadingState } from "./States";

export function Layout() {
  const { repos, selectedRepoId, setSelectedRepoId, loading, error } = useRepos();

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__logo">CI Brain</span>
          <span className="topbar__tagline">Test intelligence dashboard</span>
        </div>

        <nav className="topbar__nav">
          <NavLink to="/runs" className={({ isActive }) => (isActive ? "navlink navlink--active" : "navlink")}>
            Run history
          </NavLink>
          <NavLink
            to="/flakiness"
            className={({ isActive }) => (isActive ? "navlink navlink--active" : "navlink")}
          >
            Flaky tests
          </NavLink>
          <NavLink to="/impact" className={({ isActive }) => (isActive ? "navlink navlink--active" : "navlink")}>
            Impact analysis
          </NavLink>
          <NavLink
            to="/benchmark"
            className={({ isActive }) => (isActive ? "navlink navlink--active" : "navlink")}
          >
            Benchmark
          </NavLink>
        </nav>

        <div className="topbar__repo">
          {loading && <LoadingState label="Loading repos" />}
          {error && <span className="text-muted">API unreachable</span>}
          {!loading && !error && repos.length > 0 && (
            <select
              value={selectedRepoId ?? ""}
              onChange={(e) => setSelectedRepoId(Number(e.target.value))}
              aria-label="Select repository"
            >
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </header>

      {error ? (
        <main className="page">
          <ErrorState message={`Couldn't reach the API at load time: ${error}. Is the backend running?`} />
        </main>
      ) : (
        <main className="page">
          <Outlet />
        </main>
      )}
    </div>
  );
}
