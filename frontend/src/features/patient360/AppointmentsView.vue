<template>
  <section class="appts">
    <header>
      <p>Patient 360</p>
      <h1>Appointments</h1>
    </header>
    <ResourceNotFound v-if="missing" :patient-key="String(route.params.patientId)" />
    <template v-else>
      <ClinicalCard title="Visible on encounters">
        <ul v-if="!loading" class="list">
          <li v-for="row in rows" :key="String(row.cite_id)">
            <strong>{{ statusLabel(row.status) }}</strong>
            <span>{{ practitionerLabel(row.practitioner_user_id) }} · {{ row.dept || 'General' }} · {{ formatWhen(row.started_at) }}<template v-if="row.type_display"> · {{ row.type_display }}</template></span>
          </li>
          <li v-if="!rows.length" class="empty">No booked or pending appointments visible.</li>
        </ul>
      </ClinicalCard>
      <ClinicalCard title="Booked this session">
        <ul class="list">
          <li v-for="item in booked" :key="item.id" class="booked">
            <div>
              <strong>{{ statusLabel(item.status) }}</strong>
              <span>{{ practitionerLabel(item.practitioner_user_id) }} · {{ formatWhen(item.start) }}</span>
            </div>
            <button v-if="item.status !== 'cancelled'" type="button" class="ghost" @click="cancel(item.id)">Cancel</button>
          </li>
          <li v-if="!booked.length" class="empty">No appointments booked in this browser session yet.</li>
        </ul>
      </ClinicalCard>
      <ClinicalCard title="Book a slot">
        <form class="book" @submit.prevent="book">
          <label for="appt-slot">Available slot</label>
          <select id="appt-slot" v-model="start">
            <option disabled value="">Select a slot</option>
            <option v-for="slot in slots" :key="slot.start + slot.practitioner_user_id" :value="slot.start + '|' + slot.practitioner_user_id">
              {{ formatWhen(slot.start) }} · {{ practitionerLabel(slot.practitioner_user_id) }} · {{ slot.department }}
            </option>
          </select>
          <button type="submit" class="primary" :disabled="!start">Book</button>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
        </form>
      </ClinicalCard>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import ResourceNotFound from './ResourceNotFound.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { practitionerName } from '../../services/dashboard';
import { formatLabDate } from '../../services/patientRecord';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import type { Appointment, Slot } from '../../types/api';

const route = useRoute();
const session = useSessionStore();
const rows = ref<Array<Record<string, unknown>>>([]);
const slots = ref<Slot[]>([]);
const booked = ref<Appointment[]>([]);
const start = ref('');
const error = ref('');
const missing = ref(false);

function formatWhen(value: unknown): string {
  if (!value) return '—';
  const text = String(value);
  if (text.includes('T')) {
    const date = formatLabDate(text.slice(0, 10));
    const time = text.slice(11, 16);
    return time ? `${date} · ${time}` : date;
  }
  return formatLabDate(text) || text;
}

function statusLabel(value: unknown): string {
  const raw = String(value || 'unknown');
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function practitionerLabel(value: unknown): string {
  const named = practitionerName(value ? String(value) : undefined, session.personas);
  return named || 'Unassigned';
}

async function load() {
  missing.value = false;
  try {
    const query = await apiClient.query('encounters', { patient_key: String(route.params.patientId) });
    rows.value = query.rows.filter(row => ['booked', 'pending'].includes(String(row.status ?? '')));
  } catch (err) {
    missing.value = err instanceof ApiError && err.notFound;
    rows.value = [];
  }
  slots.value = (await apiClient.availability().catch(() => ({ slots: [], count: 0 }))).slots;
}

async function book() {
  error.value = '';
  const [slotStart, practitioner] = start.value.split('|');
  const slot = slots.value.find(s => s.start === slotStart && s.practitioner_user_id === practitioner);
  try {
    const row = await apiClient.bookAppointment({
      patient_key: String(route.params.patientId),
      practitioner_user_id: practitioner,
      start: slotStart,
      end: slot?.end,
      dept: slot?.department ?? undefined
    });
    booked.value = [row, ...booked.value];
    start.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Booking failed';
  }
}

async function cancel(id: string) {
  try {
    const row = await apiClient.cancelAppointment(id);
    booked.value = booked.value.map(item => item.id === id ? row : item);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Cancel failed';
  }
}

const { loading } = useLiveLoad(load);
</script>

<style scoped>
.appts { display: grid; gap: 20px; max-width: 900px; }
.list { display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; }
.list li { display: grid; gap: 2px; }
.list strong { font-size: 1rem; }
.list span, .empty { color: var(--color-muted); font-size: 14px; }
.booked { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.book { display: grid; gap: 10px; }
.book label { font-size: 13px; font-weight: 700; color: var(--color-muted); text-transform: uppercase; letter-spacing: 0.04em; }
.book select, .book button { min-height: 40px; }
.book select { border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 0 10px; }
.primary, .ghost {
  border-radius: var(--radius-control);
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
  width: max-content;
}
.primary { border: 0; background: var(--color-accent); color: white; }
.primary:disabled { opacity: 0.55; cursor: default; }
.ghost { border: 1px solid var(--color-line); background: var(--color-surface); }
.error { margin: 0; color: var(--color-danger); }
</style>
