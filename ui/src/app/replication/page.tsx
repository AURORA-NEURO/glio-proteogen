import type { Metadata } from "next";
import CohortReplication from "@/components/cohort-replication";

export const metadata: Metadata = {
  title: "Cross-cohort Replication · GLIO Proteogen",
  description: "Research summary-statistic replication, with cohort coverage, heterogeneity, sensitivity analysis, and replayable provenance.",
};

export default function ReplicationPage() {
  return <CohortReplication />;
}
