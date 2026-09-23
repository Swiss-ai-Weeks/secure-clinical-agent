import { expect, test } from '@playwright/test';

test('signature Patient360 demo flow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await page.locator('select').selectOption('chen');
  await page.getByText('Elisabeth Keller').first().click();

  await expect(page.getByRole('heading', { name: 'Elisabeth Keller' })).toBeVisible();
  await expect(page.getByText('Clinical brief')).toBeVisible();
  await expect(page.getByText('Since your last consultation')).toBeVisible();
  await expect(page.getByText('Grant access')).toBeVisible();

  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page.getByText('HbA1c')).toBeVisible();

  await page.getByRole('button', { name: 'Ask Patient360' }).click();
  await page.getByRole('textbox', { name: 'Question' }).fill('What changed with this patient since the last visit?');
  await page.getByRole('button', { name: 'Ask with sources' }).click();
  await expect(page.getByText(/Wrote a cited summary|NemoClaw was unavailable/)).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();

  await page.getByRole('link', { name: 'Documents' }).click();
  await page.getByLabel('Upload document').setInputFiles({
    name: 'neurology-report.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Follow-up note without identifiers.')
  });
  await expect(page.getByText('neurology-report.txt: processed')).toBeVisible();

  await page.locator('select').selectOption('nair');
  await page.goto('/patients/p_101/overview');
  await expect(page.getByText('Chart not available')).toBeVisible();

  await page.locator('select').selectOption('maria');
  await page.goto('/portal');
  await expect(page.getByRole('heading', { name: /Welcome/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Grant' })).toBeVisible();
  const revoke = page.getByRole('button', { name: 'Revoke' }).first();
  if (await revoke.count()) {
    await revoke.click();
  }
});
