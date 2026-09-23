import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    askPanelOpen: false,
    askExpandToken: 0,
    selectedPatientId: undefined as string | undefined,
    askDraftQuestion: '',
    highlightedSourceId: '',
    routePending: false,
    pageLoads: 0
  }),
  actions: {
    openAskPanel(patientId?: string, draftQuestion?: string) {
      this.selectedPatientId = patientId;
      this.askDraftQuestion = draftQuestion ?? '';
      this.askPanelOpen = true;
      this.askExpandToken += 1;
    },
    closeAskPanel() {
      this.askPanelOpen = false;
      this.askDraftQuestion = '';
    },
    consumeAskDraft(): string {
      const draft = this.askDraftQuestion;
      this.askDraftQuestion = '';
      return draft;
    },
    highlightSource(sourceId: string) {
      this.highlightedSourceId = sourceId;
    },
    beginNavigation() {
      this.routePending = true;
    },
    endNavigation() {
      this.routePending = false;
    },
    beginPageLoad() {
      this.pageLoads += 1;
    },
    endPageLoad() {
      this.pageLoads = Math.max(0, this.pageLoads - 1);
    }
  }
});
