import { expect, test } from '@playwright/test';

test('signature Patient360 demo flow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await page.locator('select').selectOption('chen');
  await page.getByText('Elisabeth Keller').first().click();

  await expect(page.getByRole('heading', { name: 'Elisabeth Keller' })).toBeVisible();
  await expect(page.getByText('✦ Clinical Brief')).toBeVisible();
  await expect(page.getByText('Since your last consultation')).toBeVisible();

  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page.getByText('HbA1c')).toBeVisible();

  await page.getByRole('button', { name: '✦ Ask Patient360' }).click();
  await page.getByRole('button', { name: 'Ask with sources' }).click();
  await expect(page.getByText('Based on authorized evidence')).toBeVisible();

  await page.getByRole('link', { name: 'Documents' }).click();
  await page.getByLabel('Upload document').setInputFiles({
    name: 'neurology-report.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Follow-up note without identifiers.')
  });
  await expect(page.getByText('neurology-report.txt: processed')).toBeVisible();
});
