/**
 * Login E2E — the SPA's own JWT handling (no header injection).
 * Covers: guard redirect, register, login, Bearer on API calls, 401 -> login, logout.
 * No story generation here, so no LLM calls.
 */
import { test, expect } from '@playwright/test';

const FRONTEND = process.env.E2E_FRONTEND_URL || 'http://localhost:5173';
const API = process.env.E2E_API_URL || 'http://localhost:8080';
const TOKEN_KEY = 'story-engine.access_token';
const PASSWORD = 'testpassword123';

test('unauthenticated visit redirects to login', async ({ page }) => {
  await page.goto(`${FRONTEND}/library`);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('form', { name: 'Log in' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Library' })).toHaveCount(0);
});

test('register, use the API with a Bearer token, log out, log back in', async ({ page }) => {
  const email = `login-e2e-${Date.now()}@test.com`;
  const authHeaders: string[] = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/v1/stories')) authHeaders.push(req.headers()['authorization'] || '');
  });

  // Register
  await page.goto(`${FRONTEND}/library`);
  await page.getByRole('button', { name: 'Create account' }).first().click();
  const form = page.getByRole('form', { name: 'Create account' });
  await form.getByLabel('Name').fill('Login E2E');
  await form.getByLabel('Email').fill(email);
  await form.getByLabel('Password').fill(PASSWORD);
  await form.getByRole('button', { name: 'Create account' }).click();

  // Back on the page we asked for, with a token sent on the owner-scoped call
  await expect(page).toHaveURL(/\/library$/);
  await expect(page.getByRole('link', { name: 'Library' })).toBeVisible();
  await expect.poll(() => authHeaders.length).toBeGreaterThan(0);
  expect(authHeaders.every((h) => h.startsWith('Bearer '))).toBe(true);
  expect(await page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY)).toBeTruthy();

  // Logout clears the token and returns to login
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY)).toBeNull();

  // Login again: returns to the page the user was on when logged out
  const login = page.getByRole('form', { name: 'Log in' });
  await login.getByLabel('Email').fill(email);
  await login.getByLabel('Password').fill(PASSWORD);
  await login.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/library$/);
  await expect(page.getByRole('link', { name: 'Generate' })).toBeVisible();
});

test('wrong password shows an error and stays on login', async ({ page, request }) => {
  const email = `login-bad-${Date.now()}@test.com`;
  await request.post(`${API}/api/v1/auth/register`, { data: { email, password: PASSWORD, name: 'Bad PW' } });
  await page.goto(`${FRONTEND}/login`);
  const login = page.getByRole('form', { name: 'Log in' });
  await login.getByLabel('Email').fill(email);
  await login.getByLabel('Password').fill('not-the-password');
  await login.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid email or password');
  await expect(page).toHaveURL(/\/login$/);
});

test('an invalid stored token gets a 401 and is sent back to login', async ({ page }) => {
  await page.addInitScript((k) => {
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem(k, 'not-a-valid-jwt');
      sessionStorage.setItem('seeded', '1');
    }
  }, TOKEN_KEY);
  await page.goto(`${FRONTEND}/library`);
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY)).toBeNull();
});
