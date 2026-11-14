import type { FormAction, FormState } from "@/features/new-match/form-model";
import { api } from "@/lib/api";

/** Looks a typed model id up once; the seat's settings then follow what the model accepts. */
export function useModelLookup(state: FormState, dispatch: React.Dispatch<FormAction>) {
  return async (model: string) => {
    if (!model || model in state.capabilities || model in state.unknown) {
      dispatch({ type: "modelLookedUp", model, capabilities: null, error: null });
      return;
    }
    try {
      dispatch({ type: "modelLookedUp", model, capabilities: await api.modelCapabilities(model), error: null });
    } catch (error) {
      dispatch({ type: "modelLookedUp", model, capabilities: null, error: error instanceof Error ? error.message : String(error) });
    }
  };
}
