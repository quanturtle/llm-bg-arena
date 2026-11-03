"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { modelName } from "@/features/new-match/form-model";
import { cn } from "@/lib/utils";

/** A searchable list of the offered models, plus "Another OpenRouter model…" with a text box. */
export function ModelPicker({
  models,
  defaultModel,
  model,
  custom,
  onChoose,
  onType,
  onTyped,
}: {
  models: string[];
  defaultModel: string;
  model: string;
  custom: boolean;
  /** A listed model id, or null for a typed one. */
  onChoose: (model: string | null) => void;
  onType: (model: string) => void;
  /** The typed id is complete: look up what it accepts. */
  onTyped: () => void;
}) {
  const [open, setOpen] = useState(false);
  const typed = custom || !models.includes(model);
  const choose = (value: string | null) => {
    onChoose(value);
    setOpen(false);
  };
  return (
    <div className="flex flex-col gap-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between font-normal">
            <span className="truncate">{typed ? "Another OpenRouter model…" : modelName(model)}</span>
            <ChevronsUpDown className="opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
          <Command>
            <CommandInput placeholder="Search models" />
            <CommandList>
              <CommandEmpty>No listed model matches.</CommandEmpty>
              <CommandGroup>
                {models.map((id) => (
                  <CommandItem key={id} value={id} onSelect={() => choose(id)}>
                    <Check className={cn(!typed && id === model ? "opacity-100" : "opacity-0")} />
                    <span className="truncate">{modelName(id)}</span>
                    {id === defaultModel ? <span className="ml-auto text-xs text-muted-foreground">default</span> : null}
                  </CommandItem>
                ))}
              </CommandGroup>
              <CommandSeparator />
              <CommandGroup>
                <CommandItem value="another openrouter model" onSelect={() => choose(null)}>
                  <Check className={cn(typed ? "opacity-100" : "opacity-0")} />
                  Another OpenRouter model…
                </CommandItem>
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {typed ? (
        <Input
          value={model}
          placeholder="provider/model, for example meta-llama/llama-4-scout"
          onChange={(event) => onType(event.target.value)}
          onBlur={onTyped}
          onKeyDown={(event) => {
            if (event.key === "Enter") onTyped();
          }}
        />
      ) : null}
    </div>
  );
}
