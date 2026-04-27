export interface Paper {
  id: number;
  title: string;
  abstract: string;
  authors: string[];
  year: number;
  citation_count: number;
  source: string;
  cluster_id: number;
  method?: string;
  dataset?: string;
  task?: string;
  metrics?: string;
  key_contribution?: string;
  future_work?: string;
  limitations?: string;
  pdf_url?: string;
  doi?: string;
  arxiv_id?: string;
  ner_models?: string[];
}

export interface Cluster {
  cluster_id: number;
  label: string;
  paper_count: number;
  paper_ids: number[];
  centroid_2d: [number, number];
  is_noise: boolean;
}

export interface TimelineEntry {
  year: number;
  paper_count: number;
  dominant_methods: string[];
  emerging_methods: string[];
  fading_methods: string[];
  centroid_drift: number;
}

export interface Temporal {
  timeline: TimelineEntry[];
  method_frequency: Record<string, Record<string, number>>;
  paper_counts_per_year: Record<string, number>;
  centroid_drift_per_year: Record<string, number>;
}

export interface ResearchGap {
  rank?: number;
  title: string;
  description: string;
  difficulty?: 'high' | 'medium' | 'low';
  gap_type?: string;
  why_it_matters?: string;
  suggested_methods?: string;
  // legacy fields — kept for backwards compatibility
  priority?: 'high' | 'medium' | 'low';
  evidence?: string;
}

export interface GeometricGap {
  type: string;
  cluster_a: number;
  cluster_b: number;
  label_a: string;
  label_b: string;
  description: string;
  position_2d: [number, number];
}

export interface PipelineResult {
  topic: string;
  metadata: {
    paper_count: number;
    year_range: [number, number];
    cluster_count: number;
    seminal_paper_count: number;
    pipeline_time_seconds: number;
  };
  papers: Paper[];
  clusters: Record<string, Cluster>;
  clustering_metrics: {
    silhouette: number;
    davies_bouldin: number;
    n_clusters: number;
    n_noise: number;
  };
  reduced_2d: [number, number][];
  labels: number[];
  temporal: Temporal;
  seminal_papers: Paper[];    // top-cited papers (no KG needed)
  gaps: {
    synthesized_gaps: ResearchGap[];
    geometric_gaps: GeometricGap[];
    future_sentences: string[];
  };
}

export interface JobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  progress: number;
  current_step: string;
  result?: PipelineResult;
  error?: string;
  topic?: string;
}
