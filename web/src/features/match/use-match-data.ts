"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, type Launch, type LaunchAction } from "@/lib/api";

// a running match and its launch status are re-read this often
export const POLL_MS = 2000;

/** The match outline; polled while the match runs. A failed poll keeps the last outline on screen. */
export function useTimeline(matchId: string) {
  return useQuery({
    queryKey: ["timeline", matchId],
    queryFn: () => api.timeline(matchId),
    refetchInterval: (query) => (query.state.data?.match.status === "running" ? POLL_MS : false),
  });
}

/** The launch of a match this server started, or null; polled while the match runs. */
export function useLaunch(matchId: string, running: boolean) {
  return useQuery({
    queryKey: ["launch", matchId],
    queryFn: () => api.launch(matchId),
    refetchInterval: running ? POLL_MS : false,
  });
}

/** The static geometry of a drawn board, read only for a game whose board uses it. */
export function useLayout(gameId: string, usesLayout: boolean) {
  return useQuery({ queryKey: ["layout", gameId], queryFn: () => api.layout(gameId), enabled: usesLayout, staleTime: Infinity });
}

/** One step's frame. A step never changes once logged, and the previous frame stays shown while the next loads. */
export function useFrame(matchId: string, step: number, last: number) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (step < last) {
      void queryClient.prefetchQuery({
        queryKey: ["frame", matchId, step + 1],
        queryFn: () => api.frame(matchId, step + 1),
        staleTime: Infinity,
      });
    }
  }, [queryClient, matchId, step, last]);
  return useQuery({
    queryKey: ["frame", matchId, step],
    queryFn: () => api.frame(matchId, step),
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });
}

/** Pause, resume or stop a launched match; an older status poll in flight cannot undo it. */
export function useLaunchControl(matchId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: LaunchAction) => api.controlLaunch(matchId, action),
    onMutate: () => queryClient.cancelQueries({ queryKey: ["launch", matchId] }),
    onSuccess: async (launch: Launch) => {
      queryClient.setQueryData(["launch", matchId], launch);
      await queryClient.invalidateQueries({ queryKey: ["timeline", matchId] });
    },
  });
}
