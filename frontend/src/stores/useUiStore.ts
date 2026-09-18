import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    askPanelOpen: false,
    selectedPatientId: 'emma-laurent',
    highlightedSourceId: '',
    /** Demo-only: visibility of the temporary access-log panel (see AccessLogPanel.vue). */
    accessLogOpen: false
  }),
  actions: {
    openAskPanel(patientId?: string) {
      if (patientId) this.selectedPatientId = patientId;
      this.askPanelOpen = true;
    },
    closeAskPanel() {
      this.askPanelOpen = false;
    },
    highlightSource(sourceId: string) {
      this.highlightedSourceId = sourceId;
    },
    toggleAccessLog() {
      this.accessLogOpen = !this.accessLogOpen;
    }
  }
});
