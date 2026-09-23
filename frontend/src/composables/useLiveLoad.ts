import { ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/useSessionStore';
import { useUiStore } from '../stores/useUiStore';

/** Re-run a loader when the open patient, persona, or AAL changes. */
export function useLiveLoad(loader: () => void | Promise<void>) {
  const route = useRoute();
  const session = useSessionStore();
  const ui = useUiStore();
  const loading = ref(true);
  let generation = 0;

  watch(
    () => [
      String(route.params.patientId ?? ''),
      session.me?.user_id ?? '',
      session.me?.session.auth_level ?? 0
    ] as const,
    () => {
      const id = ++generation;
      loading.value = true;
      ui.beginPageLoad();
      let result: void | Promise<void>;
      try {
        result = loader();
      } catch {
        ui.endPageLoad();
        if (id === generation) loading.value = false;
        return;
      }
      if (result && typeof result.then === 'function') {
        void result.finally(() => {
          ui.endPageLoad();
          if (id === generation) loading.value = false;
        });
        return;
      }
      ui.endPageLoad();
      if (id === generation) loading.value = false;
    },
    { immediate: true }
  );

  return { loading };
}
