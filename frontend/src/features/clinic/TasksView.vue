<template>
  <section class="tasks">
    <header>
      <p>Clinical operations</p>
      <h1>Tasks & follow-ups</h1>
      <span>Derived from visible labs, appointments, and uploads. Nothing is persisted here.</span>
    </header>
    <div v-if="!loading" class="task-list">
      <article v-for="task in tasks" :key="task.id">
        <div>
          <StatusPill :label="task.priority" :tone="task.priority === 'High' ? 'danger' : 'neutral'" />
          <h2>{{ taskLabel(task) }}</h2>
          <p>{{ task.patient }} · due {{ task.dueDate }}</p>
          <small>{{ task.source }}</small>
        </div>
      </article>
      <p v-if="!tasks.length">No follow-ups from visible records.</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { practitionerName } from '../../services/dashboard';
import { useSessionStore } from '../../stores/useSessionStore';
import type { FollowUp } from '../../types/patient360';

const session = useSessionStore();
const tasks = ref<FollowUp[]>([]);

function taskLabel(task: FollowUp): string {
  const doctor = practitionerName(task.clinicianId, session.personas);
  if (!doctor || !task.description.includes('appointment')) return task.description;
  return task.description.replace(' appointment', ` appointment with ${doctor}`);
}

const { loading } = useLiveLoad(async () => {
  tasks.value = await apiClient.getFollowUps().catch(() => []);
});
</script>

<style scoped>
.tasks { display: grid; gap: 20px; max-width: 1000px; }
.tasks header span { color: var(--color-muted); }
.task-list { display: grid; gap: 12px; }
.task-list article { display: flex; justify-content: space-between; gap: 18px; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); padding: 20px; }
.task-list h2 { margin: 10px 0 4px; font-size: 1.15rem; }
.task-list p, .task-list small { color: var(--color-muted); }
.task-list p { margin: 0; }
.task-list small { display: block; margin-top: 6px; }
</style>
