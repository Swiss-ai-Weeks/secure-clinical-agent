import { watch } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/useSessionStore';

/** Re-run a loader when the open patient, persona, or AAL changes. */
export function useLiveLoad(loader: () => void | Promise<void>) {
  const route = useRoute();
  const session = useSessionStore();

  watch(
    () => [
      String(route.params.patientId ?? ''),
      session.me?.user_id ?? '',
      session.me?.session.auth_level ?? 0
    ] as const,
    () => {
      void loader();
    },
    { immediate: true }
  );
}
