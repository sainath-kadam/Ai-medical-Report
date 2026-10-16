import { AxiosError, AxiosHeaders } from 'axios';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const me = vi.fn();
vi.mock('../api/auth.api', () => ({ authApi: { me: () => me() } }));

import { AuthProvider } from './AuthContext';
import { useAuth } from '../hooks/useAuth';
import { queryClient } from '../lib/queryClient';

const PROFILE_KEY = 'radiolens_profile';
const CACHE_KEY = 'radiolens_query_cache';
const user = { id: 'u1', name: 'Dr. Cached', email: 'c@example.com', role: 'doctor' };
const organization = { id: 'o1', name: 'Cached Clinic' };

function Probe() {
  const { user: current, isLoading } = useAuth();
  return <p>{isLoading ? 'loading' : current ? `user:${current.name}` : 'logged-out'}</p>;
}

function renderAuth() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );
}

function unauthorized() {
  return new AxiosError('unauthorized', '401', undefined, undefined, {
    status: 401,
    statusText: 'Unauthorized',
    data: {},
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

describe('AuthProvider on reload', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    queryClient.clear();
  });
  afterEach(() => me.mockReset());

  it('with a token and a saved profile, renders the user immediately -- no wait on /auth/me', () => {
    localStorage.setItem('medscan_access_token', 'token');
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, organization }));
    me.mockReturnValue(new Promise(() => {})); // backend still cold-starting

    renderAuth();

    expect(screen.getByText('user:Dr. Cached')).toBeInTheDocument();
  });

  it('still revalidates in the background and replaces the saved profile', async () => {
    localStorage.setItem('medscan_access_token', 'token');
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, organization }));
    me.mockResolvedValue({ user: { ...user, name: 'Dr. Fresh' }, organization });

    renderAuth();

    expect(await screen.findByText('user:Dr. Fresh')).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(PROFILE_KEY)!).user.name).toBe('Dr. Fresh');
  });

  it('a saved profile without a token is ignored (logged out)', () => {
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, organization }));

    renderAuth();

    expect(screen.getByText('logged-out')).toBeInTheDocument();
    expect(me).not.toHaveBeenCalled();
  });

  it('a 401 from /auth/me logs out and wipes the saved profile and cached pages', async () => {
    localStorage.setItem('medscan_access_token', 'token');
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, organization }));
    sessionStorage.setItem(CACHE_KEY, 'cached patient data');
    queryClient.setQueryData(['patients'], ['p1']);
    me.mockRejectedValue(unauthorized());

    renderAuth();

    expect(await screen.findByText('logged-out')).toBeInTheDocument();
    expect(localStorage.getItem(PROFILE_KEY)).toBeNull();
    expect(sessionStorage.getItem(CACHE_KEY)).toBeNull();
    expect(queryClient.getQueryData(['patients'])).toBeUndefined();
  });

  it('a non-401 error (e.g. backend down) keeps the session', async () => {
    localStorage.setItem('medscan_access_token', 'token');
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ user, organization }));
    me.mockRejectedValue(new Error('Network Error'));

    renderAuth();
    await act(async () => {});

    await waitFor(() => expect(me).toHaveBeenCalled());
    expect(screen.getByText('user:Dr. Cached')).toBeInTheDocument();
    expect(localStorage.getItem(PROFILE_KEY)).not.toBeNull();
  });

  it('without a saved profile (first visit after this change), waits for /auth/me as before', async () => {
    localStorage.setItem('medscan_access_token', 'token');
    me.mockResolvedValue({ user, organization });

    renderAuth();

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(await screen.findByText('user:Dr. Cached')).toBeInTheDocument();
  });
});
