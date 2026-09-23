import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', msg => console.log('CONSOLE', msg.type(), msg.text()));
page.on('pageerror', err => console.log('PAGEERROR', err.message));
const response = await page.goto('http://127.0.0.1:4173/', { waitUntil: 'domcontentloaded' });
console.log('status', response?.status(), 'url', page.url(), 'title', await page.title());
await page.waitForTimeout(2500);
console.log('body snippet:', (await page.locator('body').innerText()).slice(0, 1200));
await page.screenshot({ path: '/home/nvidia/Documents/secure-clinical-agent/frontend/tmp-ask-home.png' });
const persona = page.getByLabel('Persona');
console.log('persona count', await persona.count());
if (await persona.count()) {
  console.log('persona options', await persona.locator('option').allTextContents());
  await persona.selectOption('chen');
  await page.waitForTimeout(2500);
  console.log('after chen:', (await page.locator('body').innerText()).slice(0, 1200));
  await page.screenshot({ path: '/home/nvidia/Documents/secure-clinical-agent/frontend/tmp-ask-chen.png' });
}
await browser.close();
