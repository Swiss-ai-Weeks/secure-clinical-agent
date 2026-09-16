import { expect, test } from '@playwright/test';

test('signature Patient360 demo flow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await page.getByText('Emma Laurent').first().click();

  await expect(page.getByRole('heading', { name: 'Emma Laurent' })).toBeVisible();
  await expect(page.getByText('✦ Clinical Brief')).toBeVisible();
  await expect(page.getByText('Since your last consultation')).toBeVisible();

  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page.getByText('Consultation')).toBeVisible();
  await expect(page.getByText('Patient update')).toBeVisible();
  await expect(page.getByText('Laboratory result')).toBeVisible();

  await page.getByRole('button', { name: '✦ Ask Patient360' }).click();
  await page.getByRole('button', { name: 'Ask with sources' }).click();
  await expect(page.getByText("Emma's migraine pattern changed")).toBeVisible();
  await page.getByRole('button', { name: '12 Sep consultation' }).click();
  await expect(page.getByText('Source highlighted from AI answer')).toBeVisible();

  await page.getByRole('link', { name: 'Documents' }).click();
  await page.getByLabel('Upload document').setInputFiles({
    name: 'neurology-report.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('demo report')
  });
  await expect(page.getByText('Information detected')).toBeVisible();
  await page.getByRole('button', { name: 'Accept' }).first().click();
  await expect(page.getByText('Accepted into review queue')).toBeVisible();
});
