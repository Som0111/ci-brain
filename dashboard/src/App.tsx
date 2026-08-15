import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RepoProvider } from "./lib/RepoContext";
import { Runs } from "./pages/Runs";
import { Flakiness } from "./pages/Flakiness";
import { Impact } from "./pages/Impact";
import { Benchmark } from "./pages/Benchmark";

export default function App() {
  return (
    <RepoProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/runs" replace />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/flakiness" element={<Flakiness />} />
          <Route path="/impact" element={<Impact />} />
          <Route path="/benchmark" element={<Benchmark />} />
        </Route>
      </Routes>
    </RepoProvider>
  );
}
