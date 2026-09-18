import { createRouter, createWebHistory } from 'vue-router';
import RoutePlaceholder from '../features/RoutePlaceholder.vue';

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
  { path: '/tasks', name: 'tasks', component: () => import('../features/clinic/TasksView.vue') },
  { path: '/redteam', name: 'redteam', component: () => import('../features/clinic/RedTeamView.vue') },
  { path: '/threat-model', name: 'threat-model', component: () => import('../features/clinic/ThreatModelView.vue') },
  { path: '/cohort', name: 'cohort', component: () => import('../features/clinic/CohortInsightsView.vue') },
  { path: '/audit', name: 'audit', component: () => import('../features/clinic/AuditPrivacyView.vue') },
  { path: '/portal', name: 'portal', component: () => import('../features/portal/PatientPortalView.vue') }
] as const;

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...clinicalRoutes.map(route => ({
      ...route,
      component: 'component' in route ? route.component : RoutePlaceholder
    })),
    { path: '/patients/:patientId', redirect: to => `/patients/${to.params.patientId}/overview` }
  ],
  scrollBehavior: () => ({ top: 0 })
});
