import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { SchemaResponse } from "../../types";

export function useSchema() {
  return useQuery<SchemaResponse>({
    queryKey: ["schema"],
    queryFn: () => api.getSchema(),
    staleTime: 5 * 60 * 1000, // 5 minutes cache
  });
}

