import { render, screen } from '@testing-library/vue';
import { describe, expect, it } from 'vitest';
import ProvenanceBadge from '../../src/components/ui/ProvenanceBadge.vue';

describe('ProvenanceBadge', () => {
  it('marks AI content with the required symbol', () => {
    render(ProvenanceBadge, { props: { provenance: 'ai-generated' } });

    expect(screen.getByText('✦ AI generated')).toBeInTheDocument();
  });

  it('marks patient-reported content with explicit text', () => {
    render(ProvenanceBadge, { props: { provenance: 'patient-reported' } });

    expect(screen.getByText('Patient reported')).toBeInTheDocument();
  });
});
