"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Removes a match's log and thoughts file after a confirmation; `trigger` replaces the icon button. */
export function DeleteMatchButton({
  matchId,
  onDeleted,
  trigger,
}: {
  matchId: string;
  onDeleted?: () => void;
  trigger?: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.deleteMatch(matchId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["matches"] });
      onDeleted?.();
    },
  });
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        {trigger ?? (
          <Button variant="ghost" size="icon-sm" aria-label="Delete match" title="Delete this match's log and thoughts file">
            <Trash2 />
          </Button>
        )}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete match {matchId}?</AlertDialogTitle>
          <AlertDialogDescription>
            Its log and thoughts file are removed from disk. This cannot be undone.
            {remove.error ? <span className="mt-2 block text-destructive">{remove.error.message}</span> : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={(event) => {
              // keep the dialog open until the delete succeeds or shows its error
              event.preventDefault();
              remove.mutate();
            }}
          >
            Delete for good
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
