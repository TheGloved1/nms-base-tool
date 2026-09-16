import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type WithElementRef<T, U = HTMLElement> = T & {
  ref?: U | null;
};

export type WithoutChildren<T> = Omit<T, "children">;
export type WithoutChildrenOrChild<T> = Omit<T, "children" | "child">;
export type WithoutChild<T> = Omit<T, "child">;
