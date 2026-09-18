<template>
  <section class="appts">
    <header><p>Patient 360</p><h1>Appointments</h1></header>
    <ClinicalCard title="Visible on encounters">
      <p v-if="missing">Resource not found</p>
      <ul v-else>
        <li v-for="row in rows" :key="String(row.cite_id)">{{ row.status }} · {{ row.dept || '—' }} · {{ row.started_at }}</li>
        <li v-if="!rows.length">No booked or pending appointments visible.</li>
      </ul>
    </ClinicalCard>
    <ClinicalCard title="Booked this session">
      <ul>
        <li v-for="item in booked" :key="item.id">
          {{ item.status }} · {{ item.practitioner_user_id }} · {{ item.start }}
          <button v-if="item.status !== 'cancelled'" type="button" @click="cancel(item.id)">Cancel</button>
        </li>
      </ul>
    </ClinicalCard>
    <ClinicalCard title="Book a slot">
      <form class="book" @submit.prevent="book">
        <label>Slot
          <select v-model="start">
            <option disabled value="">Select an opaque slot</option>
            <option v-for="slot in slots" :key="slot.start + slot.practitioner_user_id" :value="slot.start + '|' + slot.practitioner_user_id">
              {{ slot.start }} · {{ slot.practitioner_user_id }} · {{ slot.department }}
            </option>
          </select>
        </label>
        <button type="submit">Book</button>
        <p v-if="error">{{ error }}</p>
      </form>
    </ClinicalCard>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { Appointment, Slot } from '../../types/api';

const route = useRoute();
const rows = ref<Array<Record<string, unknown>>>([]);
const slots = ref<Slot[]>([]);
const booked = ref<Appointment[]>([]);
const start = ref('');
const error = ref('');
const missing = ref(false);

async function load() {
  missing.value = false;
  try {
    const query = await apiClient.query('encounters', { patient_key: String(route.params.patientId) });
    rows.value = query.rows.filter(row => ['booked', 'pending'].includes(String(row.status ?? '')));
  } catch (err) {
    missing.value = err instanceof ApiError && err.notFound;
  }
  slots.value = (await apiClient.availability()).slots;
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

onMounted(load);
</script>

<style scoped>
.appts { display: grid; gap: 20px; max-width: 900px; }.appts header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.book { display: grid; gap: 10px; }.book select, .book button { min-height: 40px; }
</style>
