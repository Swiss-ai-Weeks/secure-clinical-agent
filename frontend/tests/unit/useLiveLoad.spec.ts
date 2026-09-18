import { defineComponent, nextTick, ref } from 'vue';
import { mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import { useLiveLoad } from '../../src/composables/useLiveLoad';
import { useSessionStore } from '../../src/stores/useSessionStore';

const Dummy = defineComponent({
  setup() {
    const loads = ref(0);
    useLiveLoad(() => {
      loads.value += 1;
    });
    return { loads };
  },
  template: '<div>{{ loads }}</div>'
});

describe('useLiveLoad', () => {
  it('re-runs when the persona or AAL changes', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/patients/:patientId/overview', component: Dummy }]
    });
    await router.push('/patients/p_101/overview');
    await router.isReady();
    const pinia = createPinia();
    const wrapper = mount(Dummy, { global: { plugins: [router, pinia] } });
    const session = useSessionStore();

    expect(wrapper.text()).toBe('1');

    session.me = {
      user_id: 'u_chen',
      display: 'Dr. Sarah Chen',
      role: 'attending',
      department: null,
      credential_level: 2,
      self_patient_id: null,
      datasets: [],
      panels: ['labs'],
      policy_version: 'test',
      session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
    };
    await nextTick();
    expect(wrapper.text()).toBe('2');

    session.me.session.auth_level = 1;
    await nextTick();
    expect(wrapper.text()).toBe('3');
  });
});
