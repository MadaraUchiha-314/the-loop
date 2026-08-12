import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.tsx";
import { ApiProvider } from "./state/ApiContext.tsx";
import "./styles/industry.css";
import "./styles/app.css";

const container = document.querySelector("#root");
if (!container) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <ApiProvider>
      <App />
    </ApiProvider>
  </StrictMode>,
);
