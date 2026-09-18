import { describe, expect, it } from 'vitest';
import { router } from '../../src/router';

describe('Patient360 router', () => {
  it('exposes every planned clinical workspace route', () => {
    expect(router.getRoutes().map(route => route.name)).toEqual(
      expect.arrayContaining([
        'home',
        'patients',
        'patient-overview',
        'patient-timeline',
        'patient-labs',
        'patient-medications',
        'patient-appointments',
        'patient-diet',
        'patient-documents',
        'patient-notes',
        'patient-imaging',
        'redteam',
        'threat-model',
        'tasks',
        'cohort',
        'audit',
        'portal'
      ])
    );
  });
});
