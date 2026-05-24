import React, { useState } from "react";
import Dashboard from "./components/Dashboard";
import ScenarioBuilder from "./components/ScenarioBuilder";

export default function App() {
  const [page, setPage] = useState("dashboard");
  return (
    <div className="min-h-screen bg-surface text-ink antialiased">
      {page === "dashboard" && <Dashboard onNavigate={setPage} />}
      {page === "scenarios" && <ScenarioBuilder onNavigate={setPage} />}
    </div>
  );
}
