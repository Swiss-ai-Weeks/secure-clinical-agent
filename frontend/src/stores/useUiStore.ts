import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    askPanelOpen: false,
    selectedPatientId: 'p_101',
    highlightedSourceId: ''
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
    }
  }
});
