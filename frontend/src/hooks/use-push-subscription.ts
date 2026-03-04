"use client";

import { useCallback, useState } from "react";

type PushPermission = NotificationPermission | "unsupported";

interface PushState {
  supported: boolean;
  permission: PushPermission;
}

function detectInitialState(): PushState {
  if (
    typeof window === "undefined" ||
    !("PushManager" in window) ||
    !("serviceWorker" in navigator)
  ) {
    return { supported: false, permission: "unsupported" };
  }
  return { supported: true, permission: Notification.permission };
}

export function usePushSubscription() {
  // Lazy initializer runs once on mount — no useEffect needed, no cascading renders
  const [state, setState] = useState<PushState>(detectInitialState);

  const subscribe = useCallback(async () => {
    if (!state.supported) return null;

    const perm = await Notification.requestPermission();
    setState((prev) => ({ ...prev, permission: perm }));
    if (perm !== "granted") return null;

    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      // applicationServerKey would go here — not needed for MVP prep
    });

    return subscription;
  }, [state.supported]);

  return { supported: state.supported, permission: state.permission, subscribe };
}
