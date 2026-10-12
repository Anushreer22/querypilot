import React from "react";
import { HealthStatus } from "./components/HealthStatus";

export const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <HealthStatus />
    </div>
  );
};

export default App;

