import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    askPanelOpen: false,
    selectedPatientId: undefined as string | undefined,
    highlightedSourceId: ''
  }),
  actions: {
    openAskPanel(patientId?: string) {
      this.selectedPatientId = patientId;
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
