import { createContext, useContext } from "react";
import type { User } from "./types";
export const AppContext = createContext<{
  user: User;
  project: string;
  setProject: (id: string) => void;
  notify: (text: string) => void;
  logout: () => void;
}>(null!);
export const useApp = () => useContext(AppContext);
