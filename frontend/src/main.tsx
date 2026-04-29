import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  PublicClientApplication,
  InteractionType,
  type Configuration,
} from "@azure/msal-browser";
import { MsalProvider, MsalAuthenticationTemplate } from "@azure/msal-react";
import "./index.css";
import App from "./App.tsx";
import { MsalAuthBridge, NoAuthProvider } from "./auth/AuthContext.tsx";
import { createLogger } from "./utils/logger";

const log = createLogger("bootstrap");

type AuthConfig = {
  authEnabled: boolean;
  clientId?: string;
  authority?: string;
  apiScopes?: string[];
};

async function bootstrap() {
  log.info(`skillcard frontend booting · build=${__GIT_TAG__ || "dev"} · sha=${__GIT_SHA__}`);
  const root = createRoot(document.getElementById("root")!);

  let authConfig: AuthConfig = { authEnabled: false };
  try {
    const res = await fetch("/api/auth/config");
    if (res.ok) authConfig = await res.json();
  } catch (e) {
    log.warn("Could not fetch auth config — running without auth", e);
  }
  log.info("auth config", { enabled: authConfig.authEnabled });

  if (authConfig.authEnabled && authConfig.clientId && authConfig.authority) {
    const msalConfig: Configuration = {
      auth: {
        clientId: authConfig.clientId,
        authority: authConfig.authority,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
      },
      cache: { cacheLocation: "localStorage" },
    };

    const pca = new PublicClientApplication(msalConfig);
    await pca.initialize();

    // If returning from a redirect, handle it before rendering
    await pca.handleRedirectPromise();

    const apiScopes = authConfig.apiScopes ?? [];

    root.render(
      <StrictMode>
        <MsalProvider instance={pca}>
          <MsalAuthenticationTemplate
            interactionType={InteractionType.Redirect}
            authenticationRequest={{ scopes: apiScopes }}
          >
            <MsalAuthBridge apiScopes={apiScopes}>
              <App />
            </MsalAuthBridge>
          </MsalAuthenticationTemplate>
        </MsalProvider>
      </StrictMode>,
    );
  } else {
    // Auth not configured — render without protection (local dev)
    root.render(
      <StrictMode>
        <NoAuthProvider>
          <App />
        </NoAuthProvider>
      </StrictMode>,
    );
  }
}

bootstrap();
