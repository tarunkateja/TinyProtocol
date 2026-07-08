import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './api';

export function useFamily() {
  const q = useQuery({ queryKey: ['me'], queryFn: api.me });
  return { family: q.data?.family ?? null, ...q };
}

export function useBaby() {
  const q = useQuery({ queryKey: ['babies'], queryFn: api.listBabies });
  return { baby: q.data?.[0] ?? null, ...q };
}

export function useFoods() {
  const q = useQuery({ queryKey: ['foods'], queryFn: api.listFoods });
  return { foods: q.data ?? [], ...q };
}

export function useMedPresets() {
  const q = useQuery({ queryKey: ['medPresets'], queryFn: api.listMedPresets });
  return { presets: q.data ?? [], ...q };
}

/** Invalidate everything that shows logged data after a write. */
export function useInvalidateLogs() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['timeline'] });
    qc.invalidateQueries({ queryKey: ['day'] });
    qc.invalidateQueries({ queryKey: ['summary'] });
  };
}
