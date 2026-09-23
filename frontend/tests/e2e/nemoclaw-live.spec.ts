import { expect, test } from '@playwright/test';

// Opt in: this creates real, isolated sessions and invokes the local model.
test.skip(process.env.PATIENT360_LIVE_NEMOCLAW !== '1', 'Requires the running Docker and NemoClaw stack');
test.use({ baseURL: process.env.PATIENT360_LIVE_UI_URL ?? 'http://127.0.0.1:4173' });

for (const session of [1, 2]) {
  test(`NemoClaw session ${session}: cold start and repeated cited note summary`, async ({ page }) => {
    test.setTimeout(900_000);
    const patient = process.env.PATIENT360_LIVE_PATIENT_KEY ?? 'p_485ba8c8597d4c5cb0fbda55317119a3';
    try {
      const bootstrap = page.waitForResponse(response => response.url().endsWith('/api/me'));
      await page.goto('/');
      await bootstrap;
      await page.getByLabel('Persona').selectOption('chen');
      await expect(page.getByLabel('Persona')).toBeEnabled();
      await expect(page.locator('.topbar')).toContainText('Dr. Sarah Chen');
      await page.goto(`/patients/${patient}/overview`);
      await page.getByRole('button', { name: 'Ask Patient360', exact: true }).click();
      const panel = page.getByRole('complementary', { name: 'Ask Patient360', exact: true });
      await expect(panel.getByRole('textbox', { name: 'Question', exact: true })).toBeEnabled();
      for (const turn of [1, 2]) {
        await panel.getByRole('textbox', { name: 'Question', exact: true }).fill('Summarize the latest note');
        const started = Date.now();
        const completed = page.waitForResponse(
          response => response.url().endsWith('/api/chat') && response.request().method() === 'POST',
          { timeout: 780_000 }
        );
        await panel.getByRole('button', { name: 'Ask with sources', exact: true }).click();
        const response = await completed;
        expect(response.status()).toBe(200);
        const body = await response.json();
        expect(body.refused).toBe(false);
        expect(body.policy_reason).toBeNull();
        // A direct-model fallback must never count as a healthy NemoClaw turn.
        expect(body.retrievalSteps).toContain('OpenShell sandbox turn');
        expect(body.retrievalSteps).not.toContain('Generated answer with Nemotron');
        expect(body.citations.length).toBeGreaterThan(0);
        expect(body.citations.some((citation: { id: string }) => body.answer.includes(citation.id))).toBe(true);
        await expect(panel.getByRole('region', { name: 'Sources used' }).getByRole('button').first()).toBeVisible();
        await expect(panel.getByText('Assistant unavailable', { exact: true })).toHaveCount(0);
        await expect(panel.getByRole('button', { name: 'Ask with sources', exact: true })).toBeEnabled();
        console.log(`Live NemoClaw session=${session} turn=${turn} elapsed=${((Date.now() - started) / 1000).toFixed(1)}s cited=true`);
      }
    } finally {
      await page.request.post('/api/auth/logout');
    }
  });
}
