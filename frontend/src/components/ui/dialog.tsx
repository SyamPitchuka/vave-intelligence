import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  onOpenChange,
  onConfirm,
  children,
  pending,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  children?: ReactNode;
  pending?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-navy-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(32rem,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-line bg-white p-5 shadow-card">
          <Dialog.Title className="text-base font-semibold text-navy-950">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm leading-6 text-muted">{description}</Dialog.Description>
          <div className="mt-4">{children}</div>
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close className="rounded-md border border-line px-3 py-2 text-sm">Cancel</Dialog.Close>
            <button
              type="button"
              className="rounded-md bg-accent-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={onConfirm}
              disabled={pending}
            >
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
