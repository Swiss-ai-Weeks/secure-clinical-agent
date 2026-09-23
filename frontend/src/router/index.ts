import { nextTick } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import { useUiStore } from '../stores/useUiStore';

const clinicalRoutes = [
  { path: '/', name: 'home', component: () => import('../features/home/HomeView.vue') },
  { path: '/patients', name: 'patients', component: () => import('../features/patients/PatientsView.vue') },
  { path: '/patients/:patientId/overview', name: 'patient-overview', component: () => import('../features/patient360/PatientOverviewView.vue') },
  { path: '/patients/:patientId/timeline', name: 'patient-timeline', component: () => import('../features/patient360/TimelineView.vue') },
  { path: '/patients/:patientId/labs', name: 'patient-labs', component: () => import('../features/patient360/LabsView.vue') },
  { path: '/patients/:patientId/medications', name: 'patient-medications', component: () => import('../features/patient360/MedicationsView.vue') },
  { path: '/patients/:patientId/appointments', name: 'patient-appointments', component: () => import('../features/patient360/AppointmentsView.vue') },
  { path: '/patients/:patientId/diet', name: 'patient-diet', component: () => import('../features/patient360/DietView.vue') },
  { path: '/patients/:patientId/documents', name: 'patient-documents', component: () => import('../features/patient360/DocumentsView.vue') },
  { path: '/patients/:patientId/notes', name: 'patient-notes', component: () => import('../features/patient360/NotesView.vue') },
  { path: '/patients/:patientId/imaging', name: 'patient-imaging', component: () => import('../features/patient360/ImagingView.vue') },
  { path: '/patients/:patientId/imaging/viewer', name: 'patient-ohif', component: () => import('../features/patient360/OhifView.vue') },
  { path: '/tasks', name: 'tasks', component: () => import('../features/clinic/TasksView.vue') },
  { path: '/redteam', name: 'redteam', component: () => import('../features/clinic/RedTeamView.vue') },
  { path: '/cohort', name: 'cohort', component: () => import('../features/clinic/CohortInsightsView.vue') },
  { path: '/audit', name: 'audit', component: () => import('../features/clinic/AuditPrivacyView.vue') },
  { path: '/portal', name: 'portal', component: () => import('../features/portal/PatientPortalView.vue') }
] as const;

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...clinicalRoutes,
    { path: '/patients/:patientId', redirect: to => `/patients/${to.params.patientId}/overview` }
  ],
  scrollBehavior: () => ({ top: 0 })
});

function withUi(fn: (ui: ReturnType<typeof useUiStore>) => void) {
  try {
    fn(useUiStore());
  } catch {
    // Pinia is not active during isolated router imports.
  }
}

router.beforeEach((to, from) => {
  if (to.path !== from.path || to.name !== from.name) {
    withUi(ui => ui.beginNavigation());
  }
});

router.afterEach(() => {
  withUi(ui => {
    void nextTick(() => ui.endNavigation());
  });
});

router.onError(() => {
  withUi(ui => ui.endNavigation());
});
