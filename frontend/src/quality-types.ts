export interface SchemaField {
  id?: string;
  key: string;
  label: string;
  field_type:
    | "boolean"
    | "single_select"
    | "multi_select"
    | "integer_rating"
    | "continuous_score"
    | "text"
    | "json";
  description: string;
  required: boolean;
  constraints: Record<string, number>;
  options: string[];
  position?: number;
}
export interface AnnotationSchema {
  id: string;
  name: string;
  version: number;
  fields: SchemaField[];
}
export interface QualityRules {
  required_annotations: number;
  required_reviews: number;
  minimum_agreement: number;
  minimum_score: number;
  maximum_variance: number | null;
  minimum_gold_accuracy: number | null;
  minimum_gold_attempts: number;
  gold_every: number;
  auto_escalate_disagreement: boolean;
  reveal_after_completion: boolean;
}
export interface Consensus {
  completed: number;
  required: number;
  conflicting: boolean;
  labels: {
    raw_agreement: number | null;
    disagreement_rate: number | null;
    counts: Record<string, number>;
  };
  scores: {
    mean: number | null;
    median: number | null;
    standard_deviation: number | null;
    variance: number | null;
  };
  fields: Record<string, Record<string, unknown>>;
  kappa_note: string;
  interpretation: string;
}
export interface Review {
  id: string;
  reviewer: string;
  reviewer_id: string;
  round: number;
  decision: string;
  comments: string;
  created_at: string;
  annotation_ids: string[];
}
export interface Escalation {
  id: string;
  task_id: string;
  source: string;
  reason: string;
  status: string;
  resolution: string | null;
  created_at: string;
}
export interface QualityDetail {
  consensus: Consensus;
  policy: QualityRules;
  schema: AnnotationSchema | null;
  reviews: Review[];
  escalations: Escalation[];
}
export interface GateResult {
  id: string;
  eligible: boolean;
  reasons: string[];
  policy: QualityRules;
  evidence: Record<string, unknown>;
}
export interface AnnotatorProfile {
  user_id: string;
  name: string;
  tasks_completed: number;
  median_minutes: number | null;
  agreement_with_others: number | null;
  agreement_samples: number;
  gold_attempted: number;
  gold_accuracy: number | null;
  rolling_gold_accuracy: number | null;
  recent_failures: number;
  rejection_rate: number | null;
  revision_rate: number | null;
  reviewed_tasks: number;
  throughput: { date: string; count: number }[];
  quality_trend: {
    date: string;
    accuracy: number;
    annotation_id: string;
    comparison: Record<string, boolean>;
  }[];
}
export interface QualityDashboard {
  tasks: number;
  pending_reviews: number;
  approval_rate: number | null;
  disagreement_rate: number | null;
  agreement_task_count: number;
  open_escalations: number;
  gold_attempts: number;
  gold_accuracy: number | null;
  annotations_completed: number;
  eligibility_rate: number | null;
  eligibility_evaluated_tasks: number;
  eligibility_note: string;
  cohen_kappa: {
    annotator_ids: string[];
    annotator_names: string[];
    tasks: number;
    kappa: number | null;
  }[];
  fleiss_kappa: {
    raters_per_task: number;
    tasks: number;
    kappa: number | null;
  }[];
  annotators: AnnotatorProfile[];
  filter_basis: string;
}
export interface Dataset {
  id: string;
  name: string;
  description: string;
  created_at: string;
  versions: DatasetVersion[];
  quality_distribution?: Record<string, number>;
  source_projects?: string[];
}
export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version: number;
  status: string;
  created_at: string;
  finalized_at: string | null;
  example_count: number;
  filters: Record<string, unknown>;
  schema_version: string;
  checksum: string | null;
  metadata: Record<string, unknown>;
  examples?: {
    id: string;
    task_id: string;
    external_id: string;
    task_type: string;
    checksum: string;
    gate_result_id: string | null;
  }[];
}
export interface ExamplePreview {
  id: string;
  task_id: string;
  external_id: string;
  project_id: string;
  task_type: string;
  score: number;
  models: string[];
  labels: string[];
  created_at: string;
}
export interface ExportJob {
  id: string;
  version_id: string;
  format: string;
  container: string;
  status: string;
  error: string | null;
  manifest: Record<string, unknown>;
  created_at: string;
}
