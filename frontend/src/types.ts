export type Role = "ADMIN" | "ANNOTATOR" | "REVIEWER";
export type Status =
  | "INGESTED"
  | "QUEUED"
  | "ASSIGNED"
  | "ANNOTATED"
  | "PENDING_REVIEW"
  | "APPROVED"
  | "REJECTED";
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  organization_id: string;
}
export interface Project {
  id: string;
  name: string;
  description: string;
  status: string;
  counts: Record<string, number>;
  created_at: string;
}
export interface Annotation {
  id: string;
  label: string;
  score: number;
  feedback: string;
  structured_payload: Record<string, unknown>;
  annotator_id: string;
  assignment_id: string;
}
export interface Assignment {
  id: string;
  task_id: string;
  annotator_id: string;
  status: string;
  assigned_at: string;
  annotation?: Annotation | null;
}
export interface Task {
  id: string;
  external_id: string | null;
  task_type: string;
  status: Status;
  priority: number;
  project_id: string;
  created_at: string;
  updated_at: string;
  input_payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
  annotator?: string;
  project?: Project;
  annotations?: Annotation[];
  assignments?: Assignment[];
}
export interface Step {
  id: string;
  sequence_number: number;
  step_type: string;
  content: string;
  tool_name: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  timestamp: string;
}
export interface Run {
  id: string;
  model_name: string;
  model_version: string;
  started_at: string;
  completed_at: string | null;
  steps: Step[];
}
export interface Audit {
  id: string;
  event_type: string;
  actor: string;
  timestamp: string;
  payload: Record<string, unknown>;
  task_id: string | null;
}
export interface Overview {
  counts: Record<string, number>;
  throughput: { date: string; count: number }[];
  completed_this_week: number;
  queue: { length: number; redis: string; oldest_queued_at: string | null };
  activity: Audit[];
}
export interface TaskPage {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
}
