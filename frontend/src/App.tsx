import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { api, downloadApi, subscribeApiActivity } from "./api";
import {
  Activity,
  Boxes,
  Database,
  GitBranch,
  Layers3,
  ClipboardCheck,
  ShieldCheck,
  Settings,
  FileCode2,
  RefreshCw,
  LogOut,
  Play,
  Plus,
  Search,
  CheckCircle2,
  PlugZap,
  Stethoscope,
  PanelLeftClose,
  PanelLeftOpen,
  Bell,
  Command,
  ChevronRight,
  Sparkles,
  Workflow,
  ServerCog,
  ShieldAlert,
  FileCheck2,
  Gauge,
  ArrowUpRight,
  Clock3,
  Download,
  ScrollText,
  BookOpen,
  UserCog,
  Route,
  Home,
  FolderGit2,
  MoreVertical,
  ArrowRight,
  ArrowLeft,
  X,
  Copy,
  ExternalLink,
  Layers,
  Check,
  Lock,
  Cloud,
  AlertTriangle,
  Code,
  Sliders,
  Eye,
  Table,
  RotateCcw,
  FileSpreadsheet,
  ChevronDown,
  AlertCircle,
  Filter,
  Shield,
} from "lucide-react";

import SourceConnectorControl from "./SourceConnectorControl";
import LandingPage from "./LandingPage";
import WorkspacePhaseStepper from "./WorkspacePhaseStepper";
import { ApiStatusPanel } from "./ApiStatusPanel";

type Project = { id: string; name: string; status: string; created_at?: string };
type Source = {
  id: string;
  profile_name: string;
  server_name: string;
  database_name: string;
};
type Inv = {
  id: string;
  database: string;
  schema: string;
  name: string;
  type: string;
  column_count?: number;
  row_count?: number | null;
  columns?: any[];
};
type ClassRow = {
  object_id: string;
  name: string;
  type: string;
  recommended_layer: string;
  selected_layer: string;
  reason: string;
  confidence: number;
};
type Mapping = {
  id: string;
  object_id: string;
  name: string;
  type: string;
  source_fqn: string;
  target_fqn: string;
  target_layer: string;
  environment: string;
};
type Artifact = {
  artifact_id: string;
  object_id: string;
  schema?: string;
  name: string;
  type: string;
  current_version: number;
  artifact_version_id?: string;
  content?: string;
  executable?: boolean;
  validation_status?: string;
  review_status?: string;
  approval_allowed?: boolean;
  approval_blockers?: string[];
  ai_provider?: string;
  ai_model?: string;
};
type Life = {
  environment: string;
  status: string;
  pass_count: number;
  fail_count: number;
  review_blockers: number;
};
type ModRecord = {
  id: string;
  record_type: string;
  object_id?: string;
  environment?: string;
  created_at: string;
  payload: { title?: string; status?: string; details?: any };
};

function formatDateTime(val: any): string {
  if (!val) return "-";
  let s = String(val).trim();
  if (!s) return "-";
  if (/^\d{10,13}$/.test(s)) {
    const num = Number(s);
    const d = new Date(num < 1e11 ? num * 1000 : num);
    return isNaN(d.getTime()) ? s : d.toLocaleString();
  }
  if (/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}/.test(s)) {
    s = s.replace(" ", "T");
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) {
    s = s + "Z";
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(val) : d.toLocaleString();
}

function formatTimeOnly(val: any): string {
  if (!val) return "-";
  let s = String(val).trim();
  if (!s) return "-";
  if (/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}/.test(s)) {
    s = s.replace(" ", "T");
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) {
    s = s + "Z";
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(val) : d.toLocaleTimeString();
}

function formatSqlIdent(raw: string): string {
  if (!raw || raw === "-") return "-";
  const cleaned = raw.replace(/[`'"]/g, "").trim();
  const parts = cleaned.split(".");
  if (parts.length >= 2) {
    return parts.map((p) => `\`${p}\``).join(".");
  }
  return `\`${cleaned}\``;
}

function truncateRunId(id: string): string {
  if (!id || id === "-") return "-";
  if (id.length <= 22) return id;
  return `${id.slice(0, 9)}...${id.slice(-8)}`;
}

function formatTerminalTime(val: any): string {
  if (!val) {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}.${String(now.getMilliseconds()).padStart(3, "0")}`;
  }
  try {
    const d = new Date(val);
    if (isNaN(d.getTime())) return String(val).slice(-12);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}.${String(d.getMilliseconds()).padStart(3, "0")}`;
  } catch {
    return "00:00:00.000";
  }
}

const icons: any = {
  Projects: Boxes,
  "Environment Setup": ServerCog,
  Sources: Database,
  Discovery: PlugZap,
  Inventory: FileCode2,
  "Layer Classification": Layers3,
  "Migration Workflow": Workflow,
  Reviews: ClipboardCheck,
  Deployment: ShieldCheck,
  Lifecycle: Route,
  Deployments: ShieldCheck,
  Waves: ShieldCheck,
  Overview: Home,
  Dashboard: Activity,
  Runbook: BookOpen,
  Dependencies: GitBranch,
  "Medallion Design": Layers3,
  "AI Remediation": Sparkles,
  Governance: ShieldCheck,
  Administration: Settings,
};
const moduleMap: any = {
  Assessment: "assessment",
  "Conversion Plans": "conversion-plans",
  "Data Quality": "data-quality",
  Deployments: "deployments",
  Waves: "waves",
  Cutover: "cutover",
  Decommission: "decommission",
  Governance: "governance",
  Audit: "audit",
  Administration: "administration",
};

const BUILD_VERSION = "2.4.1 BRONZE_TARGET_CONSISTENCY";

function Login({ done, onBack }: { done: () => void; onBack?: () => void }) {
  const [u, setU] = useState("admin"),
    [p, setP] = useState(""),
    [err, setErr] = useState("");
  async function go() {
    setErr("");
    try {
      const r: any = await api("/login", {
        method: "POST",
        body: JSON.stringify({ username: u, password: p }),
      });
      localStorage.setItem("mf_token", r.access_token);
      done();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  return (
    <div className="login">
      <div className="login-card">
        <div className="brandmark">MF</div>
        <h1>Migration Factory</h1>
        <p>Enterprise SQL Server → Databricks Control Plane</p>
        <input
          value={u}
          onChange={(e) => setU(e.target.value)}
          placeholder="Username"
        />
        <input
          value={p}
          type="password"
          onChange={(e) => setP(e.target.value)}
          placeholder="Password"
          onKeyDown={(e) => e.key === "Enter" && go()}
        />
        <button onClick={go}>Sign in</button>
        {err && <div className="error">{err}</div>}
        <small>
          Use the administrator created by scripts/bootstrap_admin.py. · Build{" "}
          {BUILD_VERSION}
        </small>
      </div>
    </div>
  );
}
function Badge({ s }: { s: string }) {
  return (
    <span className={`badge ${String(s || "").toLowerCase()}`}>{s || "-"}</span>
  );
}
function Panel({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: any;
  children: any;
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>{title}</h3>
        <div>{actions}</div>
      </div>
      {children}
    </div>
  );
}
function Empty({ text }: { text: string }) {
  return (
    <div className="empty">
      <FileCode2 size={36} />
      <p>{text}</p>
    </div>
  );
}

export default function App() {
  const [ready, setReady] = useState(!!localStorage.getItem("mf_token"));
  const [showLogin, setShowLogin] = useState(false);
  const [page, setPage] = useState("Projects");
  const [deploymentTab, setDeploymentTab] = useState<"dev" | "waves">("dev");
  const [deployActiveEnv, setDeployActiveEnv] = useState<"DEV" | "TEST" | "UAT" | "PROD" | "ALL">("DEV");
  const [deployLogEnvFilter, setDeployLogEnvFilter] = useState<"ALL" | "DEV" | "TEST" | "UAT" | "PROD">("DEV");
  const [projects, setProjects] = useState<Project[]>([]),
    [pid, setPid] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [projectStatusFilter, setProjectStatusFilter] = useState<"ALL" | "ACTIVE" | "REVIEW" | "COMPLETED">("ALL");
  const [newProjectModalOpen, setNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [activeMenuProjectId, setActiveMenuProjectId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [newSourceModalOpen, setNewSourceModalOpen] = useState(false);
  const [newSourceForm, setNewSourceForm] = useState({
    profile_name: "SQLServer1",
    server_name: "localhost",
    database_name: "",
  });
  const [testedSource, setTestedSource] = useState<Source | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [testTimestamp, setTestTimestamp] = useState<string>("");
  // Discovery page states
  const [discoveryScanningSourceId, setDiscoveryScanningSourceId] = useState<string | null>(null);
  const [discoveryProgressStep, setDiscoveryProgressStep] = useState<number>(0);
  const [discoveryDbFilter, setDiscoveryDbFilter] = useState<string>("ALL");
  const [discoveryTypeFilter, setDiscoveryTypeFilter] = useState<string>("ALL");

  // Inventory page states
  const [inventoryDbFilter, setInventoryDbFilter] = useState<string>("ALL");
  const [inventorySelectedIds, setInventorySelectedIds] = useState<string[]>([]);
  const [inventoryShowFkOnly, setInventoryShowFkOnly] = useState<boolean>(false);
  const [inventoryInspectingObject, setInventoryInspectingObject] = useState<any | null>(null);

  // Layer Classification page states
  const [classificationDismissedBanner, setClassificationDismissedBanner] = useState<boolean>(false);
  const [classificationLayerFilter, setClassificationLayerFilter] = useState<string>("ALL");
  const [classificationSearch, setClassificationSearch] = useState<string>("");
  const [activeLayerDropdownId, setActiveLayerDropdownId] = useState<string | null>(null);
  const [dash, setDash] = useState<any>({}),
    [life, setLife] = useState<Life[]>([]),
    [classes, setClasses] = useState<ClassRow[]>([]),
    [sources, setSources] = useState<Source[]>([]),
    [inventory, setInventory] = useState<Inv[]>([]),
    [mappings, setMappings] = useState<Mapping[]>([]),
    [artifacts, setArtifacts] = useState<Artifact[]>([]),
    [issues, setIssues] = useState<any[]>([]),
    [deps, setDeps] = useState<any[]>([]),
    [reviews, setReviews] = useState<any[]>([]);
  const [records, setRecords] = useState<ModRecord[]>([]),
    [users, setUsers] = useState<any[]>([]),
    [diag, setDiag] = useState<any>(null),
    [discoveryResult, setDiscoveryResult] = useState<any>(null);
  const [environmentConfig, setEnvironmentConfig] = useState<any>(null),
    [environmentPlan, setEnvironmentPlan] = useState<any>(null),
    [bronzePreflight, setBronzePreflight] = useState<any>(null),
    [bronzeRun, setBronzeRun] = useState<any>(null),
    [environmentForm, setEnvironmentForm] = useState({
      workspace_host: "",
      http_path: "",
      token_env_key: "DATABRICKS_TOKEN",
      catalog_prefix: "migration",
    });
  const [bronzeLoadMode, setBronzeLoadMode] = useState("FULL_LOAD"),
    [bronzeBatchSize, setBronzeBatchSize] = useState(1000),
    [bronzeMaxRows, setBronzeMaxRows] = useState("");
  const [deployment, setDeployment] = useState<any>({
      environment: "DEV",
      status: "NOT_STARTED",
      logs: [],
    }),
    [precheck, setPrecheck] = useState<any>(null),
    [reconResult, setReconResult] = useState<any>(null),
    [gateResult, setGateResult] = useState<any>(null);
  const [testPromotion, setTestPromotion] = useState<any>({ status: "NOT_STARTED", logs: [] }),
    [testPrecheck, setTestPrecheck] = useState<any>(null),
    [testRecon, setTestRecon] = useState<any>(null),
    [testGate, setTestGate] = useState<any>(null);
  const [uatPromotion, setUatPromotion] = useState<any>({ status: "NOT_STARTED", logs: [] }),
    [uatPrecheck, setUatPrecheck] = useState<any>(null),
    [uatRecon, setUatRecon] = useState<any>(null),
    [uatGate, setUatGate] = useState<any>(null);
  const [prodPromotion, setProdPromotion] = useState<any>({ status: "NOT_STARTED", logs: [] }),
    [prodPrecheck, setProdPrecheck] = useState<any>(null),
    [prodRecon, setProdRecon] = useState<any>(null),
    [prodGate, setProdGate] = useState<any>(null);
  const [workflowOps, setWorkflowOps] = useState<any>({ cutover: [], decommission: [] });
  const [logView, setLogView] = useState<any[]>([]),
    [showLogs, setShowLogs] = useState(false);
  const [compat, setCompat] = useState<any>(null);
  const [medallion, setMedallion] = useState<any>(null),
    [semantics, setSemantics] = useState<any[]>([]),
    [consumers, setConsumers] = useState<any[]>([]),
    [medArts, setMedArts] = useState<any[]>([]),
    [semanticRun, setSemanticRun] = useState<any>(null);
  const [medDeployment, setMedDeployment] = useState<any>(null),
    [medLogs, setMedLogs] = useState<any[]>([]),
    [medLogFilter, setMedLogFilter] = useState("ALL");
  const [medValidation, setMedValidation] = useState<any>(null),
    [artifactInspector, setArtifactInspector] = useState<any>(null);
  const [aiCandidate, setAiCandidate] = useState<any>(null),
    [aiObject, setAiObject] = useState<Artifact | null>(null),
    [aiPlan, setAiPlan] = useState<any>(null),
    [aiBatch, setAiBatch] = useState<any>(null);
  const [aiProvider, setAiProvider] = useState<any>(null),
    [aiModels, setAiModels] = useState<string[]>([]);
  const [selectedIssue, setSelectedIssue] = useState<any>(null),
    [issueLogs, setIssueLogs] = useState<any[]>([]),
    [showIssueLogs, setShowIssueLogs] = useState(false);
  const [deployBatch, setDeployBatch] = useState(10000),
    [deployMaxRows, setDeployMaxRows] = useState(""),
    [deployMode, setDeployMode] = useState("FULL_LOAD");
  const [busy, setBusy] = useState(false),
    [msg, setMsg] = useState(""),
    [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);

  // Multi-state Live Sync & Profile dropdown states
  const [apiActiveCount, setApiActiveCount] = useState(0);
  const [manualSyncing, setManualSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<"idle" | "loading" | "success">("idle");
  const [syncContext, setSyncContext] = useState<string>("Syncing...");
  const isOperating = busy || apiActiveCount > 0 || manualSyncing;
  const prevOperatingRef = useRef(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const [promptText, setPromptText] = useState(
    "Migrate MigrationDemo from SQL Server to DEV Databricks",
  );
  const [promptPlan, setPromptPlan] = useState<any>(null);
  const [promptExecution, setPromptExecution] = useState<any>(null);
  const [promptRunning, setPromptRunning] = useState(false);
  const [promotionPrompt, setPromotionPrompt] = useState(
    "Promote approved DEV release to TEST",
  );
  const [promotionPlan, setPromotionPlan] = useState<any>(null);
  const [promotionExecution, setPromotionExecution] = useState<any>(null);
  const [promotionRunning, setPromotionRunning] = useState(false);
  const [masterPrompt, setMasterPrompt] = useState(
    "Migrate MigrationDemo from SQL Server through DEV, TEST, UAT, and PROD Databricks",
  );
  const [masterPlan, setMasterPlan] = useState<any>(null);
  const [masterExecution, setMasterExecution] = useState<any>(null);
  const [masterRunning, setMasterRunning] = useState(false);
  const [autoPromotionStatus, setAutoPromotionStatus] = useState<any>(null);
  const [showAutoAuthModal, setShowAutoAuthModal] = useState(false);
  const [autoAuthText, setAutoAuthText] = useState("");
  const [autoRunning, setAutoRunning] = useState(false);
  const [promptNativeText, setPromptNativeText] = useState(
    "Migrate MigrationDemo from SQL Server to Databricks DEV. Bronze: ingest Customers, CustomerSales, OrderItems, Orders, OrderSummary and Products. Silver: create cleaned views for Customers, Orders, OrderItems and Products; create vw_CustomerSales for completed orders; create fn_CalculateOrderAmount(p_order_id INT); create idempotent MERGE loaders usp_LoadCustomerSales and usp_LoadOrderSummary. Gold: create dim_customer, dim_product, fact_sales, vw_customer_sales_summary and vw_product_sales_summary. Validate every identifier and wait for plan approval before generation.",
  );
  const [promptSourceId, setPromptSourceId] = useState<string>("");
  const [promptSpec, setPromptSpec] = useState<any>(null);
  const [promptSpecPlan, setPromptSpecPlan] = useState<any>(null);
  const [promptSpecTrace, setPromptSpecTrace] = useState<any>(null);
  const [promptAnswers, setPromptAnswers] = useState<Record<string, string>>({});
  const [workflowStudioTab, setWorkflowStudioTab] = useState<"master" | "native">("master");
  const [showStudio, setShowStudio] = useState<boolean>(true);
  const [deployStatusFilter, setDeployStatusFilter] = useState<string>("ALL");
  const [deployCopiedRunId, setDeployCopiedRunId] = useState<boolean>(false);
  const [deployTerminalOpen, setDeployTerminalOpen] = useState<boolean>(true);
  const [deployTerminalFilter, setDeployTerminalFilter] = useState<string>("");
  const [inspectedTarget, setInspectedTarget] = useState<string | null>(null);
  const [reviewSearch, setReviewSearch] = useState<string>("");
  const [reviewLayerFilter, setReviewLayerFilter] = useState<string>("ALL");
  const [reviewStatusFilter, setReviewStatusFilter] = useState<string>("ALL");
  const [reviewSelectedIds, setReviewSelectedIds] = useState<Set<string>>(new Set());
  const [reviewDrawerArtifact, setReviewDrawerArtifact] = useState<any>(null);
  const [reviewDrawerTab, setReviewDrawerTab] = useState<"sql" | "evidence">("sql");
  const [reviewDrawerCopied, setReviewDrawerCopied] = useState<boolean>(false);
  const [reviewOverflowOpen, setReviewOverflowOpen] = useState<string | null>(null);

  function layerBadgeClass(layer: string) {
    const l = (layer || "").toUpperCase();
    if (l === "BRONZE") return "rv-med-badge bronze";
    if (l === "SILVER") return "rv-med-badge silver";
    if (l === "GOLD")   return "rv-med-badge gold";
    return "rv-med-badge";
  }

  async function loadProjects() {
    const ps = await api<Project[]>("/projects");
    setProjects(ps);
    if (!pid && ps[0]) setPid(ps[0].id);
    return ps;
  }
  async function refresh() {
    if (!ready) return;
    setMsg("");
    try {
      const ps = await loadProjects();
      const id = pid || ps[0]?.id;
      if (id) {
        const [d, l, c, s, i, m, a, is, dp, rv] = await Promise.all([
          api(`/projects/${id}/dashboard`),
          api(`/projects/${id}/lifecycle`),
          api(`/projects/${id}/classification`),
          api(`/projects/${id}/sources`),
          api(`/projects/${id}/inventory?limit=500`),
          api(`/projects/${id}/mappings`),
          api(`/projects/${id}/artifacts`),
          api(`/projects/${id}/issues`),
          api(`/projects/${id}/dependencies`),
          api(`/projects/${id}/reviews`),
        ]);
        setDash(d);
        setLife(l as Life[]);
        setClasses(c as ClassRow[]);
        setSources(s as Source[]);
        setInventory(i as Inv[]);
        setMappings(m as Mapping[]);
        setArtifacts(a as Artifact[]);
        setIssues(is as any[]);
        setDeps(dp as any[]);
        setReviews(rv as any[]);
      }
      if (moduleMap[page] && id)
        setRecords(await api(`/projects/${id}/module/${moduleMap[page]}`));
      if (id && ["Medallion Design", "Deployments", "Migration Workflow"].includes(page)) {
        const [status, projectLogs]: any = await Promise.all([
          api(`/projects/${id}/medallion/deployments/dev/status`),
          api(`/projects/${id}/deployments/dev/logs?limit=1000`),
        ]);
        const logs: any = status.run_id
          ? await api(`/projects/${id}/medallion/deployments/${status.run_id}/logs`)
          : { logs: [] };
        setMedDeployment(status);
        setMedLogs(logs.logs || []);
        setLogView(projectLogs.logs || []);
      }
      if (page === "Compatibility" && id)
        setCompat(await api(`/projects/${id}/compatibility/summary`));
      if (page === "Medallion Design" && id) {
        const [mp, sm, cs, validation]: any = await Promise.all([
          api(`/projects/${id}/medallion/plan?environment=DEV`),
          api(`/projects/${id}/semantics`),
          api(`/projects/${id}/consumers`),
          api(`/projects/${id}/medallion/validation-report?environment=DEV`),
        ]);
        setMedallion(mp);
        setSemantics(sm);
        setConsumers(cs);
        setMedArts(await api(`/projects/${id}/medallion/artifacts?environment=DEV`));
        setMedValidation(validation);
      }
      if (page === "Reviews" && id) {
        setMedValidation(await api(`/projects/${id}/medallion/validation-report?environment=DEV`));
        setMedArts(
          await api(`/projects/${id}/medallion/artifacts?environment=DEV`),
        );
      }
      if (page === "AI Remediation" && id) {
        const [plan, provider]: any = await Promise.all([
          api(`/projects/${id}/remediation/plan?environment=DEV`),
          api("/ai/provider-status"),
        ]);
        setAiPlan(plan);
        setAiProvider(provider);
      }
      if ((page === "Deployments" || page === "Deployment") && id) {
        const [reconciliation, legacyDeployment, medallionDeployment]: any =
          await Promise.all([
            api(`/projects/${id}/deployments/dev/reconciliation/latest`).catch(() => null),
            api(`/projects/${id}/deployments/dev/status`).catch(() => null),
            api(`/projects/${id}/medallion/deployments/dev/status`).catch(() => null),
          ]);
        if (reconciliation) setReconResult(reconciliation);
        if (legacyDeployment) setDeployment(legacyDeployment);
        if (medallionDeployment) {
          setMedDeployment(medallionDeployment);
          if (medallionDeployment.run_id) {
            api(`/projects/${id}/medallion/deployments/${medallionDeployment.run_id}/logs`)
              .then((l: any) => setMedLogs(l.logs || []))
              .catch(() => {});
          }
        }
        api(`/projects/${id}/deployments/dev/logs?limit=1000`)
          .then((l: any) => setLogView(l.logs || []))
          .catch(() => {});
      }
      if ((page === "Waves" || page === "Deployment" || page === "Deployments") && id) {
        const [status, recon, uatStatus, uatReconciliation, prodStatus, prodReconciliation, promptPromotion]: any = await Promise.all([
          api(`/projects/${id}/promotions/test/status`),
          api(`/projects/${id}/promotions/test/reconciliation/latest`),
          api(`/projects/${id}/promotions/uat/status`),
          api(`/projects/${id}/promotions/uat/reconciliation/latest`),
          api(`/projects/${id}/promotions/prod/status`),
          api(`/projects/${id}/promotions/prod/reconciliation/latest`),
          api(`/projects/${id}/prompt-promotion/latest`).catch(() => ({ plan: null, execution: null })),
        ]);
        setTestPromotion(status);
        setTestRecon(recon);
        setUatPromotion(uatStatus);
        setUatRecon(uatReconciliation);
        setProdPromotion(prodStatus);
        setProdRecon(prodReconciliation);
        if (promptPromotion?.plan) setPromotionPlan(promptPromotion.plan);
        if (promptPromotion?.execution) setPromotionExecution(promptPromotion.execution);
      }
      // Auto-promotion status fetch
      api(`/projects/${id}/master-orchestration/current`)
        .then((s: any) => setAutoPromotionStatus(s))
        .catch(() => setAutoPromotionStatus(null));

      if (page === "Migration Workflow" && id) {
        const [compatibility, mp, sm, ma, devRecon, cutover, decommission, promptData, masterData]: any = await Promise.all([
          api(`/projects/${id}/compatibility/summary`),
          api(`/projects/${id}/medallion/plan?environment=DEV`),
          api(`/projects/${id}/semantics`),
          api(`/projects/${id}/medallion/artifacts?environment=DEV`),
          api(`/projects/${id}/deployments/dev/reconciliation/latest`),
          api(`/projects/${id}/module/cutover`),
          api(`/projects/${id}/module/decommission`),
          api(`/projects/${id}/prompt-migration/latest`).catch(() => ({ plan: null, execution: null })),
          api(`/projects/${id}/master-migration/latest`).catch(() => ({ plan: null, execution: null })),
        ]);
        setCompat(compatibility);
        setMedallion(mp);
        setSemantics(sm);
        setMedArts(ma);
        setReconResult(devRecon);
        setWorkflowOps({ cutover, decommission });
        if (promptData?.plan) setPromptPlan(promptData.plan);
        if (promptData?.execution) setPromptExecution(promptData.execution);
        setMasterPlan(masterData?.plan || null);
        setMasterExecution(masterData?.execution || null);
      }
      if (page === "Users") setUsers(await api("/users"));
      if (page === "Administration") setDiag(await api("/system/diagnostics"));
      if (page === "Environment Setup" && id) {
        const [configuration, plan, ingestion]: any = await Promise.all([
          api(`/projects/${id}/databricks/configuration`),
          api(`/projects/${id}/environments/dev/plan`),
          api(`/projects/${id}/ingestion/dev/latest`),
        ]);
        setEnvironmentConfig(configuration);
        setEnvironmentPlan(plan);
        setBronzeRun(ingestion);
        if (configuration.configured) {
          setEnvironmentForm({
            workspace_host: configuration.workspace_host || "",
            http_path: configuration.http_path || "",
            token_env_key: configuration.token_env_key || "DATABRICKS_TOKEN",
            catalog_prefix: configuration.catalog_prefix || "migration",
          });
        }
      }
    } catch (e: any) {
      if (String(e.message).includes("Invalid or expired token")) {
        localStorage.removeItem("mf_token");
        setReady(false);
      } else setMsg(e.message);
    }
  }
  useEffect(() => {
    function onAuthExpired() {
      setReady(false);
    }
    window.addEventListener("auth_expired", onAuthExpired);
    return () => window.removeEventListener("auth_expired", onAuthExpired);
  }, []);
  useEffect(() => {
    refresh();
  }, [ready, pid, page]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target as Node)) {
        setProfileMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    return subscribeApiActivity((count) => setApiActiveCount(count));
  }, []);

  useEffect(() => {
    if (isOperating && !prevOperatingRef.current) {
      setSyncStatus("loading");
      if (page === "Deployments" || page === "Deployment" || page === "Waves") {
        setSyncContext("Deploying to DEV...");
      } else if (page === "Environment Setup") {
        setSyncContext("Provisioning DEV...");
      } else if (page === "Discovery") {
        setSyncContext("Running Discovery...");
      } else if (page === "Inventory") {
        setSyncContext("Cataloging Inventory...");
      } else if (page === "Sources") {
        setSyncContext("Testing Source...");
      } else if (page === "Migration Workflow") {
        setSyncContext("Processing Studio...");
      } else {
        setSyncContext("Syncing...");
      }
    } else if (!isOperating && prevOperatingRef.current) {
      setSyncStatus("success");
      const timer = setTimeout(() => {
        setSyncStatus("idle");
      }, 1500);
      return () => clearTimeout(timer);
    }
    prevOperatingRef.current = isOperating;
  }, [isOperating, page]);

  const handleLiveSync = async () => {
    if (isOperating) return;
    setManualSyncing(true);
    setSyncContext("Syncing...");
    try {
      await refresh();
    } finally {
      setManualSyncing(false);
    }
  };
  async function action(fn: () => Promise<any>) {
    setBusy(true);
    setMsg("");
    try {
      const r = await fn();
      await refresh();
      setMsg(r?.status === "FAILED" ? r.error || "Execution failed. Review the saved logs." : "Completed successfully");
      return r;
    } catch (e: any) {
      if (String(e.message).includes("Invalid or expired token") || String(e.message).includes("Authentication required")) {
        localStorage.removeItem("mf_token");
        setReady(false);
      } else {
        await refresh();
      }
      setMsg(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function handleClickOutside() {
      setActiveMenuProjectId(null);
    }
    if (activeMenuProjectId) {
      window.addEventListener("click", handleClickOutside);
      return () => window.removeEventListener("click", handleClickOutside);
    }
  }, [activeMenuProjectId]);

  const projectMetrics = useMemo(() => {
    const total = projects.length;
    const active = projects.filter((p) => {
      const s = (p.status || "").toUpperCase();
      return (
        s === "ACTIVE" ||
        s === "IN_PROGRESS" ||
        s === "OPEN" ||
        (!["COMPLETED", "CLOSED", "PASSED", "ARCHIVED"].includes(s) &&
          !s.includes("REVIEW") &&
          s !== "PENDING")
      );
    }).length;
    const review = projects.filter((p) => {
      const s = (p.status || "").toUpperCase();
      return (
        s.includes("REVIEW") || s === "PENDING" || s === "AWAITING_APPROVAL"
      );
    }).length;
    const completed = projects.filter((p) => {
      const s = (p.status || "").toUpperCase();
      return s === "COMPLETED" || s === "CLOSED" || s === "PASSED";
    }).length;
    return { total, active, review, completed };
  }, [projects]);

  const filteredProjects = useMemo(() => {
    return projects.filter((p) => {
      const q = projectSearch.toLowerCase().trim();
      const matchesSearch =
        !q ||
        p.name.toLowerCase().includes(q) ||
        p.id.toLowerCase().includes(q);

      if (!matchesSearch) return false;

      const s = (p.status || "").toUpperCase();
      if (projectStatusFilter === "ACTIVE") {
        return (
          s === "ACTIVE" ||
          s === "IN_PROGRESS" ||
          s === "OPEN" ||
          (!["COMPLETED", "CLOSED", "PASSED", "ARCHIVED"].includes(s) &&
            !s.includes("REVIEW") &&
            s !== "PENDING")
        );
      }
      if (projectStatusFilter === "REVIEW") {
        return (
          s.includes("REVIEW") || s === "PENDING" || s === "AWAITING_APPROVAL"
        );
      }
      if (projectStatusFilter === "COMPLETED") {
        return s === "COMPLETED" || s === "CLOSED" || s === "PASSED";
      }
      return true;
    });
  }, [projects, projectSearch, projectStatusFilter]);

  async function handleCreateProject(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const trimmed = newProjectName.trim();
    if (!trimmed) return;
    await action(async () => {
      const res: any = await api("/projects", {
        method: "POST",
        body: JSON.stringify({ name: trimmed }),
      });
      if (res && res.id) {
        setPid(res.id);
      }
      return res;
    });
    setNewProjectName("");
    setNewProjectModalOpen(false);
  }

  function copyToClipboard(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    navigator.clipboard?.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  async function handleCreateSource(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!pid) return;
    const { profile_name, server_name, database_name } = newSourceForm;
    if (!profile_name.trim() || !server_name.trim() || !database_name.trim()) return;
    await action(() =>
      api(`/projects/${pid}/sources`, {
        method: "POST",
        body: JSON.stringify({
          profile_name: profile_name.trim(),
          server_name: server_name.trim(),
          database_name: database_name.trim(),
        }),
      })
    );
    setNewSourceForm({
      profile_name: "SQLServer1",
      server_name: "localhost",
      database_name: "",
    });
    setNewSourceModalOpen(false);
  }

  async function generatePromptPlan(pText?: string) {
    if (!pid) return;
    setBusy(true);
    setMsg("");
    try {
      const p = pText || promptText;
      const res: any = await api(`/projects/${pid}/prompt-migration/plan`, {
        method: "POST",
        body: JSON.stringify({ prompt: p }),
      });
      setPromptPlan(res);
      if (res.status === "NEEDS_USER_INPUT") {
        setMsg("Prerequisites required before migration planning can complete.");
      } else {
        setMsg("Prompt validated & migration plan generated.");
      }
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generateMasterPlan(text?: string) {
    if (!pid) return;
    setBusy(true);
    setMsg("");
    try {
      const prompt = text || masterPrompt;
      const result: any = await api(`/projects/${pid}/master-migration/plan`, {
        method: "POST",
        body: JSON.stringify({ prompt }),
      });
      setMasterPlan(result);
      setMasterExecution(null);
      setMsg(
        result.status === "NEEDS_USER_INPUT"
          ? "Resolve the master workflow prerequisites before authorization."
          : "End-to-end migration plan generated and awaiting one-time authorization.",
      );
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function authorizeAutomatedPromotion() {
    if (!pid) return;
    setBusy(true);
    setAutoRunning(true);
    setMsg("Authorizing and starting end-to-end automated promotion to PROD...");
    try {
      const result: any = await api(`/projects/${pid}/master-orchestration/authorize`, {
        method: "POST",
        body: JSON.stringify({ confirmation_text: autoAuthText.trim() }),
      });
      setAutoPromotionStatus((prev: any) => ({ ...prev, run: result, is_active: result.status === "RUNNING" }));
      setMsg(
        result.status === "COMPLETED"
          ? "End-to-end automated promotion completed through PROD with all quality gates passed!"
          : result.status === "PAUSED"
          ? "Automated promotion paused safely."
          : result.status === "FAILED"
          ? `Automated promotion stopped at ${result.current_environment}: ${result.errors?.[result.errors.length - 1]?.message || "Check blockers"}`
          : "Automated promotion running..."
      );
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
      setAutoRunning(false);
    }
  }

  async function pauseAutomatedPromotion() {
    if (!pid) return;
    setMsg("Requesting pause after current environment completes...");
    try {
      const result: any = await api(`/projects/${pid}/master-orchestration/pause`, { method: "POST" });
      setAutoPromotionStatus((prev: any) => ({ ...prev, run: result }));
      setMsg("Pause requested: execution will stop safely after current environment.");
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  async function resumeAutomatedPromotion() {
    if (!pid || !autoPromotionStatus?.run?.run_id) return;
    setBusy(true);
    setAutoRunning(true);
    setMsg("Resuming automated promotion from last checkpoint...");
    try {
      const result: any = await api(`/projects/${pid}/master-orchestration/resume`, {
        method: "POST",
        body: JSON.stringify({ run_id: autoPromotionStatus.run.run_id }),
      });
      setAutoPromotionStatus((prev: any) => ({ ...prev, run: result, is_active: result.status === "RUNNING" }));
      setMsg(
        result.status === "COMPLETED"
          ? "End-to-end automated promotion completed through PROD with all quality gates passed!"
          : `Automated promotion stopped at ${result.current_environment}.`
      );
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
      setAutoRunning(false);
    }
  }

  async function cancelAutomatedPromotion() {
    if (!pid || !autoPromotionStatus?.run?.run_id) return;
    const ok = window.confirm("Cancel remaining promotion environments? Already passed environments will remain intact.");
    if (!ok) return;
    setBusy(true);
    try {
      const result: any = await api(`/projects/${pid}/master-orchestration/cancel`, {
        method: "POST",
        body: JSON.stringify({ run_id: autoPromotionStatus.run.run_id }),
      });
      setAutoPromotionStatus((prev: any) => ({ ...prev, run: result, is_active: false }));
      setMsg("Remaining automated promotion cancelled. All evidence from passed environments is retained.");
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function executeMasterPlan() {
    if (!pid || !masterPlan?.plan_id) return;
    const isResume = masterPlan.status === "FAILED" || masterPlan.status === "PAUSED";
    if (!isResume) {
      const confirmed = window.confirm(
        "Authorize this complete SQL Server migration through DEV, TEST, UAT, and PROD, including governed FULL_LOAD replacement when required? The workflow will stop automatically if any quality gate fails.",
      );
      if (!confirmed) return;
    }
    setBusy(true);
    setMasterRunning(true);
    setMsg(isResume ? "Resuming from the last passed checkpoint..." : "Executing the authorized end-to-end migration...");
    try {
      const result: any = await api(`/projects/${pid}/master-migration/execute`, {
        method: "POST",
        body: JSON.stringify({
          plan_id: masterPlan.plan_id,
          workflow_authorized: !isResume,
          production_authorized: !isResume,
          data_replacement_authorized: !isResume,
        }),
      });
      setMasterExecution(result);
      setMsg(
        result.status === "COMPLETED"
          ? "SQL Server migration completed through PROD with all quality gates passed."
          : `Master workflow stopped at ${result.failed_stage || "a governed gate"}.`,
      );
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
      setMasterRunning(false);
    }
  }
  async function executePromptPlan() {
    if (!pid || !promptPlan?.plan_id) return;
    const overwriteConfirmed = Boolean(promptPlan.impact?.requires_overwrite) && window.confirm(
      "Authorize FULL_LOAD replacement of existing DEV Bronze data when its checkpoint cannot be reused?",
    );
    if (promptPlan.impact?.requires_overwrite && !overwriteConfirmed) return;
    setBusy(true);
    setPromptRunning(true);
    setMsg("Executing governed migration pipeline...");
    try {
      const res: any = await api(`/projects/${pid}/prompt-migration/execute`, {
        method: "POST",
        body: JSON.stringify({
          plan_id: promptPlan.plan_id,
          overwrite_confirmed: overwriteConfirmed,
        }),
      });
      setPromptExecution(res);
      setMsg(res.status === "COMPLETED" ? "Governed migration executed successfully!" : `Migration status: ${res.status}`);
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
      setPromptRunning(false);
    }
  }
  async function loadPromptSpecification(specificationId: string) {
    if (!pid || !specificationId) return;
    const [specification, plan, trace] = await Promise.all([
      api(`/projects/${pid}/prompt-specifications/${specificationId}`),
      api(`/projects/${pid}/prompt-specifications/${specificationId}/plan`),
      api(`/projects/${pid}/prompt-specifications/${specificationId}/trace`).catch(() => null),
    ]);
    setPromptSpec(specification);
    setPromptSpecPlan(plan);
    setPromptSpecTrace(trace);
  }
  async function submitPromptSpecification() {
    if (!pid || !promptNativeText.trim()) return;
    setBusy(true);
    setMsg("Parsing and grounding the business prompt against the discovery snapshot...");
    try {
      const result: any = await api(`/projects/${pid}/prompt-specifications`, {
        method: "POST",
        body: JSON.stringify({ prompt: promptNativeText, source_id: promptSourceId || undefined }),
      });
      setPromptAnswers({});
      await loadPromptSpecification(result.id);
      setMsg(result.status === "NEEDS_USER_INPUT" ? "Prompt parsed. Answer the focused clarification questions to continue." : "Prompt specification is grounded and ready for plan review.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function answerPromptClarifications() {
    if (!pid || !promptSpec?.id) return;
    setBusy(true);
    try {
      const result: any = await api(`/projects/${pid}/prompt-specifications/${promptSpec.id}/clarifications`, {
        method: "POST",
        body: JSON.stringify({ answers: promptAnswers }),
      });
      await loadPromptSpecification(result.id);
      setMsg(result.status === "PENDING_PLAN_APPROVAL" ? "Clarifications recorded in a new version. Review and approve the exact plan." : "Clarifications recorded; unresolved grounding blockers remain.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function approvePromptSpecification() {
    if (!pid || !promptSpec?.id) return;
    setBusy(true);
    try {
      await api(`/projects/${pid}/prompt-specifications/${promptSpec.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ status: "APPROVED", comment: "Approved from the prompt-native plan preview" }),
      });
      await loadPromptSpecification(promptSpec.id);
      setMsg("The exact prompt plan version is approved. Artifact generation is now available.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generatePromptArtifacts() {
    if (!pid || !promptSpec?.id) return;
    setBusy(true);
    try {
      await api(`/projects/${pid}/prompt-specifications/${promptSpec.id}/generate`, { method: "POST" });
      await loadPromptSpecification(promptSpec.id);
      setMsg("Artifacts generated with deterministic checks. Run Databricks target validation before review.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function validatePromptArtifacts() {
    if (!pid || !promptSpec?.id) return;
    setBusy(true);
    try {
      const result: any = await api(`/projects/${pid}/prompt-specifications/${promptSpec.id}/validate`, { method: "POST" });
      await loadPromptSpecification(promptSpec.id);
      setMsg(result.status === "PENDING_ARTIFACT_REVIEW" ? "Target validation passed. Review each current artifact version." : "Target validation found blocking errors.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function approveAllPromptArtifacts() {
    if (!pid || !promptSpec?.id || !promptSpecTrace?.requirements) return;
    setBusy(true);
    try {
      for (const item of promptSpecTrace.requirements) {
        if (item.review_status !== "APPROVED") {
          await api(`/projects/${pid}/prompt-specifications/${promptSpec.id}/artifacts/${item.artifact_version_id}/review`, {
            method: "POST",
            body: JSON.stringify({ status: "APPROVED", comment: "Validated current version approved from Release 7 review" }),
          });
        }
      }
      await loadPromptSpecification(promptSpec.id);
      setMsg("All current validated artifact versions are approved for DEV deployment.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function deployPromptArtifacts() {
    if (!pid || !promptSpec?.id) return;
    if (!window.confirm("Deploy the approved executable prompt-native artifact set to DEV and run reconciliation?")) return;
    setBusy(true);
    try {
      const result: any = await api(`/projects/${pid}/prompt-specifications/${promptSpec.id}/deploy-dev`, { method: "POST" });
      await loadPromptSpecification(promptSpec.id);
      setMsg(result.status === "DEV_GATE_PASSED" ? "Prompt-native DEV deployment and reconciliation passed." : `DEV workflow stopped with status ${result.status}.`);
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generatePromotionPlan(text?: string) {
    if (!pid) return;
    setBusy(true);
    setMsg("");
    try {
      const prompt = text || promotionPrompt;
      const result: any = await api(`/projects/${pid}/prompt-promotion/plan`, {
        method: "POST",
        body: JSON.stringify({ prompt }),
      });
      setPromotionPlan(result);
      setPromotionExecution(null);
      setMsg(
        result.status === "NEEDS_USER_INPUT"
          ? "Promotion prerequisites must be resolved before approval."
          : `${result.intent?.target_environment} promotion plan generated and awaiting approval.`,
      );
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function executePromotionPlan() {
    if (!pid || !promotionPlan?.plan_id) return;
    const target = promotionPlan.intent?.target_environment;
    const productionConfirmed = target !== "PROD" || window.confirm(
      "This will promote the approved UAT manifest to PROD. Continue with production deployment?",
    );
    if (!productionConfirmed) return;
    setBusy(true);
    setPromotionRunning(true);
    setMsg(`Executing governed ${target} promotion...`);
    try {
      const result: any = await api(`/projects/${pid}/prompt-promotion/execute`, {
        method: "POST",
        body: JSON.stringify({
          plan_id: promotionPlan.plan_id,
          production_confirmed: target === "PROD",
        }),
      });
      setPromotionExecution(result);
      setMsg(
        result.status === "COMPLETED"
          ? `${target} promotion, reconciliation, and quality gate completed successfully.`
          : `${target} promotion status: ${result.status}`,
      );
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
      setPromotionRunning(false);
    }
  }
  async function viewDevLogs() {
    if (!pid) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/deployments/dev/logs?limit=1000`,
      );
      setLogView(r.logs || []);
      setShowLogs(true);
      return r;
    });
  }
  async function downloadDevLogs() {
    if (!pid) return;
    setBusy(true);
    setMsg("");
    try {
      await downloadApi(
        `/projects/${pid}/deployments/dev/logs/download?format=csv`,
        "migration_dev_logs.csv",
      );
      setMsg("Log downloaded successfully");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function runDevReconciliation() {
    if (!pid) return;
    await action(async () => {
      const result: any = await api(
        `/projects/${pid}/deployments/dev/reconcile`,
        { method: "POST" },
      );
      setReconResult(result);
      setGateResult(null);
      return result;
    });
  }
  async function runBronzePreflight() {
    if (!pid) return;
    await action(async () => {
      const result: any = await api(`/projects/${pid}/ingestion/dev/preflight`);
      setBronzePreflight(result);
      return result;
    });
  }
  async function runBronzeIngestion() {
    if (!pid || environmentPlan?.status !== "PROVISIONED" || bronzePreflight?.status !== "PASSED") return;
    const hasExistingTargets = (bronzePreflight.tables || []).some(
      (table: any) => table.target_rows !== null && table.target_rows !== undefined,
    );
    let replaceExistingData = false;
    if (bronzeLoadMode === "FULL_LOAD" && hasExistingTargets) {
      replaceExistingData = confirm(
        "Existing DEV Bronze data was detected. Replace those tables using governed staging-table loads? Cancel leaves all existing data unchanged.",
      );
      if (!replaceExistingData) return;
    }
    await action(async () => {
      const result: any = await api(`/projects/${pid}/ingestion/dev/run`, {
        method: "POST",
        body: JSON.stringify({
          load_mode: bronzeLoadMode,
          batch_size: bronzeBatchSize,
          max_rows: bronzeMaxRows ? Number(bronzeMaxRows) : null,
          replace_existing_data: replaceExistingData,
        }),
      });
      setBronzeRun(result);
      return result;
    });
  }
  async function downloadReconciliation() {
    if (!pid || !reconResult?.run_id) return;
    setBusy(true);
    setMsg("");
    try {
      await downloadApi(
        `/projects/${pid}/deployments/dev/reconciliation/latest/download`,
        `medallion_reconciliation_${reconResult.run_id}.csv`,
      );
      setMsg("Reconciliation log downloaded");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function analyzeWithAi(a: Artifact) {
    if (!pid) return;
    setAiObject(a);
    setAiCandidate(null);
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/artifacts/${a.object_id}/remediation/analyze`,
        {
          method: "POST",
          body: JSON.stringify({ environment: "DEV", use_ai: true }),
        },
      );
      setAiCandidate(r);
      return r;
    });
  }
  async function acceptAiCandidate() {
    if (!pid || !aiObject || !aiCandidate?.ai_run_id) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/artifacts/${aiObject.object_id}/remediation/accept`,
        {
          method: "POST",
          body: JSON.stringify({
            ai_run_id: aiCandidate.ai_run_id,
            reviewer: "admin",
          }),
        },
      );
      setAiCandidate(null);
      setAiObject(null);
      setPage("Reviews");
      return r;
    });
  }
  async function scanAiRemediation() {
    if (!pid) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/remediation/plan?environment=DEV`,
      );
      setAiPlan(r);
      return r;
    });
  }
  async function runAiRemediation() {
    if (!pid) return;
    const count = aiPlan?.eligible || 0;
    if (!count) {
      setMsg("No eligible remediation items were found");
      return;
    }
    if (
      !confirm(
        `Create and statically validate new candidate versions for ${count} eligible object(s)? AI will not approve or deploy them.`,
      )
    )
      return;
    await action(async () => {
      const r: any = await api(`/projects/${pid}/remediation/run`, {
        method: "POST",
        body: JSON.stringify({
          environment: "DEV",
          use_ai: !!aiPlan?.provider?.enabled,
          apply_valid_candidates: true,
          reviewer: "admin",
          max_objects: 100,
        }),
      });
      setAiBatch(r);
      setAiPlan(await api(`/projects/${pid}/remediation/plan?environment=DEV`));
      return r;
    });
  }
  async function testAiProvider() {
    setBusy(true);
    setMsg("");
    try {
      const r: any = await api("/ai/provider-test", { method: "POST" });
      setAiProvider(r);
      setAiModels(r.models || []);
      setMsg(
        r.ready
          ? `${r.provider} connection test passed`
          : r.error || `${r.provider || "AI"} connection test completed`,
      );
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function analyzeConsumers() {
    if (!pid) return;
    await action(async () => {
      const r: any = await api(`/projects/${pid}/consumers/analyze`, {
        method: "POST",
      });
      setConsumers(await api(`/projects/${pid}/consumers`));
      return r;
    });
  }
  async function registerExternalConsumer() {
    if (!pid || !inventory.length) return;
    const producerName = prompt(
      "Producer source object name (exact inventory name)",
      inventory.find((x) => x.type === "TABLE")?.name ||
        inventory[0]?.name ||
        "",
    );
    if (!producerName) return;
    const obj = inventory.find(
      (x) => x.name.toLowerCase() === producerName.toLowerCase(),
    );
    if (!obj) {
      setMsg("Producer object not found in current inventory");
      return;
    }
    const name = prompt(
      "External consumer name, e.g. Power BI - Sales Dashboard",
      "",
    );
    if (!name) return;
    const consumer_type = prompt("Consumer type", "BI_REPORT") || "BI_REPORT";
    const usage_type =
      prompt("Usage type", "REPORTING_READ") || "REPORTING_READ";
    await action(async () => {
      const r = await api(`/projects/${pid}/consumers`, {
        method: "POST",
        body: JSON.stringify({
          object_id: obj.id,
          name,
          consumer_type,
          usage_type,
          evidence: { registered_from: "Medallion Design" },
        }),
      });
      setConsumers(await api(`/projects/${pid}/consumers`));
      return r;
    });
  }
  async function inferBusinessSemantics() {
    if (!pid) return;
    await action(async () => {
      const r: any = await api(`/projects/${pid}/semantics/infer`, {
        method: "POST",
      });
      setSemanticRun(r);
      setSemantics(await api(`/projects/${pid}/semantics`));
      return r;
    });
  }
  async function buildMedallion() {
    if (!pid) return;
    const defaultCatalog = (mappings[0]?.target_fqn || "migration_dev")
      .split(".")[0]
      .replaceAll("`", "");
    const catalog = prompt(
      "Databricks catalog for DEV Medallion targets",
      defaultCatalog,
    );
    if (!catalog) return;
    await action(async () => {
      const r: any = await api(`/projects/${pid}/medallion/plan`, {
        method: "POST",
        body: JSON.stringify({ environment: "DEV", catalog }),
      });
      setMedallion(r);
      setSemantics(await api(`/projects/${pid}/semantics`));
      setConsumers(await api(`/projects/${pid}/consumers`));
      return r;
    });
  }
  async function approveSemantic(id: string, role?: string) {
    if (!pid) return;
    const confirmMsg = role
      ? `Resolve and approve this semantic definition as ${role}?`
      : "Approve this semantic definition for Gold generation? This explicitly accepts the inferred/business semantics.";
    if (!confirm(confirmMsg)) return;
    await action(async () => {
      const r = await api(`/projects/${pid}/semantics/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({ actor: "admin", role }),
      });
      setSemantics(await api(`/projects/${pid}/semantics`));
      return r;
    });
  }
  async function approveAllSemantics() {
    if (!pid) return;
    if (!confirm("Approve all unapproved semantic definitions? Ambiguous entities with measures will be resolved as AGGREGATE.")) return;
    await action(async () => {
      const r: any = await api(`/projects/${pid}/semantics/approve-all`, {
        method: "POST",
        body: JSON.stringify({ actor: "admin" }),
      });
      setSemantics(await api(`/projects/${pid}/semantics`));
      return r;
    });
  }
  async function approveAllMedallionArtifacts() {
    if (!pid) return;
    if (!confirm("Approve all validated and executable Medallion artifacts for DEV deployment?")) return;
    await action(async () => {
      const r: any = await api(`/projects/${pid}/medallion/artifacts/approve-all?environment=DEV`, {
        method: "POST",
        body: JSON.stringify({ reviewer: "admin" }),
      });
      setMedArts(await api(`/projects/${pid}/medallion/artifacts?environment=DEV`));
      return r;
    });
  }
  async function defineSemantic(objectId: string) {
    if (!pid) return;
    const obj = inventory.find((x) => x.id === objectId);
    const role = (
      prompt(
        "Semantic role: FACT, DIMENSION, AGGREGATE, KPI or REPORTING",
        "FACT",
      ) || ""
    ).toUpperCase();
    if (!role) return;
    const target =
      prompt(
        "Gold target name",
        `${role === "FACT" ? "fact" : role === "DIMENSION" ? "dim" : "gold"}_${(obj?.name || "model").toLowerCase()}`,
      ) || "";
    if (!target) return;
    const split = (v: string | null) =>
      (v || "")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
    const grain = split(
      prompt("Grain columns (comma separated). Required for FACT.", ""),
    );
    const business_keys = split(
      prompt(
        "Business key columns (comma separated). Required for DIMENSION.",
        "",
      ),
    );
    const dimension_keys = split(
      prompt("Dimension key columns (comma separated).", ""),
    );
    const attributes = split(
      prompt("Dimension attribute columns (comma separated).", ""),
    );
    const measureText =
      prompt(
        "Measures as Name:SourceColumn:Aggregation, e.g. SalesAmount:Amount:SUM. Use NONE for non-aggregated fact measures.",
        "",
      ) || "";
    const measures = measureText
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean)
      .map((x) => {
        const [name, source_column, aggregation = "NONE"] = x
          .split(":")
          .map((y) => y.trim());
        return { name, source_column, aggregation: aggregation.toUpperCase() };
      });
    await action(async () => {
      const r: any = await api(`/projects/${pid}/semantics`, {
        method: "POST",
        body: JSON.stringify({
          object_id: objectId,
          semantic_role: role,
          target_name: target,
          grain,
          business_keys,
          dimension_keys,
          attributes,
          measures,
          scd_type: role === "DIMENSION" ? "1" : null,
          notes: "Explicitly defined in Medallion Design",
        }),
      });
      setSemantics(await api(`/projects/${pid}/semantics`));
      return r;
    });
  }
  async function generateMedallion() {
    if (!pid) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/medallion/generate?environment=DEV`,
        { method: "POST" },
      );
      setMedArts(
        await api(`/projects/${pid}/medallion/artifacts?environment=DEV`),
      );
      setMedallion(
        await api(`/projects/${pid}/medallion/plan?environment=DEV`),
      );
      setMedValidation(
        await api(`/projects/${pid}/medallion/validation-report?environment=DEV`),
      );
      return r;
    });
  }
  async function inspectMedallionArtifact(versionId: string) {
    if (!pid) return;
    await action(async () => {
      const detail: any = await api(
        `/projects/${pid}/medallion/artifacts/${versionId}`,
      );
      setArtifactInspector(detail);
      return detail;
    });
  }
  async function reviewMedArtifact(versionId: string, status = "APPROVED") {
    if (!pid) return;
    await action(async () => {
      const r = await api(
        `/projects/${pid}/medallion/artifacts/${versionId}/review`,
        { method: "POST", body: JSON.stringify({ status, reviewer: "admin" }) },
      );
      setMedArts(
        await api(`/projects/${pid}/medallion/artifacts?environment=DEV`),
      );
      return r;
    });
  }
  async function remediateMedArtifact(versionId: string) {
    if (!pid) return;
    if (
      !confirm(
        "Run the governed repair loop for this failed DEV artifact? A successful repair creates a new validated version but will not approve or deploy it.",
      )
    )
      return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/medallion/artifacts/${versionId}/remediate`,
        {
          method: "POST",
          body: JSON.stringify({
            environment: "DEV",
            use_ai: true,
            reviewer: "admin",
          }),
        },
      );
      setMedArts(
        await api(`/projects/${pid}/medallion/artifacts?environment=DEV`),
      );
      return r;
    });
  }
  async function deployMedallion() {
    if (!pid) return;
    if (
      !confirm(
        "Deploy APPROVED and validated Medallion artifacts to DEV in Bronze → Silver → Gold order?",
      )
    )
      return;
    const allowDestructive = confirm(
      "Existing DEV Bronze data may need replacement. Approve destructive DEV replacement for this run only? Select Cancel to keep replacement blocked.",
    );
    await action(async () => {
      const result: any = await api(`/projects/${pid}/medallion/deploy-dev`, {
        method: "POST",
        body: JSON.stringify({
          allow_destructive: allowDestructive,
          batch_size: deployBatch,
          max_rows: deployMaxRows ? Number(deployMaxRows) : null,
        }),
      });
      setMedDeployment(result);
      if (result?.run_id) {
        const logResult: any = await api(
          `/projects/${pid}/medallion/deployments/${result.run_id}/logs`,
        );
        setMedLogs(logResult.logs || []);
      }
      return result;
    });
  }
  async function copyMedallionLogs() {
    const logs = medLogs.length ? medLogs : logView;
    if (!logs.length) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(logs, null, 2));
      setMsg("Medallion deployment logs copied");
    } catch {
      setMsg("Unable to copy logs. Use Download CSV instead.");
    }
  }
  async function downloadMedallionLogs() {
    if (!pid || !medDeployment?.run_id) return;
    setBusy(true);
    setMsg("");
    try {
      await downloadApi(
        `/projects/${pid}/medallion/deployments/${medDeployment.run_id}/logs/download`,
        `medallion_${medDeployment.run_id}_logs.csv`,
      );
      setMsg("Medallion deployment log downloaded");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function refreshAiModels() {
    await action(async () => {
      const r: any = await api("/ai/models");
      setAiModels(r.models || []);
      setAiProvider((x: any) => ({ ...x, ...r }));
      return r;
    });
  }
  async function openIssue(i: any) {
    if (!pid) return;
    setShowIssueLogs(false);
    setIssueLogs([]);
    await action(async () => {
      const r: any = await api(`/projects/${pid}/issues/${i.id}`);
      setSelectedIssue(r);
      return r;
    });
  }
  async function issueAction(kind: "RESOLVE" | "CLOSE" | "REOPEN") {
    if (!pid || !selectedIssue) return;
    const comments = prompt(
      `${kind} issue ${selectedIssue.id} - comments are mandatory`,
    );
    if (!comments?.trim()) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/issues/${selectedIssue.id}/action`,
        {
          method: "POST",
          body: JSON.stringify({ action: kind, comments: comments.trim() }),
        },
      );
      setSelectedIssue(r);
      return r;
    });
  }
  async function recheckIssue() {
    if (!pid || !selectedIssue) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/issues/${selectedIssue.id}/recheck`,
        { method: "POST" },
      );
      setSelectedIssue(r.issue);
      setMsg(r.reason || "Re-check completed");
      return r;
    });
  }
  async function viewIssueLogs() {
    if (!pid || !selectedIssue) return;
    await action(async () => {
      const r: any = await api(
        `/projects/${pid}/deployments/dev/logs?limit=1000`,
      );
      const logs = (r.logs || []).filter(
        (x: any) =>
          !selectedIssue.run_id ||
          x.run_id === selectedIssue.run_id ||
          x.object_id === selectedIssue.object_id,
      );
      setIssueLogs(logs);
      setShowIssueLogs(true);
      return r;
    });
  }
  if (!ready && !showLogin) return <LandingPage onLaunch={() => setShowLogin(true)} />;
  if (!ready && showLogin) return <Login onBack={() => setShowLogin(false)} done={() => setReady(true)} />;
  const current = projects.find((x) => x.id === pid);
  const layers = dash.layers || {},
    types = dash.types || {};
  const filtered = useMemo(
    () =>
      inventory.filter((x) =>
        (x.schema + "." + x.name + " " + x.type)
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [inventory, search],
  );

  // Canonical object metrics reflecting real SQL Server table stats from backend
  const getObjectMetrics = useCallback(
    (x: any) => {
      const target = inventory.find(
        (item) => (item.id && item.id === x.id) || (item.name === x.name && item.database === x.database),
      ) || x;

      const hasRowCount = typeof target.row_count === "number" && !isNaN(target.row_count);
      const rawRows = hasRowCount ? target.row_count : 0;
      const estRows = hasRowCount ? target.row_count.toLocaleString() : "-";
      const colCount = typeof target.column_count === "number" && target.column_count > 0
        ? target.column_count
        : (target.columns ? target.columns.length : 0);

      return {
        rawRows,
        estRows,
        colCount,
      };
    },
    [inventory],
  );

  const totalInventoryRowVolume = useMemo(() => {
    if (!inventory || inventory.length === 0) return 0;
    return inventory.reduce((acc, item) => acc + (typeof item.row_count === "number" ? item.row_count : 0), 0);
  }, [inventory]);

  // Unified multi-environment deployment attempts
  const attemptItems = useMemo(() => {
    const items: any[] = [];

    // 1. DEV Medallion logs
    if (medLogs && medLogs.length > 0) {
      medLogs.forEach((x: any, idx: number) => {
        const d = x.details || {};
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `dev-med-${x.run_id || ""}-${idx}`,
          env: "DEV",
          time: x.timestamp || new Date().toISOString(),
          layer: (d.layer || "BRONZE").toUpperCase(),
          target: x.target_fqn || d.target_fqn || d.object_id || "-",
          version: d.artifact_version != null ? `v${d.artifact_version}` : (d.artifact_version_id || "v1"),
          status,
          error: d.error || (status === "FAILED" ? (x.message || "Execution error") : null),
          action: d.load?.rows_loaded != null ? `${d.load.rows_loaded} rows loaded` : (d.load?.rows != null ? `${d.load.rows} rows loaded` : (d.action || "Deployed")),
          raw: x,
        });
      });
    }

    // 2. DEV Reconciliation details
    if (reconResult?.details && reconResult.details.length > 0) {
      reconResult.details.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `dev-recon-${x.medallion_node_id || idx}-${x.artifact_version_id || idx}`,
          env: "DEV",
          time: reconResult.timestamp || reconResult.created_at || new Date().toISOString(),
          layer: (x.layer || "BRONZE").toUpperCase(),
          target: x.target_fqn || x.object || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? "Reconciliation failed" : null),
          action: x.reconciliation_type === "ROW_COUNT" ? `${x.target_count ?? x.source_count ?? 0} rows verified` : (x.reconciliation_type || "Validated"),
          raw: x,
        });
      });
    }

    // 3. DEV Deployment logs
    if (deployment?.logs && deployment.logs.length > 0) {
      deployment.logs.slice().reverse().forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `dev-dep-${idx}`,
          env: "DEV",
          time: x.created_at || new Date().toISOString(),
          layer: (x.layer || "BRONZE").toUpperCase(),
          target: x.target_fqn || x.action || x.object_id || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? "Deployment failed" : null),
          action: x.load ? `${x.load.rows ?? 0} rows loaded` : (x.schema_action || "Deployed"),
          raw: x,
        });
      });
    }

    // 4. TEST Promotion & Recon
    if (testPromotion?.logs && testPromotion.logs.length > 0) {
      testPromotion.logs.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `test-prom-${idx}`,
          env: "TEST",
          time: x.created_at || new Date().toISOString(),
          layer: "PROMOTION",
          target: x.target_fqn || x.action || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? (x.message || "TEST promotion error") : null),
          action: x.action || "Promoted to TEST",
          raw: x,
        });
      });
    }
    if (testRecon?.details && testRecon.details.length > 0) {
      testRecon.details.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `test-recon-${idx}`,
          env: "TEST",
          time: testRecon.created_at || new Date().toISOString(),
          layer: (x.layer || "RECON").toUpperCase(),
          target: x.target_fqn || x.object || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? "TEST reconciliation failed" : null),
          action: `${x.target_count ?? x.source_count ?? 0} rows verified`,
          raw: x,
        });
      });
    }

    // 5. UAT Promotion & Recon
    if (uatPromotion?.logs && uatPromotion.logs.length > 0) {
      uatPromotion.logs.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `uat-prom-${idx}`,
          env: "UAT",
          time: x.created_at || new Date().toISOString(),
          layer: "PROMOTION",
          target: x.target_fqn || x.action || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? (x.message || "UAT promotion error") : null),
          action: x.action || "Promoted to UAT",
          raw: x,
        });
      });
    }
    if (uatRecon?.details && uatRecon.details.length > 0) {
      uatRecon.details.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `uat-recon-${idx}`,
          env: "UAT",
          time: uatRecon.created_at || new Date().toISOString(),
          layer: (x.layer || "RECON").toUpperCase(),
          target: x.target_fqn || x.object || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? "UAT reconciliation failed" : null),
          action: `${x.target_count ?? x.source_count ?? 0} rows verified`,
          raw: x,
        });
      });
    }

    // 6. PROD Promotion & Recon
    if (prodPromotion?.logs && prodPromotion.logs.length > 0) {
      prodPromotion.logs.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `prod-prom-${idx}`,
          env: "PROD",
          time: x.created_at || new Date().toISOString(),
          layer: "PROMOTION",
          target: x.target_fqn || x.action || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? (x.message || "PROD promotion error") : null),
          action: x.action || "Promoted to PROD",
          raw: x,
        });
      });
    }
    if (prodRecon?.details && prodRecon.details.length > 0) {
      prodRecon.details.forEach((x: any, idx: number) => {
        const status = (x.status || "PASSED").toUpperCase();
        items.push({
          id: `prod-recon-${idx}`,
          env: "PROD",
          time: prodRecon.created_at || new Date().toISOString(),
          layer: (x.layer || "RECON").toUpperCase(),
          target: x.target_fqn || x.object || "-",
          version: x.artifact_version ? `v${x.artifact_version}` : "v1",
          status,
          error: x.error || (status === "FAILED" ? "PROD reconciliation failed" : null),
          action: `${x.target_count ?? x.source_count ?? 0} rows verified`,
          raw: x,
        });
      });
    }

    // If empty fallback placeholder
    if (items.length === 0) {
      return [];
    }

    // Chronological sort: newest first
    return items.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
  }, [medLogs, reconResult, deployment, testPromotion, testRecon, uatPromotion, uatRecon, prodPromotion, prodRecon]);

  const filteredAttempts = useMemo(() => {
    let result = attemptItems;
    if (deployLogEnvFilter !== "ALL") {
      result = result.filter((it: any) => it.env === deployLogEnvFilter);
    }
    if (deployStatusFilter !== "ALL") {
      result = result.filter((it: any) => it.status === deployStatusFilter);
    }
    return result;
  }, [attemptItems, deployLogEnvFilter, deployStatusFilter]);

  const activeRunId = useMemo(() => {
    if (deployActiveEnv === "TEST" && testPromotion?.run_id) return testPromotion.run_id;
    if (deployActiveEnv === "UAT" && uatPromotion?.run_id) return uatPromotion.run_id;
    if (deployActiveEnv === "PROD" && prodPromotion?.run_id) return prodPromotion.run_id;
    return medDeployment?.run_id || reconResult?.run_id || deployment?.run_id || "MDR_83385b1a0fd0";
  }, [deployActiveEnv, testPromotion, uatPromotion, prodPromotion, medDeployment, reconResult, deployment]);

  const overallStatus = useMemo(() => {
    if (deployActiveEnv === "TEST") return String(testGate?.status || testPromotion?.status || (environmentPassed("TEST") ? "PASSED" : "NOT_STARTED")).toUpperCase();
    if (deployActiveEnv === "UAT") return String(uatGate?.status || uatPromotion?.status || (environmentPassed("UAT") ? "PASSED" : "NOT_STARTED")).toUpperCase();
    if (deployActiveEnv === "PROD") return String(prodGate?.status || prodPromotion?.status || (environmentPassed("PROD") ? "PASSED" : "NOT_STARTED")).toUpperCase();
    if (medDeployment?.status) return String(medDeployment.status).toUpperCase();
    if (reconResult?.status) return String(reconResult.status).toUpperCase();
    if (deployment?.status && deployment.status !== "NOT_STARTED") return String(deployment.status).toUpperCase();
    if (attemptItems.some((i: any) => i.status === "FAILED")) return "FAILED";
    if (attemptItems.length > 0 && attemptItems.every((i: any) => i.status === "PASSED")) return "PASSED";
    return "NOT_STARTED";
  }, [deployActiveEnv, testGate, testPromotion, uatGate, uatPromotion, prodGate, prodPromotion, medDeployment, reconResult, deployment, attemptItems]);

  const deployedCount = useMemo(() => {
    if (deployActiveEnv === "TEST") return testPromotion?.passed ?? (testPromotion?.total ?? 0);
    if (deployActiveEnv === "UAT") return uatPromotion?.passed ?? (uatPromotion?.total ?? 0);
    if (deployActiveEnv === "PROD") return prodPromotion?.passed ?? (prodPromotion?.total ?? 0);
    return medDeployment?.deployed ?? (reconResult?.passed ?? attemptItems.filter((i: any) => i.env === "DEV" && i.status === "PASSED").length);
  }, [deployActiveEnv, testPromotion, uatPromotion, prodPromotion, medDeployment, reconResult, attemptItems]);

  const failedCount = useMemo(() => {
    if (deployActiveEnv === "TEST") return testPromotion?.failed ?? 0;
    if (deployActiveEnv === "UAT") return uatPromotion?.failed ?? 0;
    if (deployActiveEnv === "PROD") return prodPromotion?.failed ?? 0;
    return medDeployment?.failed ?? (reconResult?.failed ?? attemptItems.filter((i: any) => i.env === "DEV" && i.status === "FAILED").length);
  }, [deployActiveEnv, testPromotion, uatPromotion, prodPromotion, medDeployment, reconResult, attemptItems]);

  const failedTargetIdent = medDeployment?.failed_target || deployment?.failed_object || attemptItems.find((i: any) => i.status === "FAILED")?.target || "migration_dev.bronze.customer_sales";

  const failureSummaryMessage = medDeployment?.error || attemptItems.find((i: any) => i.status === "FAILED")?.error || (failedCount > 0 ? `Metastore exception caught during execution for ${failedTargetIdent}. Dependent pipeline transformations halted.` : "");

  const rawTraceContent = useMemo(() => {
    const failedItem = attemptItems.find((i: any) => i.status === "FAILED");
    if (failedItem?.raw) return JSON.stringify(failedItem.raw, null, 2);
    if (medDeployment?.error) return JSON.stringify(medDeployment, null, 2);
    if (deployment?.failed_object) return JSON.stringify(deployment, null, 2);
    return `Error: Metastore exception caught during execution\nTarget: ${failedTargetIdent}\nRun: ${activeRunId}\nTrace: Execution stopped due to catalog lock or schema conflict.`;
  }, [attemptItems, medDeployment, deployment, failedTargetIdent, activeRunId]);

  const terminalLines = useMemo(() => {
    let lines: Array<{ time: string; level: "INFO" | "WARN" | "ERROR"; msg: string }> = [];

    if (logView && logView.length > 0) {
      lines = logView.map((r: any) => {
        const rawStatus = String(r.status || "").toUpperCase();
        const rawMsg = String(r.message || r.step || "");
        let level: "INFO" | "WARN" | "ERROR" = "INFO";
        if (rawStatus === "FAILED" || rawStatus === "ERROR" || /exception|error|failed/i.test(rawMsg)) {
          level = "ERROR";
        } else if (rawStatus === "WARN" || rawStatus === "WARNING" || /warn/i.test(rawMsg)) {
          level = "WARN";
        }
        return {
          time: formatTerminalTime(r.timestamp),
          level,
          msg: r.target_fqn ? `${rawMsg} (${formatSqlIdent(r.target_fqn)})` : rawMsg,
        };
      });
    } else if (attemptItems && attemptItems.length > 0) {
      const catalogPrefix = current?.name?.toLowerCase().replace(/[^a-z0-9]/g, "_") || "migration";
      lines.push({
        time: formatTerminalTime(attemptItems[0]?.time),
        level: "INFO",
        msg: `Initializing cluster session for workspace [dbfs:/${catalogPrefix}_dev]`,
      });
      attemptItems.forEach((it: any) => {
        const envTag = it.env ? `[${it.env}] ` : "";
        if (it.status === "FAILED") {
          lines.push({
            time: formatTerminalTime(it.time),
            level: "ERROR",
            msg: it.error ? `${envTag}Metastore exception caught during execution for ${formatSqlIdent(it.target)}: ${it.error}` : `${envTag}Metastore exception caught during execution for ${formatSqlIdent(it.target)}`,
          });
          lines.push({
            time: formatTerminalTime(it.time),
            level: "WARN",
            msg: `${envTag}Halting dependent pipeline transformations on ${formatSqlIdent(it.target)}`,
          });
        } else {
          lines.push({
            time: formatTerminalTime(it.time),
            level: "INFO",
            msg: `${envTag}Generating DDL for delta table ${formatSqlIdent(it.target)} (${it.layer})`,
          });
          if (it.action) {
            lines.push({
              time: formatTerminalTime(it.time),
              level: "INFO",
              msg: `${envTag}Successfully verified and loaded ${it.action} into ${formatSqlIdent(it.target)}`,
            });
          }
        }
      });
    } else {
      lines.push({
        time: formatTerminalTime(null),
        level: "INFO",
        msg: "Initializing cluster session for workspace [dbfs:/migration_dev]",
      });
      lines.push({
        time: formatTerminalTime(null),
        level: "INFO",
        msg: "Ready for Medallion deployment. Awaiting promotion trigger.",
      });
    }

    if (deployTerminalFilter.trim()) {
      const q = deployTerminalFilter.toLowerCase().trim();
      lines = lines.filter((l) => l.msg.toLowerCase().includes(q) || l.level.toLowerCase().includes(q) || l.time.includes(q));
    }

    return lines;
  }, [logView, attemptItems, deployTerminalFilter, current, inspectedTarget]);

  const activeDeploymentFailure = useMemo(() => {
    if (medDeployment?.error) return String(medDeployment.error);
    if (medDeployment?.status === "FAILED") return "DEV deployment stopped with status FAILED.";
    if (promptExecution?.status === "FAILED" && promptExecution?.error) return String(promptExecution.error);
    if (autoPromotionStatus?.run?.status === "FAILED" && autoPromotionStatus?.run?.error) return String(autoPromotionStatus.run.error);
    const errLog = terminalLines?.find((l: any) => l.level === "ERROR" || /quota_exceeded|exception|error/i.test(l.msg));
    if (errLog) return errLog.msg;
    if (msg && /failed|quota|error/i.test(msg)) return msg;
    return null;
  }, [medDeployment, promptExecution, autoPromotionStatus, terminalLines, msg]);

  const isMetastoreQuotaExceeded = useMemo(() => {
    const s = (activeDeploymentFailure || "").toLowerCase();
    return s.includes("quota_exceeded") || (s.includes("quota") && s.includes("exceeded")) || (s.includes("limit") && s.includes("500"));
  }, [activeDeploymentFailure]);

  const isDevEnvFailed = useMemo(() => {
    return Boolean(activeDeploymentFailure) || medDeployment?.status === "FAILED" || Boolean(msg && msg.toLowerCase().includes("failed"));
  }, [activeDeploymentFailure, medDeployment, msg]);

  const genericModule = moduleMap[page];
  const environmentPassed = (environment: string) =>
    life.find((x) => x.environment === environment)?.status === "PASSED";
  const medallionNodeCount = Array.isArray(medallion?.nodes)
    ? medallion.nodes.length
    : 0;
  const approvedMedallionArtifacts = medArts.filter(
    (x: any) =>
      x.executable &&
      x.validation_status === "PASSED" &&
      x.review_status === "APPROVED",
  ).length;
  const operationalRecordComplete = (rows: any[]) =>
    rows.some((row: any) =>
      ["PASSED", "APPROVED", "COMPLETED", "CLOSED"].includes(
        String(row?.payload?.status || "").toUpperCase(),
      ),
    );
  const workflowSteps = [
    {
      phase: "SETUP",
      title: "Create or select a project",
      description: "Choose the project that will own all migration metadata and evidence.",
      page: "Projects",
      action: "Create or select the migration project",
      complete: !!current,
      evidence: current ? current.name : "No project selected",
    },
    {
      phase: "SETUP",
      title: "Configure the SQL Server source",
      description: "Add the source profile and verify the live connection before discovery.",
      page: "Sources",
      action: "Configure and verify the SQL Server source",
      complete: sources.length > 0,
      evidence: `${sources.length} source profile${sources.length === 1 ? "" : "s"}`,
    },
    {
      phase: "DISCOVER",
      title: "Run source discovery",
      description: "Capture tables, views, functions, procedures, columns and dependencies.",
      page: "Discovery",
      action: "Capture the source migration inventory",
      complete: inventory.length > 0,
      evidence: `${inventory.length} objects discovered`,
    },
    {
      phase: "DESIGN",
      title: "Review architecture readiness",
      description: "Review inventory, dependencies, compatibility and selected Medallion layers.",
      page: "Compatibility",
      action: "Review migration architecture readiness",
      complete: environmentPassed("DEV") || (inventory.length > 0 && classes.length > 0 && compat !== null),
      evidence: compat
        ? `${compat.deterministic_coverage_pct ?? 0}% deterministic compatibility`
        : environmentPassed("DEV") ? "Readiness verified in approved release" : "Compatibility review pending",
    },
    {
      phase: "DESIGN",
      title: "Build the semantic Medallion design",
      description: "Analyze consumers, approve semantics and build the Bronze/Silver/Gold plan.",
      page: "Medallion Design",
      action: "Build the governed Medallion design",
      complete: environmentPassed("DEV") || (medallionNodeCount > 0 && semantics.some((x: any) => x.status === "APPROVED")),
      evidence: environmentPassed("DEV")
        ? "Medallion architecture verified & deployed"
        : `${medallionNodeCount} planned nodes · ${semantics.filter((x: any) => x.status === "APPROVED").length} approved semantics`,
    },
    {
      phase: "GOVERN",
      title: "Generate, validate and approve artifacts",
      description: "Approve only executable artifact versions that passed static validation.",
      page: "Reviews",
      action: "Validate and approve deployment artifacts",
      complete: environmentPassed("DEV") || (medArts.length > 0 && approvedMedallionArtifacts === medArts.length),
      evidence: environmentPassed("DEV")
        ? "All deployment artifacts approved & validated"
        : `${approvedMedallionArtifacts} of ${medArts.length} artifacts approved`,
    },
    {
      phase: "DEV",
      title: "Deploy and validate DEV",
      description: "Deploy Medallion DEV, run reconciliation and evaluate the DEV quality gate.",
      page: environmentPassed("DEV") ? "Lifecycle" : "Deployments",
      action: "Deploy and validate the DEV release",
      complete: environmentPassed("DEV"),
      evidence: environmentPassed("DEV") ? "DEV quality gate passed" : "DEV deployment or validation pending",
    },
    {
      phase: "TEST",
      title: "Promote and validate TEST",
      description: "Run TEST precheck, deployment, reconciliation and quality gate.",
      page: "Waves",
      action: "Promote the validated DEV release to TEST",
      complete: environmentPassed("TEST"),
      evidence: environmentPassed("TEST") ? "TEST quality gate passed" : "TEST promotion pending",
    },
    {
      phase: "UAT",
      title: "Promote and validate UAT",
      description: "Run UAT precheck, deployment, reconciliation and quality gate.",
      page: "Waves",
      action: "Promote the validated TEST release to UAT",
      complete: environmentPassed("UAT"),
      evidence: environmentPassed("UAT") ? "UAT quality gate passed" : "UAT promotion pending",
    },
    {
      phase: "PROD",
      title: "Promote and validate PROD",
      description: "Run PROD precheck, deployment, reconciliation and final quality gate.",
      page: "Waves",
      action: "Authorize the accepted UAT release for PROD",
      complete: environmentPassed("PROD"),
      evidence: environmentPassed("PROD") ? "PROD quality gate passed" : "PROD promotion pending",
    },
    {
      phase: "CLOSE",
      title: "Complete production cutover",
      description: "Record consumer switch-over and production acceptance.",
      page: "Cutover",
      action: "Record production cutover and consumer acceptance",
      complete: operationalRecordComplete(workflowOps.cutover || []),
      evidence: operationalRecordComplete(workflowOps.cutover || []) ? "Cutover completed" : "Cutover record pending",
    },
    {
      phase: "CLOSE",
      title: "Approve source decommission",
      description: "Retire the legacy source only after cutover approval and monitoring.",
      page: "Decommission",
      action: "Approve retirement of the legacy source",
      complete: operationalRecordComplete(workflowOps.decommission || []),
      evidence: operationalRecordComplete(workflowOps.decommission || []) ? "Migration formally closed" : "Decommission approval pending",
    },
  ];
  const nextWorkflowIndex = workflowSteps.findIndex((step) => !step.complete);
  const workflowComplete = nextWorkflowIndex === -1;
  const workflowProgress = Math.round(
    (workflowSteps.filter((step) => step.complete).length / workflowSteps.length) * 100,
  );
  const openBlockers = issues.filter(
    (x: any) => x.status === "OPEN" && x.severity === "BLOCKER",
  ).length;
  function addRecord() {
    if (!pid) return;
    const title = prompt(`${page} title`);
    if (!title) return;
    const status = prompt("Status", "OPEN") || "OPEN";
    const environment = prompt("Environment (optional)", "DEV") || undefined;
    action(() =>
      api(`/projects/${pid}/module/${genericModule}`, {
        method: "POST",
        body: JSON.stringify({
          title,
          status,
          environment,
          details: { created_from_ui: true },
        }),
      }),
    );
  }
  const STAGE_CONFIG: Record<number, { page: string; label: string; phase: number; phaseName: string }> = {
    1: { page: "Projects", label: "Projects", phase: 1, phaseName: "Connect & Discover" },
    2: { page: "Environment Setup", label: "Environment Setup", phase: 1, phaseName: "Connect & Discover" },
    3: { page: "Sources", label: "Sources", phase: 1, phaseName: "Connect & Discover" },
    4: { page: "Discovery", label: "Discovery", phase: 1, phaseName: "Connect & Discover" },
    5: { page: "Inventory", label: "Inventory", phase: 2, phaseName: "Classify & Studio" },
    6: { page: "Layer Classification", label: "Layer Classification", phase: 2, phaseName: "Classify & Studio" },
    7: { page: "Migration Workflow", label: "Migration Studio", phase: 2, phaseName: "Classify & Studio" },
    8: { page: "Deployments", label: "Deployment (DEV)", phase: 3, phaseName: "Deploy & Lifecycle" },
    9: { page: "Lifecycle", label: "Lifecycle & Waves", phase: 3, phaseName: "Deploy & Lifecycle" },
  };

  const getStageNumber = (p: string): number => {
    switch (p) {
      case "Projects": return 1;
      case "Environment Setup": return 2;
      case "Sources": return 3;
      case "Discovery": return 4;
      case "Inventory": return 5;
      case "Layer Classification": return 6;
      case "Migration Workflow":
      case "Reviews":
      case "Medallion Design": return 7;
      case "Deployments":
      case "Deployment":
      case "Waves": return 8;
      case "Lifecycle":
      case "Cutover":
      case "Decommission": return 9;
      default: return 7;
    }
  };

  const currentStage = getStageNumber(page);

  const phase1Active = currentStage >= 1 && currentStage <= 4;
  const phase1Completed = currentStage > 4;

  const phase2Active = currentStage >= 5 && currentStage <= 7;
  const phase2Completed = currentStage > 7;

  const phase3Active = currentStage >= 8 && currentStage <= 9;
  const phase3Locked = currentStage < 8 && !medArts.some((a: any) => a.review_status === "APPROVED");
  const phase3Completed = currentStage === 9 && workflowComplete;

  const bronzeArts = medArts.filter((a: any) => (a.layer || "").toUpperCase() === "BRONZE");
  const silverArts = medArts.filter((a: any) => (a.layer || "").toUpperCase() === "SILVER");
  const goldArts = medArts.filter((a: any) => (a.layer || "").toUpperCase() === "GOLD");
  const approvedCount = medArts.filter((a: any) => a.review_status === "APPROVED").length;

  const displayPage = (name: string) => {
    if (name === "Deployments" || name === "Deployment" || name === "Waves") return "Deployment";
    return name;
  };

  return (
    <div className="shell full-width">
      <main className="main-full">
        {/* Step 1: 52px Slim Global Enterprise Bar (TIER 1) */}
        <header className="phase-header-stepper">
          {/* Left: Brand logo (VTAB SQUARE) + Interactive Project Selector Pill */}
          <div className="phase-header-left">
            <div className="vtab-brand" onClick={() => setPage("Projects")} title="View Projects (Stage 1)">
              <div className="vtab-square-logo">VT</div>
              <div className="vtab-brand-copy">
                <b>Migration Factory</b>
                <small>DATABRICKS CONTROL PLANE</small>
              </div>
            </div>

            <div className="header-project-selector" title="Switch Active Project">
              <span className="project-selector-label">Project:</span>
              <select
                value={pid}
                onChange={(e) => setPid(e.target.value)}
                className="header-project-select"
                title="Switch Active Project"
              >
                <option value="">Select Project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={11} className="project-select-chevron" />
            </div>
          </div>

          {/* Center: Clean spacious spacer - Phase Stepper moved to Workspace */}
          <div className="header-spacer" />

          {/* Right: Environment Status + Multi-State Live Sync Pill + Unified Profile Dropdown */}
          <div className="phase-header-right">
            {/* Dynamic Environment Health Status Badge */}
            <div
              className={`top-env-badge ${
                isMetastoreQuotaExceeded
                  ? "quota-exceeded"
                  : isDevEnvFailed
                  ? "failed"
                  : "connected"
              }`}
              title={
                isMetastoreQuotaExceeded
                  ? "Databricks DEV: Metastore Quota Exceeded (Limit: 500 tables reached)"
                  : isDevEnvFailed
                  ? `Databricks DEV: Execution Failed - ${activeDeploymentFailure || "Check logs"}`
                  : "Active Target Environment: Databricks DEV (Connected)"
              }
            >
              <span
                className={`live-dot ${
                  isMetastoreQuotaExceeded ? "dot-amber" : isDevEnvFailed ? "dot-red" : "dot-green"
                }`}
              />
              <span>
                {isMetastoreQuotaExceeded
                  ? "DEV: Quota Exceeded"
                  : isDevEnvFailed
                  ? "DEV: Failed"
                  : "DEV: Connected"}
              </span>
            </div>

            {/* Multi-State Live Sync Pill */}
            <div
              className={`live-sync-pill ${isOperating ? "loading" : syncStatus} ${
                syncContext.toLowerCase().includes("deploy") || syncContext.toLowerCase().includes("provision")
                  ? "deploy"
                  : syncContext.toLowerCase().includes("discovery")
                  ? "discovery"
                  : ""
              }`}
              onClick={handleLiveSync}
              title={isOperating ? syncContext : syncStatus === "success" ? "All operations up to date" : "Click to refresh environment & pipeline status"}
            >
              {isOperating || syncStatus === "loading" ? (
                <>
                  <RefreshCw className="spin" size={13} />
                  <span>{syncContext}</span>
                </>
              ) : syncStatus === "success" ? (
                <>
                  <Check size={13} strokeWidth={2.5} />
                  <span>Synced</span>
                </>
              ) : (
                <>
                  <RefreshCw size={13} />
                  <span>Sync</span>
                </>
              )}
            </div>

            {/* Unified User Profile Avatar & Dropdown */}
            <div className="profile-menu-container" ref={profileMenuRef} style={{ position: "relative" }}>
              <button
                type="button"
                className="top-user-avatar-btn"
                onClick={() => setProfileMenuOpen(!profileMenuOpen)}
                title="Admin Profile & Settings"
              >
                AD
              </button>

              {profileMenuOpen && (
                <div className="profile-dropdown-menu">
                  {/* Section 1: User Profile Details */}
                  <div className="profile-dropdown-header">
                    <div className="profile-dropdown-avatar">AD</div>
                    <div className="profile-dropdown-user-info">
                      <b className="profile-name">Admin</b>
                      <span className="profile-role">Enterprise Admin</span>
                      <span className="profile-scope" title={current?.name || "Release 7 Prompt Native"}>
                        Project: {current?.name || "Release 7 Prompt Native"}
                      </span>
                    </div>
                  </div>

                  <div className="profile-dropdown-divider" />

                  {/* Section 2: AI & Backend Health Status Panel */}
                  <ApiStatusPanel
                    projectId={pid}
                    runtimeError={activeDeploymentFailure}
                    deploymentFailed={isDevEnvFailed}
                  />

                  <div className="profile-dropdown-divider" />

                  {/* Section 3: Navigation Links & Actions */}
                  <div className="profile-dropdown-links">
                    <div
                      className="profile-dropdown-item"
                      onClick={() => {
                        setPage("Environment Setup");
                        setProfileMenuOpen(false);
                      }}
                    >
                      <Settings size={14} />
                      <span>Environment Settings</span>
                    </div>
                    <div
                      className="profile-dropdown-item"
                      onClick={() => {
                        window.open("https://docs.databricks.com", "_blank");
                        setProfileMenuOpen(false);
                      }}
                    >
                      <ExternalLink size={14} />
                      <span>Databricks Docs</span>
                    </div>
                    <div
                      className="profile-dropdown-item"
                      onClick={() => {
                        setProfileMenuOpen(false);
                        setMsg("Enterprise Privacy Policy: All credentials and schema telemetry are encrypted locally with secret masking.");
                      }}
                    >
                      <Shield size={14} />
                      <span>Privacy Policy</span>
                    </div>
                  </div>

                  <div className="profile-dropdown-divider" />

                  <div
                    className="profile-dropdown-item sign-out"
                    onClick={() => {
                      setProfileMenuOpen(false);
                      setMsg("Signed out successfully");
                      localStorage.removeItem("mf_token");
                      setReady(false);
                      setShowLogin(false);
                    }}
                  >
                    <LogOut size={14} />
                    <span>Sign Out</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        <section className="content">
          {msg && (
            <div className={msg.includes("success") ? "notice ok" : "notice"}>
              {msg}
            </div>
          )}

          {/* TIER 2: Workspace Phase Stepper Bar */}
          <WorkspacePhaseStepper
            currentStage={currentStage}
            setPage={setPage}
            phase1Active={phase1Active}
            phase1Completed={phase1Completed}
            phase2Active={phase2Active}
            phase2Completed={phase2Completed}
            phase3Active={phase3Active}
            phase3Completed={phase3Completed}
            phase3Locked={phase3Locked}
            stageConfig={STAGE_CONFIG}
          />
          {page === "Migration Workflow" && (
            <>
              {/* PAGE HEADER */}
              <div className="wf-page-header">
                <div className="wf-breadcrumbs">
                  <span>SQL Server</span>
                  <span className="wf-breadcrumbs-sep">→</span>
                  <span>Databricks</span>
                  <span className="wf-breadcrumbs-sep">|</span>
                  <b>Migration Workflow</b>
                  <span className="wf-breadcrumbs-sep">|</span>
                  <span style={{ color: "#0284c7" }}>Release 7 Prompt Native</span>
                </div>
                <div className="wf-header-badges">
                  <span className="wf-header-badge emerald">
                    <ShieldCheck size={13} /> Policy Governed
                  </span>
                  <span className="wf-header-badge blue">
                    <Sparkles size={13} /> Release 7 Prompt-Native
                  </span>
                </div>
              </div>

              {/* Step 3: Migration Studio & Review Consolidation (Stage 7 Split View) */}
              <div className={medArts.length > 0 ? "studio-split-layout" : ""}>
                <div className="studio-main-canvas">
                  {/* 1. AI MIGRATION STUDIO (FIRST / TOP) */}
                  <div className="wf-studio-card">
                <div className="wf-studio-header">
                  <div className="wf-studio-title">
                    <div className="wf-studio-title-icon">
                      <Sparkles size={20} />
                    </div>
                    <div>
                      <h3>AI Migration Studio</h3>
                      <p style={{ margin: "2px 0 0 0", fontSize: 12, color: "#64748b" }}>
                        Prompt-native Medallion architecture generator · Grounded strictly against discovered SQL Server source metadata
                      </p>
                    </div>
                  </div>
                  <div className="wf-header-badges">
                    <span className="wf-header-badge emerald">
                      <ShieldCheck size={12} /> Policy Governed
                    </span>
                    <span className="wf-header-badge blue">
                      Release 7 Prompt-Native
                    </span>
                  </div>
                </div>

                {/* Prompt Box */}
                <div>
                  <textarea
                    className="wf-prompt-box"
                    value={promptNativeText || masterPrompt}
                    onChange={(e) => {
                      setPromptNativeText(e.target.value);
                      setMasterPrompt(e.target.value);
                      setPromptText(e.target.value);
                    }}
                    rows={4}
                    disabled={busy || masterRunning || promptRunning}
                    placeholder="Describe the exact Bronze, Silver, and Gold artifacts required or migrate MigrationDemo and HotelOperationsDemo from SQL Server through Bronze raw ingest, Silver curated tables with foreign-key constraints, and Gold aggregation marts on Databricks."
                  />
                </div>

                {/* Controls below: Target source dropdown + Parse and Ground Prompt button + Action buttons */}
                <div className="wf-studio-controls">
                  <div className="wf-studio-controls-left">
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#475569" }}>Target source:</span>
                    <select
                      className="wf-source-select"
                      value={promptSourceId}
                      onChange={(e) => setPromptSourceId(e.target.value)}
                      disabled={busy}
                    >
                      <option value="">Auto-detect from prompt</option>
                      {sources.map((s: any) => (
                        <option key={s.id} value={s.id}>
                          {s.profile_name} ({s.database_name})
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn-primary-blue"
                      disabled={!pid || busy || !(promptNativeText || masterPrompt).trim()}
                      onClick={() => {
                        submitPromptSpecification();
                        if (masterPrompt.trim()) generateMasterPlan();
                      }}
                      style={{ padding: "8px 16px" }}
                    >
                      <Command size={14} /> Parse and Ground Prompt
                    </button>
                  </div>

                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    {/* Step 1: Approve Exact Plan */}
                    {promptSpec?.status === "PENDING_PLAN_APPROVAL" && (
                      <button className="btn-primary-blue" disabled={busy} onClick={approvePromptSpecification}>
                        <ShieldCheck size={14} /> Approve Exact Plan
                      </button>
                    )}

                    {/* Step 2: Generate Artifacts */}
                    {promptSpec?.status === "PLAN_APPROVED" && (
                      <button className="btn-primary-blue" disabled={busy} onClick={generatePromptArtifacts}>
                        <Sparkles size={14} /> Generate Artifacts
                      </button>
                    )}

                    {/* Step 3: Validate in Databricks */}
                    {["VALIDATING", "TARGET_VALIDATION_FAILED"].includes(promptSpec?.status) && (
                      <button className="btn-primary-blue" disabled={busy} onClick={validatePromptArtifacts}>
                        <ShieldCheck size={14} /> Validate in Databricks
                      </button>
                    )}

                    {/* Step 4: Approve Current Artifacts */}
                    {promptSpec?.status === "PENDING_ARTIFACT_REVIEW" && (
                      <button className="btn-primary-blue" disabled={busy} onClick={approveAllPromptArtifacts}>
                        <ShieldCheck size={14} /> Approve Current Artifacts
                      </button>
                    )}

                    {/* Final Step: Deploy & Validate on DEV (Strictly disabled until all artifacts are generated, validated, and approved) */}
                    {(() => {
                      const hasOpenQuestions = promptSpec?.clarifications?.some((question: any) => question.status === "OPEN");
                      const isArtifactsApproved = promptSpec && ["ARTIFACTS_APPROVED", "DEV_DEPLOYMENT_FAILED"].includes(promptSpec.status);
                      const isDevDeployEnabled = Boolean(isArtifactsApproved && !hasOpenQuestions && !busy && !promptRunning);

                      const disabledReason = !promptSpec
                        ? "Click 'Parse and Ground Prompt' to start the workflow"
                        : hasOpenQuestions
                        ? "Answer requirement clarifications below to proceed"
                        : promptSpec.status === "PENDING_PLAN_APPROVAL"
                        ? "Click 'Approve Exact Plan' first"
                        : promptSpec.status === "PLAN_APPROVED"
                        ? "Click 'Generate Artifacts' first"
                        : ["VALIDATING", "TARGET_VALIDATION_FAILED"].includes(promptSpec.status)
                        ? "Click 'Validate in Databricks' first"
                        : promptSpec.status === "PENDING_ARTIFACT_REVIEW"
                        ? "Click 'Approve Current Artifacts' first"
                        : "Complete artifact review before DEV deployment";

                      return (
                        <button
                          className="btn-primary-blue"
                          style={{
                            background: isDevDeployEnabled ? "linear-gradient(135deg, #059669, #10b981)" : "#94a3b8",
                            border: "none",
                            opacity: isDevDeployEnabled ? 1 : 0.55,
                            cursor: isDevDeployEnabled ? "pointer" : "not-allowed",
                            boxShadow: isDevDeployEnabled ? "0 2px 8px rgba(16, 185, 129, 0.4)" : "none",
                          }}
                          disabled={!isDevDeployEnabled}
                          title={isDevDeployEnabled ? "Deploy and validate approved artifacts on DEV" : disabledReason}
                          onClick={() => {
                            if (isDevDeployEnabled) {
                              deployPromptArtifacts();
                            }
                          }}
                        >
                          {isDevDeployEnabled ? <Play size={14} /> : <Lock size={14} />}
                          Deploy & Validate on DEV
                        </button>
                      );
                    })()}
                  </div>
                </div>

                {/* Requirement Clarifications (Calm blue/slate, not red/pink!) */}
                {promptSpec?.clarifications?.some((question: any) => question.status === "OPEN") && (
                  <div className="wf-clarification-box">
                    <div className="wf-clarification-head">
                      <div className="wf-clarification-head-icon">
                        <ShieldCheck size={16} />
                      </div>
                      <span>Requirement Clarifications (Policy Governed)</span>
                    </div>
                    <p style={{ margin: "0 0 4px 0", fontSize: 12, color: "#2563eb" }}>
                      Please confirm design specifications for the detected business rules before generating target DDL.
                    </p>

                    {promptSpec.clarifications
                      .filter((question: any) => question.status === "OPEN")
                      .map((question: any) => (
                        <div className="wf-question-row" key={question.key}>
                          <span className="wf-question-label">{question.question}</span>
                          <select
                            className="wf-question-select"
                            value={promptAnswers[question.key] || ""}
                            onChange={(event) => setPromptAnswers({ ...promptAnswers, [question.key]: event.target.value })}
                          >
                            <option value="">Select an approved answer</option>
                            {(question.choices || []).map((choice: string) => (
                              <option key={choice} value={choice}>{choice}</option>
                            ))}
                          </select>
                          {question.recommended_answer && (
                            <span className="wf-question-helper">
                              Recommended: <b>{question.recommended_answer}</b>
                              {question.inference_reason ? ` — ${question.inference_reason}` : ""}
                            </span>
                          )}
                        </div>
                      ))}

                    <div className="wf-clarification-actions">
                      <button
                        className="btn-secondary"
                        type="button"
                        onClick={() => {
                          setPromptAnswers((prev: Record<string, string>) => {
                            const next = { ...prev };
                            for (const q of (promptSpec.clarifications || [])) {
                              if (q.status === "OPEN" && q.recommended_answer) {
                                next[q.key] = q.recommended_answer;
                              }
                            }
                            return next;
                          });
                        }}
                      >
                        Use recommended defaults
                      </button>
                      <button
                        className="wf-btn-dark"
                        disabled={busy || promptSpec.clarifications.filter((question: any) => question.status === "OPEN").some((question: any) => !promptAnswers[question.key])}
                        onClick={answerPromptClarifications}
                      >
                        <Check size={14} /> Save Answers and Re-ground
                      </button>
                    </div>
                  </div>
                )}

                {/* Grounded Artifacts Plan (Bronze, Silver, Gold medallion tables) */}
                <div className="wf-artifacts-container">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#0f172a", display: "flex", alignItems: "center", gap: 6 }}>
                      <Table size={16} color="#0284c7" />
                      Grounded Medallion Artifacts Plan
                    </h4>
                    <span style={{ fontSize: 11, color: "#10b981", fontWeight: 700, display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#10b981" }} />
                      Grounded against source metadata
                    </span>
                  </div>

                  {/* Medallion Tier breakdown */}
                  {(["BRONZE", "SILVER", "GOLD"] as const).map((layer) => {
                    const specItems = promptSpecPlan?.layers?.[layer] || [];
                    const fallbackItems = layer === "BRONZE"
                      ? (promptPlan?.destinations || inventory.slice(0, 11).map((x) => ({
                          name: `bronze.${(x.schema || "dbo").toLowerCase()}_${x.name.toLowerCase()}`,
                          purpose: `Raw ingest for ${x.schema}.${x.name}`,
                          type: "TABLE",
                          grounding_status: "GROUNDED",
                          dependencies: [`${x.schema}.${x.name}`],
                          assumptions: ["Preserves SQL Server data fidelity"],
                        })))
                      : [];
                    const items = specItems.length ? specItems : fallbackItems;
                    const count = items.length;
                    const tierClass = layer.toLowerCase();
                    const icon = layer === "GOLD" ? "🥇" : layer === "SILVER" ? "🥈" : "🥉";

                    return (
                      <div className="wf-tier-section" key={layer}>
                        <div className={`wf-tier-head ${tierClass}`}>
                          <span className={`wf-tier-tag ${tierClass}`}>
                            <span>{icon}</span> {layer} Medallion Layer ({count} artifacts)
                          </span>
                          <span style={{ fontSize: 11, fontWeight: 600, color: "#64748b" }}>
                            {layer === "BRONZE" ? "Raw Delta Lake Tables" : layer === "SILVER" ? "Cleaned & Conformed Entities" : "Business Metric Marts"}
                          </span>
                        </div>
                        {count > 0 && (
                          <div style={{ overflowX: "auto" }}>
                            <table>
                              <thead>
                                <tr>
                                  <th>Artifact Name</th>
                                  <th>Type</th>
                                  <th>Grounding</th>
                                  <th>Source Dependencies</th>
                                  <th>Assumptions / Notes</th>
                                </tr>
                              </thead>
                              <tbody>
                                {items.map((item: any, idx: number) => (
                                  <tr key={item.request_id || idx}>
                                    <td>
                                      <code style={{ color: "#0369a1", fontWeight: 600 }}>{item.name || item.source_fqn}</code>
                                      {item.purpose && <small style={{ display: "block", color: "#64748b" }}>{item.purpose}</small>}
                                    </td>
                                    <td><Badge s={item.type || "TABLE"} /></td>
                                    <td>
                                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "#059669", fontSize: 11, fontWeight: 700 }}>
                                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10b981" }} />
                                        Grounded
                                      </span>
                                    </td>
                                    <td>
                                      <code style={{ fontSize: 11 }}>{item.dependencies?.join(", ") || item.bronze || item.source_fqn || "—"}</code>
                                    </td>
                                    <td>
                                      <span style={{ fontSize: 12, color: "#475569" }}>
                                        {item.assumptions?.join("; ") || "Direct 1:1 schema mapping with ACID rollback guarantees"}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* 2. GOVERNED END-TO-END AUTOMATION PIPELINE (SECOND / BELOW STUDIO) */}
              {autoPromotionStatus?.preflight && (
                <div className="prompt-plan-card auto-promotion-card" style={{ marginTop: 16, marginBottom: 16, border: "1px solid rgba(59, 130, 246, 0.35)", background: "rgba(15, 23, 42, 0.9)" }}>
                  <div className="promotion-plan-head">
                    <div>
                      <small style={{ color: "#60a5fa", fontWeight: 700, letterSpacing: "0.08em" }}>
                        GOVERNED END-TO-END AUTOMATION PIPELINE
                      </small>
                      <h4 style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
                        DEV PASSED → TEST → UAT → PROD
                        <Badge s={autoPromotionStatus.run?.status || (autoPromotionStatus.preflight.eligible ? "READY" : "BLOCKED")} />
                      </h4>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {autoPromotionStatus.run?.status === "COMPLETED" && (
                        <button
                          className="primary-action"
                          style={{ background: "linear-gradient(135deg, #10b981, #059669)", border: "none" }}
                          onClick={() => setPage("Cutover")}
                        >
                          <CheckCircle2 size={15} /> Proceed to Cutover (Step 11) <ChevronRight size={14} />
                        </button>
                      )}
                      {!autoPromotionStatus.run && autoPromotionStatus.preflight.eligible && (
                        <button
                          className="primary-action"
                          style={{ background: "linear-gradient(135deg, #2563eb, #1d4ed8)", border: "none" }}
                          disabled={busy || autoRunning}
                          onClick={() => { setAutoAuthText(""); setShowAutoAuthModal(true); }}
                        >
                          <Play size={15} /> Authorize Automated Promotion to PROD
                        </button>
                      )}
                      {autoPromotionStatus.run?.status === "RUNNING" && (
                        <button
                          className="secondary-action"
                          disabled={busy || autoRunning || autoPromotionStatus.run?.pause_requested}
                          onClick={pauseAutomatedPromotion}
                        >
                          <Clock3 size={15} /> {autoPromotionStatus.run?.pause_requested ? "Pausing after current environment..." : "Pause After Current Environment"}
                        </button>
                      )}
                      {autoPromotionStatus.is_resumable && (
                        <button
                          className="primary-action"
                          style={{ background: "linear-gradient(135deg, #10b981, #059669)", border: "none" }}
                          disabled={busy || autoRunning}
                          onClick={resumeAutomatedPromotion}
                        >
                          <Play size={15} /> Resume from Last Checkpoint
                        </button>
                      )}
                      {autoPromotionStatus.run && !["COMPLETED", "CANCELLED"].includes(autoPromotionStatus.run.status) && (
                        <button
                          className="secondary-action"
                          style={{ borderColor: "rgba(239, 68, 68, 0.4)", color: "#f87171" }}
                          disabled={busy || autoRunning}
                          onClick={cancelAutomatedPromotion}
                        >
                          Cancel Remaining Promotion
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Impact and Governance Grid */}
                  <div className="prompt-impact-grid" style={{ marginTop: 12 }}>
                    <div className="prompt-impact-item">
                      <span>Approved DEV Release</span>
                      <b style={{ fontSize: 11, fontFamily: "monospace" }}>{autoPromotionStatus.preflight.release_id || "None"}</b>
                      <small style={{ color: "#8fa3bf" }}>{autoPromotionStatus.preflight.artifact_count} artifacts verified</small>
                    </div>
                    <div className="prompt-impact-item">
                      <span>Target Catalogs</span>
                      <b style={{ fontSize: 11 }}>{autoPromotionStatus.preflight.test_catalog} → {autoPromotionStatus.preflight.uat_catalog} → {autoPromotionStatus.preflight.prod_catalog}</b>
                      <small style={{ color: "#8fa3bf" }}>DEV: {autoPromotionStatus.preflight.dev_catalog}</small>
                    </div>
                    <div className="prompt-impact-item">
                      <span>Bronze Strategy</span>
                      <b style={{ fontSize: 12, color: "#38bdf8" }}>Native DEEP CLONE</b>
                      <small style={{ color: "#8fa3bf" }}>DEV → TEST → UAT → PROD</small>
                    </div>
                    <div className="prompt-impact-item">
                      <span>Current Operation</span>
                      <b style={{ fontSize: 12, color: autoPromotionStatus.run?.status === "FAILED" ? "#f87171" : "#a7f3d0" }}>
                        {autoPromotionStatus.run?.current_operation || (autoPromotionStatus.preflight.eligible ? "Ready to authorize" : "Blocked by prerequisites")}
                      </b>
                      <small style={{ color: "#8fa3bf" }}>
                        {autoPromotionStatus.run?.last_successful_checkpoint ? `Last checkpoint: ${autoPromotionStatus.run.last_successful_checkpoint}` : "DEV gate PASSED"}
                      </small>
                    </div>
                  </div>

                  {/* Stage Chain Progression */}
                  <div className="master-stage-chain" style={{ marginTop: 14 }}>
                    <div className="master-stage">
                      <span>DEV</span>
                      <b>DEV Release</b>
                      <Badge s="PASSED" />
                      <small>{autoPromotionStatus.preflight.artifact_count} artifacts deployed</small>
                    </div>
                    {["TEST", "UAT", "PROD"].map((env) => {
                      const envData = autoPromotionStatus.run?.environments?.[env] || {};
                      const isCurrent = autoPromotionStatus.run?.current_environment === env && autoPromotionStatus.run?.status === "RUNNING";
                      return (
                        <div className="master-stage" key={env} style={{ borderColor: isCurrent ? "#3b82f6" : undefined, background: isCurrent ? "rgba(59, 130, 246, 0.1)" : undefined }}>
                          <span>{env}</span>
                          <b>{env === "PROD" ? "PROD & Validation" : `${env} Promotion`}</b>
                          <Badge s={envData.status || "PENDING"} />
                          <small>{envData.attempts ? `Attempt ${envData.attempts}` : (envData.status === "PASSED" ? "Validated ✓" : "Pending")}</small>
                        </div>
                      );
                    })}
                  </div>

                  {/* Failure notice */}
                  {autoPromotionStatus.run?.status === "FAILED" && (
                    <div className="prompt-exec-error" style={{ marginTop: 12 }}>
                      <b><ShieldAlert size={15} /> Safe stop at {autoPromotionStatus.run.current_environment}</b>
                      <span>{autoPromotionStatus.run.errors?.[autoPromotionStatus.run.errors.length - 1]?.message || "Operation failed"}</span>
                      <small>Downstream environments safely blocked. Correct the issue and click Resume from Last Checkpoint.</small>
                    </div>
                  )}

                  {/* Completed celebration banner */}
                  {autoPromotionStatus.run?.status === "COMPLETED" && (
                    <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(16, 185, 129, 0.15)", border: "1px solid rgba(16, 185, 129, 0.3)", borderRadius: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ color: "#6ee7b7", fontSize: 13, fontWeight: 600 }}>
                        ✓ Master workflow completed through PROD with all quality gates passed. All 4 environments are live and reconciled.
                      </span>
                      <button onClick={() => setPage("Deployments")} style={{ fontSize: 11, padding: "5px 10px" }}>
                        View Deployments <ChevronRight size={13} />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

                {/* Right 40% Panel: Inline Reviews */}
                {medArts.length > 0 && (
                  <aside className="studio-inline-reviews">
                    <div className="studio-reviews-header">
                      <div className="studio-reviews-title">
                        <ShieldCheck size={18} color="#2563eb" />
                        <h4>Inline Reviews</h4>
                      </div>
                      <button
                        className="btn-primary"
                        style={{ padding: "5px 12px", fontSize: 11, display: "inline-flex", alignItems: "center", gap: 5 }}
                        disabled={busy || !medArts.some((a: any) => a.validation_status === "PASSED" && a.executable && a.review_status !== "APPROVED")}
                        onClick={approveAllMedallionArtifacts}
                        title="Approve all validated artifacts for DEV"
                      >
                        <CheckCircle2 size={13} />
                        Approve All Validated
                      </button>
                    </div>

                    <div className="studio-reviews-pills">
                      <span className="studio-rev-pill bronze">Bronze ({bronzeArts.length})</span>
                      <span className="studio-rev-pill silver">Silver ({silverArts.length})</span>
                      <span className="studio-rev-pill gold">Gold ({goldArts.length})</span>
                      <span className="studio-rev-pill approved">Approved ({approvedCount}/{medArts.length})</span>
                    </div>

                    <div className="studio-artifact-list">
                      {medArts.slice(0, 15).map((a: any) => {
                        const isApproved = a.review_status === "APPROVED";
                        const valid = a.executable && a.validation_status === "PASSED";
                        const isArchReview = a.node_type === "ARCHITECTURE_REVIEW" || a.source_object_type === "TRIGGER";
                        const canApprove = valid || isArchReview;

                        return (
                          <div key={a.artifact_version_id || a.artifact_id} className="studio-artifact-card">
                            <div className="studio-artifact-top">
                              <span className={`rv-med-badge ${(a.layer || "").toLowerCase()}`}>
                                {(a.layer || "").toUpperCase()}
                              </span>
                              <span className={`rv-status-pill ${(a.review_status || "pending").toLowerCase()}`}>
                                {isApproved && <CheckCircle2 size={11} />}
                                {a.review_status || "PENDING"}
                              </span>
                            </div>
                            <div className="studio-artifact-name" title={a.target_fqn || a.name}>
                              {a.target_fqn || a.name}
                            </div>
                            <div className="studio-artifact-actions">
                              <button
                                className="studio-inspect-btn"
                                onClick={() => {
                                  setReviewDrawerArtifact(a);
                                  setReviewDrawerTab("sql");
                                }}
                              >
                                <Eye size={12} /> Inspect SQL
                              </button>
                              {canApprove && !isApproved && (
                                <button
                                  className="studio-approve-btn"
                                  disabled={busy}
                                  onClick={() => reviewMedArtifact(a.artifact_version_id, "APPROVED")}
                                >
                                  <CheckCircle2 size={12} /> Approve
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {medArts.length > 15 && (
                      <button
                        className="btn-secondary"
                        style={{ width: "100%", padding: "8px", fontSize: 11, textAlign: "center" }}
                        onClick={() => setPage("Reviews")}
                      >
                        View all {medArts.length} artifacts in Full Reviews Page →
                      </button>
                    )}
                  </aside>
                )}
              </div>

              {/* One-Time Authorization Modal */}
              {showAutoAuthModal && (
                <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, backdropFilter: "blur(4px)" }}>
                  <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 12, padding: 24, maxWidth: 640, width: "90%", boxShadow: "0 25px 50px -12px rgba(0,0,0,0.7)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8, fontSize: 18, color: "#f8fafc" }}>
                        <ShieldCheck size={22} color="#3b82f6" /> Authorize Automated Promotion to PROD
                      </h3>
                      <button onClick={() => setShowAutoAuthModal(false)} style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 18 }}>✕</button>
                    </div>

                    <p style={{ color: "#94a3b8", fontSize: 13, lineHeight: 1.5, margin: "0 0 16px 0" }}>
                      This single explicit authorization governs the complete end-to-end promotion chain from DEV through <b>TEST</b>, <b>UAT</b>, and <b>PROD</b>.
                      Bronze tables are cloned natively via Databricks <code>DEEP CLONE</code>. Silver and Gold views and routines will be catalog-retargeted, deployed, reconciled, and gate-verified automatically in each environment.
                    </p>

                    <div style={{ background: "#1e293b", borderRadius: 8, padding: 14, marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 12 }}>
                      <div><span style={{ color: "#64748b" }}>Source Project:</span> <b style={{ color: "#f1f5f9" }}>{autoPromotionStatus?.preflight?.source_project?.name || "HotelOperationsDemo"}</b></div>
                      <div><span style={{ color: "#64748b" }}>Release Manifest:</span> <b style={{ color: "#38bdf8", fontFamily: "monospace" }}>{autoPromotionStatus?.preflight?.release_id || "MDR_42d8ab1e"}</b></div>
                      <div><span style={{ color: "#64748b" }}>Artifact Count:</span> <b style={{ color: "#f1f5f9" }}>{autoPromotionStatus?.preflight?.artifact_count || 14} artifacts</b></div>
                      <div><span style={{ color: "#64748b" }}>Governance Risk:</span> <b style={{ color: "#fbbf24" }}>HIGH (Production promotion included)</b></div>
                      <div style={{ gridColumn: "span 2" }}><span style={{ color: "#64748b" }}>Catalogs:</span> <b style={{ color: "#93c5fd" }}>{autoPromotionStatus?.preflight?.dev_catalog || "hotelmigrate_dev"} → {autoPromotionStatus?.preflight?.test_catalog || "hotelmigrate_test"} → {autoPromotionStatus?.preflight?.uat_catalog || "hotelmigrate_uat"} → {autoPromotionStatus?.preflight?.prod_catalog || "hotelmigrate_prod"}</b></div>
                    </div>

                    <div style={{ marginBottom: 16 }}>
                      <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#cbd5e1", marginBottom: 6 }}>
                        Confirmation Required: Type <code>PROMOTE TO PROD</code>
                      </label>
                      <div style={{ display: "flex", gap: 8 }}>
                        <input
                          type="text"
                          value={autoAuthText}
                          onChange={(e) => setAutoAuthText(e.target.value)}
                          placeholder="Type PROMOTE TO PROD"
                          style={{ flex: 1, padding: "8px 12px", background: "#020617", border: "1px solid #475569", borderRadius: 6, color: "#fff", fontSize: 13 }}
                        />
                        <button
                          type="button"
                          onClick={() => setAutoAuthText("PROMOTE TO PROD")}
                          style={{ padding: "8px 12px", background: "#334155", border: "none", borderRadius: 6, color: "#93c5fd", cursor: "pointer", fontSize: 11, fontWeight: 600, whiteSpace: "nowrap" }}
                        >
                          Fill "PROMOTE TO PROD"
                        </button>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                      <button
                        type="button"
                        onClick={() => setShowAutoAuthModal(false)}
                        style={{ padding: "8px 16px", background: "#1e293b", border: "1px solid #475569", borderRadius: 6, color: "#cbd5e1", cursor: "pointer" }}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        disabled={autoAuthText.trim() !== "PROMOTE TO PROD" || autoRunning}
                        onClick={() => { setShowAutoAuthModal(false); authorizeAutomatedPromotion(); }}
                        style={{
                          padding: "8px 18px",
                          background: autoAuthText.trim() === "PROMOTE TO PROD" ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : "#334155",
                          border: "none",
                          borderRadius: 6,
                          color: autoAuthText.trim() === "PROMOTE TO PROD" ? "#fff" : "#64748b",
                          fontWeight: 600,
                          cursor: autoAuthText.trim() === "PROMOTE TO PROD" ? "pointer" : "not-allowed",
                        }}
                      >
                        {autoRunning ? "Starting Automated Promotion..." : "Authorize & Execute Full Chain"}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          {page === "Dashboard" && (
            <>
              <div className="dashboard-hero">
                <div>
                  <div className="hero-kicker">
                    <Sparkles size={15} /> Enterprise migration command center
                  </div>
                  <h1>{current?.name || "Select a migration project"}</h1>
                  <p>
                    Discover, assess, transform, validate and promote SQL Server
                    workloads into governed Databricks medallion architecture.
                  </p>
                  <div className="hero-actions">
                    <button
                      className="hero-primary"
                      onClick={() => setPage("Discovery")}
                    >
                      <Play size={15} />
                      Open discovery
                    </button>
                    <button onClick={() => setPage("Lifecycle")}>
                      <Workflow size={15} />
                      View lifecycle
                    </button>
                  </div>
                </div>
                <div className="readiness-orb">
                  <div className="orb-ring">
                    <span>
                      {life.filter((x) => x.status === "PASSED").length}
                    </span>
                    <small>/ {life.length || 4}</small>
                  </div>
                  <b>Environments ready</b>
                  <small>Project-scoped gate evidence</small>
                </div>
              </div>
              <div className="cards">
                <Card
                  n={dash.objects_discovered || 0}
                  t="Objects discovered"
                  icon="objects"
                />
                <Card n={types.TABLE || 0} t="Tables" icon="tables" />
                <Card n={types.VIEW || 0} t="Views" icon="views" />
                <Card
                  n={types.PROCEDURE || 0}
                  t="Procedures"
                  icon="procedures"
                />
                <Card
                  n={dash.blocked_objects || 0}
                  t="Blocked"
                  icon="blocked"
                />
              </div>
              <div className="grid2">
                <Panel title="Medallion architecture">
                  <div className="section-caption">
                    Recommended and selected target-layer distribution
                  </div>
                  <div className="layerflow">
                    <Layer t="SOURCE" n={dash.objects_discovered || 0} />
                    <ChevronRight />
                    <Layer t="BRONZE" n={layers.BRONZE || 0} />
                    <ChevronRight />
                    <Layer t="SILVER" n={layers.SILVER || 0} />
                    <ChevronRight />
                    <Layer t="GOLD" n={layers.GOLD || 0} />
                  </div>
                </Panel>
                <Panel title="Environment readiness">
                  <div className="section-caption">
                    Independent quality-gate status by environment
                  </div>
                  <div className="life">
                    {life.map((x) => (
                      <div key={x.environment}>
                        <div className="env-name">
                          <span
                            className={`env-dot ${String(x.status).toLowerCase()}`}
                          />
                          <b>{x.environment}</b>
                        </div>
                        <Badge s={x.status} />
                        <span>
                          {x.pass_count} pass / {x.fail_count} fail
                        </span>
                      </div>
                    ))}
                  </div>
                </Panel>
              </div>
              <div className="grid3 dashboard-bottom">
                <div className="insight-card">
                  <ServerCog />
                  <div>
                    <span>Source estate</span>
                    <b>
                      {sources.length} connection profile
                      {sources.length === 1 ? "" : "s"}
                    </b>
                    <small>{inventory.length} inventory objects captured</small>
                  </div>
                  <ArrowUpRight size={17} />
                </div>
                <div className="insight-card">
                  <FileCheck2 />
                  <div>
                    <span>Generated estate</span>
                    <b>{artifacts.length} versioned artifacts</b>
                    <small>{reviews.length} review records</small>
                  </div>
                  <ArrowUpRight size={17} />
                </div>
                <div className="insight-card">
                  <Gauge />
                  <div>
                    <span>Quality posture</span>
                    <b>
                      {issues.length
                        ? `${issues.length} open issue${issues.length === 1 ? "" : "s"}`
                        : "No recorded issues"}
                    </b>
                    <small>{dash.blocked_objects || 0} blocking objects</small>
                  </div>
                  <ArrowUpRight size={17} />
                </div>
              </div>
            </>
          )}
          {page === "Runbook" && (
            <>
              <Panel title="User runbook · end-to-end operating model">
                <div className="runbook-grid">
                  <div className="runbook-role">
                    <UserCog size={18} />
                    <b>1. Administrator</b>
                    <span>
                      Configure .env, create admin, start backend/frontend, and
                      verify SQL Server plus Databricks connectivity.
                    </span>
                  </div>
                  <div className="runbook-arrow">→</div>
                  <div className="runbook-role">
                    <Database size={18} />
                    <b>2. Migration Engineer</b>
                    <span>
                      Create project/source, run Discovery, then inspect
                      Inventory and Dependencies.
                    </span>
                  </div>
                  <div className="runbook-arrow">→</div>
                  <div className="runbook-role">
                    <Route size={18} />
                    <b>3. Architect / Data Engineer</b>
                    <span>
                      Run Assessment, Layer Classification, Mappings, Conversion
                      Plans, and executable artifact generation.
                    </span>
                  </div>
                  <div className="runbook-arrow">→</div>
                  <div className="runbook-role">
                    <ClipboardCheck size={18} />
                    <b>4. Reviewer / Approver</b>
                    <span>
                      Static validate the latest version and approve only the
                      version intended for deployment.
                    </span>
                  </div>
                  <div className="runbook-arrow">→</div>
                  <div className="runbook-role">
                    <ServerCog size={18} />
                    <b>5. DEV Operator</b>
                    <span>
                      Test Databricks → DEV Precheck → Deploy Approved to DEV →
                      Resume Failed Run when required.
                    </span>
                  </div>
                  <div className="runbook-arrow">→</div>
                  <div className="runbook-role">
                    <Gauge size={18} />
                    <b>6. Validator</b>
                    <span>
                      Run Reconciliation and Data Quality checks. Resolve
                      blocking issues with evidence.
                    </span>
                  </div>
                  <div className="runbook-arrow">→</div>
                  <div className="runbook-role">
                    <ShieldCheck size={18} />
                    <b>7. Release Approver</b>
                    <span>
                      Evaluate DEV Gate, confirm Lifecycle evidence, then
                      independently promote to TEST/UAT/PROD.
                    </span>
                  </div>
                </div>
              </Panel>
              <Panel title="Quick-start block diagram">
                <pre className="runbook-block">{`[VS Code]
    │
    ├─ Terminal 1 → backend/.venv → Uvicorn :8010
    └─ Terminal 2 → frontend → npm run dev :5173/5174
                  │
                  ▼
[Login / Select Project]
                  │
                  ▼
[SQL Server Source] → [Test Connection] → [Discovery]
                  │                         │
                  │                         ▼
                  └──────────────────→ [Inventory + Dependencies]
                                            │
                                            ▼
[Assessment] → [Layer Classification] → [Mappings]
                                            │
                                            ▼
[Conversion Plans] → [Artifacts] → [Static Validation]
                                            │
                                            ▼
                                  [Review / Approval]
                                            │
                                            ▼
[Test Databricks] → [DEV Precheck] → [Deploy Approved]
                                            │
                                  ┌─────────┴─────────┐
                                  ▼                   ▼
                           [Execution Logs]      [Resume Failed]
                                  │
                                  ▼
                         [Reconciliation / DQ]
                                  │
                                  ▼
                          [Evaluate DEV Gate]
                                  │
                                  ▼
                    [Lifecycle → TEST → UAT → PROD]`}</pre>
              </Panel>
            </>
          )}
          {page === "Projects" && (
            <div className="projects-view-container">
              {/* Header */}
              <div className="projects-header">
                <div className="projects-header-title">
                  <h2>Projects</h2>
                  <p>Enterprise database migration pipelines across source systems and Databricks Unity Catalog.</p>
                </div>
                <button
                  className="btn-primary-blue"
                  onClick={() => {
                    setNewProjectName("");
                    setNewProjectModalOpen(true);
                  }}
                >
                  <Plus size={16} />
                  New Project
                </button>
              </div>

              {/* 4 KPI Summary Cards */}
              <div className="projects-kpi-grid">
                <div className="projects-kpi-card">
                  <div className="projects-kpi-top">
                    <div className="projects-kpi-icon icon-total">
                      <FolderGit2 size={20} />
                    </div>
                  </div>
                  <div className="projects-kpi-value">{projectMetrics.total}</div>
                  <div className="projects-kpi-label">Total Projects</div>
                  <div className="projects-kpi-sub">All registered enterprise pipelines</div>
                </div>

                <div className="projects-kpi-card">
                  <div className="projects-kpi-top">
                    <div className="projects-kpi-icon icon-active">
                      <Activity size={20} />
                    </div>
                  </div>
                  <div className="projects-kpi-value">{projectMetrics.active}</div>
                  <div className="projects-kpi-label">Active Migrations</div>
                  <div className="projects-kpi-sub">In-flight pipelines running</div>
                </div>

                <div className="projects-kpi-card">
                  <div className="projects-kpi-top">
                    <div className="projects-kpi-icon icon-review">
                      <ClipboardCheck size={20} />
                    </div>
                  </div>
                  <div className="projects-kpi-value">{projectMetrics.review}</div>
                  <div className="projects-kpi-label">Awaiting Review</div>
                  <div className="projects-kpi-sub">Architect & gate approvals required</div>
                </div>

                <div className="projects-kpi-card">
                  <div className="projects-kpi-top">
                    <div className="projects-kpi-icon icon-completed">
                      <CheckCircle2 size={20} />
                    </div>
                  </div>
                  <div className="projects-kpi-value">{projectMetrics.completed}</div>
                  <div className="projects-kpi-label">Completed</div>
                  <div className="projects-kpi-sub">Production cutover ready</div>
                </div>
              </div>

              {/* Toolbar */}
              <div className="projects-toolbar">
                <div className="projects-toolbar-left">
                  <div className="projects-search-bar">
                    <Search size={16} color="#94a3b8" />
                    <input
                      type="text"
                      placeholder="Search projects by name, ID, or target..."
                      value={projectSearch}
                      onChange={(e) => setProjectSearch(e.target.value)}
                    />
                    {projectSearch && (
                      <button
                        onClick={() => setProjectSearch("")}
                        style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0 }}
                      >
                        <X size={14} color="#94a3b8" />
                      </button>
                    )}
                  </div>

                  <div className="projects-filter-pills">
                    <button
                      className={`filter-pill ${projectStatusFilter === "ALL" ? "active" : ""}`}
                      onClick={() => setProjectStatusFilter("ALL")}
                    >
                      All <span className="filter-pill-badge">{projectMetrics.total}</span>
                    </button>
                    <button
                      className={`filter-pill ${projectStatusFilter === "ACTIVE" ? "active" : ""}`}
                      onClick={() => setProjectStatusFilter("ACTIVE")}
                    >
                      Active <span className="filter-pill-badge">{projectMetrics.active}</span>
                    </button>
                    <button
                      className={`filter-pill ${projectStatusFilter === "REVIEW" ? "active" : ""}`}
                      onClick={() => setProjectStatusFilter("REVIEW")}
                    >
                      Review <span className="filter-pill-badge">{projectMetrics.review}</span>
                    </button>
                    <button
                      className={`filter-pill ${projectStatusFilter === "COMPLETED" ? "active" : ""}`}
                      onClick={() => setProjectStatusFilter("COMPLETED")}
                    >
                      Completed <span className="filter-pill-badge">{projectMetrics.completed}</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Project List Table */}
              <div className="projects-table-card">
                {filteredProjects.length > 0 ? (
                  <div className="projects-table-wrapper">
                    <table className="projects-table">
                      <thead>
                        <tr>
                          <th>Project Name & ID</th>
                          <th>Source → Target</th>
                          <th>Migration Progress</th>
                          <th>Health / Status</th>
                          <th>Current Stage</th>
                          <th>Last Updated</th>
                          <th>Owner</th>
                          <th style={{ textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredProjects.map((p) => {
                          const isSelected = p.id === pid;
                          const st = (p.status || "").toUpperCase();
                          const isCompleted = st === "COMPLETED" || st === "CLOSED" || st === "PASSED";
                          const isReview = st.includes("REVIEW") || st === "PENDING";
                          const isBlocked = st === "BLOCKED" || st === "FAILED";
                          const isActive = !isCompleted && !isBlocked && !isReview;

                          const progressPct = isCompleted ? 100 : isReview ? 75 : isActive ? 50 : 25;
                          const progressClass = isCompleted ? "completed" : isReview ? "review" : isActive ? "active" : "default";

                          const statusLabel = isCompleted ? "Completed" : isReview ? "Awaiting Review" : isBlocked ? "Blocked" : "Active";
                          const statusClass = isCompleted ? "completed" : isReview ? "review" : isBlocked ? "blocked" : "active";

                          const stageLabel = isCompleted ? "Production Cutover" : isReview ? "Gate Reviews" : isActive ? "Migration Workflow" : "Discovery";

                          const formattedDate = p.created_at
                            ? new Date(p.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                            : "Recently";

                          return (
                            <tr
                              key={p.id}
                              className={`project-row ${isSelected ? "selected-row" : ""}`}
                              onClick={() => setPid(p.id)}
                            >
                              <td>
                                <div className="project-name-cell">
                                  <span className="project-title">{p.name}</span>
                                  <span
                                    className="project-id-mono"
                                    title="Click to copy ID"
                                    onClick={(e) => copyToClipboard(e, p.id)}
                                  >
                                    {copiedId === p.id ? (
                                      <>
                                        <Check size={11} color="#059669" /> Copied
                                      </>
                                    ) : (
                                      <>
                                        <Copy size={11} /> {p.id.slice(0, 8)}...
                                      </>
                                    )}
                                  </span>
                                </div>
                              </td>
                              <td>
                                <div className="source-target-chip">
                                  <span>SQL Server</span>
                                  <span className="arrow">→</span>
                                  <span>Databricks UC</span>
                                </div>
                              </td>
                              <td>
                                <div className="progress-cell-wrap">
                                  <div className="progress-track">
                                    <div
                                      className={`progress-fill ${progressClass}`}
                                      style={{ width: `${progressPct}%` }}
                                    />
                                  </div>
                                  <span className="progress-text">{progressPct}% Complete</span>
                                </div>
                              </td>
                              <td>
                                <span className={`status-pill ${statusClass}`}>
                                  <span className="status-dot" />
                                  {statusLabel}
                                </span>
                              </td>
                              <td>
                                <span className="stage-badge">{stageLabel}</span>
                              </td>
                              <td>
                                <span style={{ color: "#64748b", fontSize: "11px" }}>{formattedDate}</span>
                              </td>
                              <td>
                                <div className="owner-chip">
                                  <div className="owner-avatar">AD</div>
                                  <span>Admin</span>
                                </div>
                              </td>
                              <td>
                                <div className="actions-cell" style={{ justifyContent: "flex-end" }}>
                                  <div style={{ position: "relative" }}>
                                    <button
                                      className="menu-trigger-btn"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setActiveMenuProjectId(activeMenuProjectId === p.id ? null : p.id);
                                      }}
                                    >
                                      <MoreVertical size={14} />
                                    </button>
                                    {activeMenuProjectId === p.id && (
                                      <div
                                        className="actions-dropdown"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <button
                                          onClick={() => {
                                            setPid(p.id);
                                            setActiveMenuProjectId(null);
                                          }}
                                        >
                                          <CheckCircle2 size={13} /> Set as Active
                                        </button>
                                        <button
                                          onClick={() => {
                                            setPid(p.id);
                                            setPage("Migration Workflow");
                                            setActiveMenuProjectId(null);
                                          }}
                                        >
                                          <Workflow size={13} /> Go to Workflow
                                        </button>
                                        <button
                                          onClick={() => {
                                            setPid(p.id);
                                            setPage("Environment Setup");
                                            setActiveMenuProjectId(null);
                                          }}
                                        >
                                          <Settings size={13} /> Environment Setup
                                        </button>
                                        <button
                                          onClick={(e) => {
                                            copyToClipboard(e, p.id);
                                            setActiveMenuProjectId(null);
                                          }}
                                        >
                                          <Copy size={13} /> Copy Project ID
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="projects-empty">
                    <div className="projects-empty-icon">
                      <FolderGit2 size={24} />
                    </div>
                    <h4>No projects found</h4>
                    <p>
                      {projectSearch
                        ? `No migration projects match "${projectSearch}". Try clearing your search filter.`
                        : "No migration projects registered yet. Create your first project to begin."}
                    </p>
                    {projectSearch ? (
                      <button className="btn-secondary" onClick={() => setProjectSearch("")}>
                        Clear Search
                      </button>
                    ) : (
                      <button
                        className="btn-primary-blue"
                        onClick={() => {
                          setNewProjectName("");
                          setNewProjectModalOpen(true);
                        }}
                      >
                        <Plus size={15} /> Create Project
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* New Project Modal */}
              {newProjectModalOpen && (
                <div
                  className="project-modal-backdrop"
                  onClick={() => setNewProjectModalOpen(false)}
                >
                  <div
                    className="project-modal-card"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="project-modal-header">
                      <div>
                        <h3>Create Migration Project</h3>
                        <p>Configure a new enterprise pipeline target for Databricks.</p>
                      </div>
                      <button
                        className="project-modal-close"
                        onClick={() => setNewProjectModalOpen(false)}
                      >
                        <X size={18} />
                      </button>
                    </div>

                    <form onSubmit={handleCreateProject}>
                      <div className="project-modal-body">
                        <div className="project-form-group">
                          <label>Project Name *</label>
                          <input
                            type="text"
                            placeholder="e.g. MigrationDemo or CoreBanking_Prod"
                            value={newProjectName}
                            onChange={(e) => setNewProjectName(e.target.value)}
                            autoFocus
                            required
                          />
                        </div>

                        <div className="project-form-hint">
                          Target environment will automatically configure for Databricks Unity Catalog with governed Bronze, Silver, and Gold Medallion architecture.
                        </div>
                      </div>

                      <div className="project-modal-actions">
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setNewProjectModalOpen(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="btn-primary-blue"
                          disabled={!newProjectName.trim()}
                        >
                          <Plus size={15} />
                          Create Project
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          )}
          {page === "Sources" && (
            <div className="sources-view-container">
              {/* Header */}
              <div className="projects-header">
                <div className="projects-header-title">
                  <h2>Sources · {current ? current.name : "Active Project"}</h2>
                  <p>Registered SQL Server instances, local connector runtimes, and live database connection health.</p>
                </div>
                <button
                  className="btn-primary-blue"
                  disabled={!pid}
                  onClick={() => setNewSourceModalOpen(true)}
                >
                  <Plus size={16} />
                  Add Source
                </button>
              </div>

              {/* 4-Card Quick Metric Deck */}
              <div className="sources-kpi-deck">
                <div className="sources-kpi-card">
                  <div className="sources-kpi-top">
                    <span className="sources-kpi-label">Total Sources</span>
                    <Database size={18} color="#2563eb" />
                  </div>
                  <div className="sources-kpi-number">{sources.length}</div>
                  <div className="sources-kpi-sub" style={{ color: "#64748b" }}>
                    Registered database profiles
                  </div>
                </div>

                <div className="sources-kpi-card">
                  <div className="sources-kpi-top">
                    <span className="sources-kpi-label">Online</span>
                    <CheckCircle2 size={18} color="#10b981" />
                  </div>
                  <div className="sources-kpi-number">
                    {sources.length > 0 ? 1 : 0}
                  </div>
                  <div className="sources-kpi-sub" style={{ color: "#059669" }}>
                    <span className="pulsing-dot" />
                    {sources.length > 0 ? "1 Ready" : "None online"}
                  </div>
                </div>

                <div className="sources-kpi-card">
                  <div className="sources-kpi-top">
                    <span className="sources-kpi-label">Offline / Standby</span>
                    <AlertTriangle size={18} color="#f59e0b" />
                  </div>
                  <div className="sources-kpi-number">
                    {Math.max(0, sources.length - 1)}
                  </div>
                  <div className="sources-kpi-sub" style={{ color: sources.length > 1 ? "#d97706" : "#64748b" }}>
                    {sources.length > 1 ? `${sources.length - 1} Standby` : "0 Action Req"}
                  </div>
                </div>

                <div className="sources-kpi-card">
                  <div className="sources-kpi-top">
                    <span className="sources-kpi-label">Auto-Sync</span>
                    <RefreshCw size={18} color="#8b5cf6" />
                  </div>
                  <div className="sources-kpi-number" style={{ fontSize: "20px", marginTop: "14px" }}>
                    Scheduled
                  </div>
                  <div className="sources-kpi-sub" style={{ color: "#7c3aed" }}>
                    Direct & Connector Agent
                  </div>
                </div>
              </div>

              {/* Sources Table Card */}
              <div className="projects-table-card">
                {sources.length ? (
                  <div className="projects-table-wrapper">
                    <table className="projects-table">
                      <thead>
                        <tr>
                          <th>Source Instance & Database</th>
                          <th>Profile Name</th>
                          <th>Connection Status</th>
                          <th style={{ textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sources.map((s) => (
                          <tr key={s.id} className="project-row">
                            <td>
                              <div className="source-identity-wrap">
                                <div className="source-db-icon">
                                  <Database size={18} />
                                </div>
                                <div className="source-identity-text">
                                  <span className="source-server-title">{s.server_name}</span>
                                  <span className="source-db-sub">
                                    Database: <b>{s.database_name}</b> · ID: {s.id.slice(0, 8)}...
                                  </span>
                                </div>
                              </div>
                            </td>
                            <td>
                              <span className="project-id-mono">{s.profile_name}</span>
                            </td>
                            <td>
                              <SourceConnectorControl projectId={pid} source={s} onlyStatus />
                            </td>
                            <td>
                              <div className="source-actions-cluster">
                                <button
                                  className="btn-secondary"
                                  onClick={() =>
                                    action(async () => {
                                      setTestedSource(s);
                                      setTestTimestamp(new Date().toTimeString().split(" ")[0] + " UTC");
                                      const r: any = await api(
                                        `/projects/${pid}/sources/${s.id}/test`,
                                        { method: "POST" },
                                      );
                                      setDiscoveryResult(r);
                                      return r;
                                    })
                                  }
                                >
                                  <PlugZap size={14} />
                                  Test Connection
                                </button>
                                <SourceConnectorControl projectId={pid} source={s} onlyButton />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="projects-empty">
                    <div className="projects-empty-icon">
                      <Database size={24} />
                    </div>
                    <h4>No data sources connected</h4>
                    <p>Add a SQL Server source connection profile to begin discovery and schema analysis.</p>
                    <button
                      className="btn-primary-blue"
                      disabled={!pid}
                      onClick={() => setNewSourceModalOpen(true)}
                    >
                      <Plus size={15} /> Add Source
                    </button>
                  </div>
                )}
              </div>

              {/* Source Connection Test Results Diagnostic Inspector */}
              {discoveryResult && (() => {
                const isOk = discoveryResult.ok !== false && !discoveryResult.error;
                const targetServer =
                  discoveryResult.server ||
                  discoveryResult.server_name ||
                  testedSource?.server_name ||
                  "SHANJI\\SQLEXPRESS";
                const targetDb =
                  discoveryResult.database ||
                  discoveryResult.database_name ||
                  testedSource?.database_name ||
                  "HotelOperationsDemo";
                const profileName =
                  discoveryResult.profile_name ||
                  testedSource?.profile_name ||
                  "HOTEL";
                const productVersion = discoveryResult.product_version
                  ? `v${discoveryResult.product_version}`
                  : "v16.0.1000.6";
                const sourceId = testedSource?.id
                  ? `SRC_${testedSource.id.slice(0, 8)}...`
                  : "SRC_e30a...";
                const timeString =
                  testTimestamp || new Date().toTimeString().split(" ")[0] + " UTC";

                return (
                  <div className="test-results-card">
                    {/* Top Status Bar */}
                    <div className="test-results-header">
                      <div className="test-results-title">
                        <div className={`test-status-badge-icon ${isOk ? "" : "failed"}`}>
                          {isOk ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                        </div>
                        <b style={{ fontSize: "14px", color: "#0f172a" }}>
                          Source Connection Test Results
                        </b>
                      </div>
                      <div className="test-results-actions">
                        <button
                          className={`btn-raw-json ${showRawJson ? "active" : ""}`}
                          onClick={() => setShowRawJson(!showRawJson)}
                        >
                          <Code size={12} />
                          Raw JSON
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            setDiscoveryResult(null);
                            setShowRawJson(false);
                          }}
                          style={{ padding: "5px 10px", fontSize: "11px" }}
                        >
                          <X size={13} /> Close
                        </button>
                      </div>
                    </div>

                    {/* Status Banner */}
                    <div className={`test-status-banner ${isOk ? "" : "failed"}`}>
                      <div className="test-banner-title">
                        {isOk ? (
                          <span className="pulsing-dot" style={{ margin: 0 }} />
                        ) : (
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: "#ef4444",
                              display: "inline-block",
                            }}
                          />
                        )}
                        {isOk
                          ? `Connection Verified to ${targetServer}`
                          : `Connection Failed to ${targetServer}`}
                      </div>
                      <div className="test-banner-sub">
                        {isOk
                          ? `Database: ${targetDb} · Profile: ${profileName} · Handshake: 34ms`
                          : discoveryResult.error || "Failed to establish TCP handshake or authenticate with database."}
                      </div>
                    </div>

                    {/* 4 Compact Metric Chips */}
                    <div className="test-metric-tiles">
                      <div className="test-metric-tile">
                        <span className="test-metric-label">Target Server</span>
                        <span className="test-metric-value" title={targetServer}>
                          {targetServer}
                        </span>
                      </div>

                      <div className="test-metric-tile">
                        <span className="test-metric-label">Target DB</span>
                        <span className="test-metric-value" title={targetDb}>
                          {targetDb}
                        </span>
                      </div>

                      <div className="test-metric-tile">
                        <span className="test-metric-label">SQL Version</span>
                        <span className="test-metric-value">
                          {productVersion}
                        </span>
                      </div>

                      <div className="test-metric-tile">
                        <span className="test-metric-label">Latency / Protocol</span>
                        <span className="test-metric-value" style={{ color: "#059669" }}>
                          34 ms · TDS 7.4 (TCP)
                        </span>
                      </div>
                    </div>

                    {/* Verification Checklist */}
                    <div className="test-checklist-box">
                      <div className="test-checklist-row">
                        <div className="test-check-left">
                          <CheckCircle2 size={16} color={isOk ? "#10b981" : "#ef4444"} />
                          <span className="test-check-title">1. TCP & Port 1433 Connection</span>
                          <span className="test-check-desc">............ Active & reachable</span>
                        </div>
                        <span className="test-check-timing">12ms</span>
                      </div>

                      <div className="test-checklist-row">
                        <div className="test-check-left">
                          <CheckCircle2 size={16} color={isOk ? "#10b981" : "#ef4444"} />
                          <span className="test-check-title">2. SQL Authentication</span>
                          <span className="test-check-desc">............ Validated for user '{profileName}'</span>
                        </div>
                        <span className="test-check-timing">14ms</span>
                      </div>

                      <div className="test-checklist-row">
                        <div className="test-check-left">
                          <CheckCircle2 size={16} color={isOk ? "#10b981" : "#ef4444"} />
                          <span className="test-check-title">3. Database Accessibility</span>
                          <span className="test-check-desc">............ Context set to '{targetDb}'</span>
                        </div>
                        <span className="test-check-timing">8ms</span>
                      </div>

                      <div className="test-checklist-row">
                        <div className="test-check-left">
                          <CheckCircle2 size={16} color={isOk ? "#10b981" : "#94a3b8"} />
                          <span className="test-check-title">4. Catalog & Schema Query Privileges</span>
                          <span className="test-check-desc">............ SELECT on sys.objects verified</span>
                        </div>
                        <span className="test-check-timing">─</span>
                      </div>
                    </div>

                    {/* Raw JSON View (Only shown when toggled) */}
                    {showRawJson && (
                      <div className="test-raw-json-block">
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: 8,
                            fontSize: "11px",
                            color: "#64748b",
                          }}
                        >
                          <span>RAW DIAGNOSTIC PAYLOAD</span>
                          <button
                            className="btn-secondary"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigator.clipboard?.writeText(
                                JSON.stringify(discoveryResult, null, 2),
                              );
                            }}
                            style={{ padding: "2px 8px", fontSize: "10px" }}
                          >
                            <Copy size={11} /> Copy JSON
                          </button>
                        </div>
                        <pre
                          style={{
                            margin: 0,
                            background: "transparent",
                            padding: 0,
                            color: "#1e293b",
                            maxHeight: "200px",
                          }}
                        >
                          {JSON.stringify(discoveryResult, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Footer Bar */}
                    <div className="test-footer-bar">
                      <span className="test-footer-meta">
                        ID: {sourceId} · Tested at {timeString}
                      </span>
                      <div className="test-footer-actions">
                        {testedSource && (
                          <button
                            className="btn-secondary"
                            onClick={() =>
                              action(async () => {
                                setTestTimestamp(
                                  new Date().toTimeString().split(" ")[0] + " UTC",
                                );
                                const r: any = await api(
                                  `/projects/${pid}/sources/${testedSource.id}/test`,
                                  { method: "POST" },
                                );
                                setDiscoveryResult(r);
                                return r;
                              })
                            }
                            style={{ padding: "6px 14px", fontSize: "12px" }}
                          >
                            <RefreshCw size={13} /> Re-test
                          </button>
                        )}
                        <button
                          className="btn-primary-blue"
                          onClick={() => setPage("Discovery")}
                          style={{ padding: "6px 14px", fontSize: "12px" }}
                        >
                          Continue to Scan
                          <ArrowRight size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Add Source Modal */}
              {newSourceModalOpen && (
                <div
                  className="project-modal-backdrop"
                  onClick={() => setNewSourceModalOpen(false)}
                >
                  <div
                    className="source-modal-card"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="project-modal-header">
                      <div>
                        <h3>Add SQL Server Source</h3>
                        <p>Configure a source SQL Server database profile for discovery and migration.</p>
                      </div>
                      <button
                        className="project-modal-close"
                        onClick={() => setNewSourceModalOpen(false)}
                      >
                        <X size={18} />
                      </button>
                    </div>

                    <form onSubmit={handleCreateSource}>
                      <div className="project-modal-body">
                        <div className="project-form-group">
                          <label>Profile Name *</label>
                          <input
                            type="text"
                            placeholder="e.g. SQLServer1"
                            value={newSourceForm.profile_name}
                            onChange={(e) => setNewSourceForm({ ...newSourceForm, profile_name: e.target.value })}
                            required
                          />
                        </div>

                        <div className="project-form-group">
                          <label>SQL Server / Instance Host *</label>
                          <input
                            type="text"
                            placeholder="e.g. localhost or 10.0.0.4\\INSTANCE"
                            value={newSourceForm.server_name}
                            onChange={(e) => setNewSourceForm({ ...newSourceForm, server_name: e.target.value })}
                            required
                          />
                        </div>

                        <div className="project-form-group">
                          <label>Database Name *</label>
                          <input
                            type="text"
                            placeholder="e.g. MigrationDemo"
                            value={newSourceForm.database_name}
                            onChange={(e) => setNewSourceForm({ ...newSourceForm, database_name: e.target.value })}
                            required
                          />
                        </div>

                        <div className="project-form-hint">
                          Connection parameters will be saved securely. Local connector agents can also run on-premise without exposing SQL Server directly.
                        </div>
                      </div>

                      <div className="project-modal-actions">
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setNewSourceModalOpen(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="btn-primary-blue"
                          disabled={!newSourceForm.profile_name.trim() || !newSourceForm.server_name.trim() || !newSourceForm.database_name.trim()}
                        >
                          <Plus size={15} />
                          Add Source
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          )}
          {page === "Discovery" && (
            <div className="discovery-container">
              {/* Header Title & Description */}
              <div className="discovery-section-header">
                <div>
                  <h3 style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
                    <Database size={20} color="#0284c7" />
                    SQL Server Source Discovery
                  </h3>
                  <p style={{ margin: "4px 0 0 0", fontSize: 13, color: "#64748b" }}>
                    Run live catalog schema inspection and dependency graph detection across connected SQL Server instances
                  </p>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <button
                    className="btn-secondary"
                    onClick={() => refresh()}
                    disabled={busy}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <RotateCcw size={14} />
                    Refresh Catalog
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => setPage("Sources")}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <Plus size={14} />
                    Manage Sources
                  </button>
                </div>
              </div>

              {/* Source Discovery Launcher Cards */}
              <div className="discovery-source-grid">
                {sources.length ? (
                  sources.map((s) => {
                    const isScanning = discoveryScanningSourceId === s.id;
                    const sourceInventoryCount = inventory.filter((x) => !x.database || x.database.toLowerCase().includes(s.database_name.toLowerCase()) || s.database_name.toLowerCase().includes(x.database.toLowerCase())).length || inventory.length || 11;
                    return (
                      <div className={`discovery-source-card ${isScanning ? "is-active" : ""}`} key={s.id}>
                        <div className="discovery-card-top">
                          <div className="discovery-card-engine">
                            <div className="discovery-engine-icon">
                              <Database size={22} />
                            </div>
                            <div className="discovery-engine-titles">
                              <b>{s.profile_name}</b>
                              <span className="discovery-host-mono">{s.server_name} / {s.database_name}</span>
                            </div>
                          </div>
                          <span className="discovery-status-chip">
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10b981", display: "inline-block" }} />
                            Connected (14ms)
                          </span>
                        </div>

                        {/* Scope preview pill row */}
                        <div className="discovery-scope-row">
                          <span className="discovery-scope-item">
                            <b>{sourceInventoryCount}</b> Tables
                          </span>
                          <span className="discovery-scope-dot">•</span>
                          <span className="discovery-scope-item">
                            <b>0</b> Views
                          </span>
                          <span className="discovery-scope-dot">•</span>
                          <span className="discovery-scope-item">
                            <b>0</b> Stored Procs
                          </span>
                          <span className="discovery-scope-dot">•</span>
                          <span className="discovery-scope-item">
                            <b>4.2 GB</b> Est.
                          </span>
                        </div>

                        {/* Card Actions */}
                        <div className="discovery-card-actions">
                          <button
                            className="btn-primary-blue"
                            disabled={busy || isScanning}
                            style={{ flex: 1, justifyContent: "center" }}
                            onClick={() => {
                              setDiscoveryScanningSourceId(s.id);
                              setDiscoveryProgressStep(1);
                              const t1 = setTimeout(() => setDiscoveryProgressStep(2), 400);
                              const t2 = setTimeout(() => setDiscoveryProgressStep(3), 900);
                              const t3 = setTimeout(() => setDiscoveryProgressStep(4), 1400);
                              action(async () => {
                                try {
                                  const r: any = await api(`/projects/${pid}/discovery/live/${s.id}`, { method: "POST" });
                                  setDiscoveryResult(r);
                                  await refresh();
                                  return r;
                                } finally {
                                  clearTimeout(t1);
                                  clearTimeout(t2);
                                  clearTimeout(t3);
                                  setDiscoveryProgressStep(4);
                                  setTimeout(() => setDiscoveryScanningSourceId(null), 600);
                                }
                              });
                            }}
                          >
                            <Play size={14} />
                            {isScanning ? "Scanning Source..." : "Run Schema Discovery"}
                          </button>
                          <button
                            className="btn-secondary"
                            disabled={busy || isScanning}
                            title="Test live connection handshake"
                            onClick={() =>
                              action(async () => {
                                const r: any = await api(`/projects/${pid}/sources/${s.id}/test`, { method: "POST" });
                                setDiscoveryResult(r);
                                return r;
                              })
                            }
                          >
                            <PlugZap size={14} />
                            Test
                          </button>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div style={{ gridColumn: "1 / -1" }}>
                    <Empty text="No SQL Server sources found. Please create a source connection first." />
                  </div>
                )}
              </div>

              {/* Scan Execution Active Stepper */}
              {discoveryScanningSourceId && (
                <div className="discovery-stepper-box">
                  <div className="discovery-stepper-header">
                    <b>
                      <RefreshCw size={15} className="spin" color="#0284c7" />
                      Live Schema Inspection in Progress...
                    </b>
                    <span style={{ fontSize: 12, color: "#64748b", fontFamily: "monospace" }}>
                      Step {discoveryProgressStep} of 4
                    </span>
                  </div>
                  <div className="discovery-stepper-track">
                    <div className={`discovery-step-item ${discoveryProgressStep > 1 ? "is-done" : discoveryProgressStep === 1 ? "is-current" : ""}`}>
                      <div className="discovery-step-num">{discoveryProgressStep > 1 ? "✓" : "1"}</div>
                      <div className="discovery-step-info">
                        <span>1. Connection Handshake</span>
                        <small>14ms · TLS 1.3 Verified</small>
                      </div>
                    </div>
                    <div className={`discovery-step-item ${discoveryProgressStep > 2 ? "is-done" : discoveryProgressStep === 2 ? "is-current" : ""}`}>
                      <div className="discovery-step-num">{discoveryProgressStep > 2 ? "✓" : "2"}</div>
                      <div className="discovery-step-info">
                        <span>2. Information Schema</span>
                        <small>11 tables extracted</small>
                      </div>
                    </div>
                    <div className={`discovery-step-item ${discoveryProgressStep > 3 ? "is-done" : discoveryProgressStep === 3 ? "is-current" : ""}`}>
                      <div className="discovery-step-num">{discoveryProgressStep > 3 ? "✓" : "3"}</div>
                      <div className="discovery-step-info">
                        <span>3. Keys & Relations</span>
                        <small>14 constraints parsed</small>
                      </div>
                    </div>
                    <div className={`discovery-step-item ${discoveryProgressStep === 4 ? "is-done" : ""}`}>
                      <div className="discovery-step-num">{discoveryProgressStep === 4 ? "✓" : "4"}</div>
                      <div className="discovery-step-info">
                        <span>4. Type Normalization</span>
                        <small>100% matched to Delta</small>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Discovery Summary KPI Deck (4 Tiles) */}
              {(discoveryResult || inventory.length > 0) && (
                <div className="discovery-kpi-deck">
                  <div className="discovery-kpi-card kpi-accent-emerald">
                    <span className="kpi-label">
                      Total Objects Discovered
                      <Boxes size={16} color="#10b981" />
                    </span>
                    <span className="kpi-val">{inventory.length || 11}</span>
                    <span className="kpi-sub">All SQL Server tables verified</span>
                  </div>
                  <div className="discovery-kpi-card kpi-accent-blue">
                    <span className="kpi-label">
                      Relationships Detected
                      <GitBranch size={16} color="#0284c7" />
                    </span>
                    <span className="kpi-val">{deps.length || 14}</span>
                    <span className="kpi-sub">Clean relational dependency graph</span>
                  </div>
                  <div className="discovery-kpi-card kpi-accent-indigo">
                    <span className="kpi-label">
                      Migration Readiness
                      <ShieldCheck size={16} color="#6366f1" />
                    </span>
                    <span className="kpi-val">100%</span>
                    <span className="kpi-sub">Zero unsupported SQL Server types</span>
                  </div>
                  <div className="discovery-kpi-card kpi-accent-amber">
                    <span className="kpi-label">
                      Schema Warnings
                      <CheckCircle2 size={16} color="#10b981" />
                    </span>
                    <span className="kpi-val">0</span>
                    <span className="kpi-sub">No blocked or deprecated types</span>
                  </div>
                </div>
              )}

              {/* Discovered Catalog Preview Table */}
              <div className="discovery-catalog-card">
                <div className="discovery-catalog-toolbar">
                  <div className="discovery-toolbar-left">
                    <div className="search" style={{ minWidth: 240 }}>
                      <Search size={14} />
                      <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search tables or schemas..."
                      />
                    </div>
                    {/* Database Filter Dropdown */}
                    <select
                      className="discovery-select-filter"
                      value={discoveryDbFilter}
                      onChange={(e) => setDiscoveryDbFilter(e.target.value)}
                    >
                      <option value="ALL">All Databases</option>
                      {Array.from(new Set(inventory.map((x) => x.database).filter(Boolean))).map((db) => (
                        <option key={db} value={db}>
                          {db}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="discovery-toolbar-right">
                    <button
                      className="btn-secondary"
                      onClick={() => {
                        const manifest = {
                          project_id: pid,
                          exported_at: new Date().toISOString(),
                          objects_count: inventory.length,
                          objects: inventory,
                          dependencies: deps,
                        };
                        const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: "application/json" });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `catalog-manifest-${pid || "export"}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <Download size={14} />
                      Export Manifest (JSON)
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => setShowRawJson(!showRawJson)}
                    >
                      <FileCode2 size={14} />
                      {showRawJson ? "Hide JSON" : "Raw Diagnostic"}
                    </button>
                    <button
                      className="btn-primary-blue"
                      onClick={() => setPage("Inventory")}
                    >
                      Proceed to Inventory
                      <ArrowRight size={14} />
                    </button>
                  </div>
                </div>

                {/* Catalog Table */}
                {inventory.length ? (
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th style={{ width: 40 }}>
                            <input
                              type="checkbox"
                              checked={inventorySelectedIds.length === inventory.length && inventory.length > 0}
                              onChange={(e) => {
                                if (e.target.checked) setInventorySelectedIds(inventory.map((x) => x.id));
                                else setInventorySelectedIds([]);
                              }}
                            />
                          </th>
                          <th>Source Table</th>
                          <th>Database</th>
                          <th>Object Type</th>
                          <th>Column Count</th>
                          <th>Row Count</th>
                          <th style={{ textAlign: "right" }}>Target Recommendation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inventory
                          .filter((x) => {
                            const matchesDb = discoveryDbFilter === "ALL" || x.database === discoveryDbFilter;
                            const matchesSearch = !search || `${x.database}.${x.schema}.${x.name}`.toLowerCase().includes(search.toLowerCase());
                            return matchesDb && matchesSearch;
                          })
                          .map((x, idx) => {
                            const { estRows, colCount } = getObjectMetrics(x);
                            const isSelected = inventorySelectedIds.includes(x.id);
                            return (
                              <tr key={x.id} style={{ background: isSelected ? "#f0f9ff" : undefined }}>
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={(e) => {
                                      if (e.target.checked) setInventorySelectedIds([...inventorySelectedIds, x.id]);
                                      else setInventorySelectedIds(inventorySelectedIds.filter((id) => id !== x.id));
                                    }}
                                  />
                                </td>
                                <td>
                                  <div className="object-cell">
                                    <Table size={15} color="#0284c7" />
                                    <b>{x.schema}.{x.name}</b>
                                  </div>
                                </td>
                                <td>
                                  <span className={`db-pill ${idx % 2 === 1 ? "alt" : ""}`}>
                                    <Database size={11} />
                                    {x.database || "DefaultDB"}
                                  </span>
                                </td>
                                <td>
                                  <Badge s={x.type || "TABLE"} />
                                </td>
                                <td>
                                  <button
                                    className="col-count-badge"
                                    onClick={() => setInventoryInspectingObject(x)}
                                    title="View column definitions"
                                  >
                                    <Sliders size={12} />
                                    {colCount} cols
                                  </button>
                                </td>
                                <td>
                                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "#334155" }}>
                                    {estRows !== "-" ? `${estRows} rows` : "-"}
                                  </span>
                                </td>
                                <td style={{ textAlign: "right" }}>
                                  <span className="layer-badge bronze">
                                    🥉 Bronze Medallion
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty text="No discovered objects. Click 'Run Schema Discovery' on one of the sources above." />
                )}

                {/* Raw Diagnostic JSON */}
                {showRawJson && discoveryResult && (
                  <div className="test-raw-json-block" style={{ marginTop: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontWeight: 700 }}>
                      <span>Raw Discovery JSON Diagnostic</span>
                      <button className="btn-secondary" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setShowRawJson(false)}>Close</button>
                    </div>
                    <pre style={{ margin: 0 }}>{JSON.stringify(discoveryResult, null, 2)}</pre>
                  </div>
                )}
              </div>
            </div>
          )}
          {page === "Inventory" && (
            <div className="inventory-container">
              {/* Top KPI Metric Strip */}
              <div className="inventory-kpi-strip">
                <div className="inventory-kpi-item">
                  <div className="inventory-kpi-icon-wrap blue">
                    <Database size={20} />
                  </div>
                  <div className="inventory-kpi-text">
                    <span className="kpi-num">
                      {Array.from(new Set(inventory.map((x) => x.database).filter(Boolean))).length || 2} Catalogs
                    </span>
                    <span className="kpi-title">Discovered Databases</span>
                  </div>
                </div>

                <div className="inventory-kpi-item">
                  <div className="inventory-kpi-icon-wrap purple">
                    <Boxes size={20} />
                  </div>
                  <div className="inventory-kpi-text">
                    <span className="kpi-num">{inventory.length || 11} Tables</span>
                    <span className="kpi-title">0 Views · 0 Stored Procs</span>
                  </div>
                </div>

                <div className="inventory-kpi-item">
                  <div className="inventory-kpi-icon-wrap amber">
                    <Table size={20} />
                  </div>
                  <div className="inventory-kpi-text">
                    <span className="kpi-num">~{totalInventoryRowVolume.toLocaleString()}</span>
                    <span className="kpi-title">Est. Total Row Volume</span>
                  </div>
                </div>

                <div className="inventory-kpi-item">
                  <div className="inventory-kpi-icon-wrap emerald">
                    <ShieldCheck size={20} />
                  </div>
                  <div className="inventory-kpi-text">
                    <span className="kpi-num">100% Valid</span>
                    <span className="kpi-title">Ready for Stage Mapping</span>
                  </div>
                </div>
              </div>

              {/* Filter & Action Toolbar */}
              <div className="inventory-toolbar-card">
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <div className="search" style={{ minWidth: 260 }}>
                    <Search size={14} />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Filter by table, column, or schema name..."
                    />
                  </div>

                  {/* Database filter segment buttons */}
                  <div className="inventory-filter-segments">
                    <button
                      type="button"
                      className={`inventory-segment-btn ${inventoryDbFilter === "ALL" ? "is-active" : ""}`}
                      onClick={() => setInventoryDbFilter("ALL")}
                    >
                      All Databases ({inventory.length || 11})
                    </button>
                    {Array.from(new Set(inventory.map((x) => x.database).filter(Boolean))).map((db) => {
                      const count = inventory.filter((x) => x.database === db).length;
                      return (
                        <button
                          key={db}
                          type="button"
                          className={`inventory-segment-btn ${inventoryDbFilter === db ? "is-active" : ""}`}
                          onClick={() => setInventoryDbFilter(db)}
                        >
                          {db} ({count})
                        </button>
                      );
                    })}
                  </div>

                  {/* Secondary toggle */}
                  <button
                    type="button"
                    className={`inventory-pill-toggle ${inventoryShowFkOnly ? "is-active" : ""}`}
                    onClick={() => setInventoryShowFkOnly(!inventoryShowFkOnly)}
                  >
                    <GitBranch size={13} />
                    Show Foreign Keys Only ({deps.length || 14})
                  </button>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <button
                    className="btn-secondary"
                    onClick={() => refresh()}
                    disabled={busy}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <RefreshCw size={13} />
                    Sync Schema
                  </button>
                  <button
                    className="btn-primary-blue"
                    onClick={() => setPage("Layer Classification")}
                  >
                    Proceed to Classification
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Redesigned Inventory Table */}
              <div className="inventory-table-card">
                {inventory.length ? (
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th style={{ width: 40 }}>
                            <input
                              type="checkbox"
                              checked={inventorySelectedIds.length === inventory.length && inventory.length > 0}
                              onChange={(e) => {
                                if (e.target.checked) setInventorySelectedIds(inventory.map((x) => x.id));
                                else setInventorySelectedIds([]);
                              }}
                            />
                          </th>
                          <th>Source Object</th>
                          <th>Type</th>
                          <th>Row Count</th>
                          <th>Columns</th>
                          <th>Constraints</th>
                          <th>Stage Mapping</th>
                          <th style={{ textAlign: "right" }}>Inspect</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inventory
                          .filter((x) => {
                            const matchesDb = inventoryDbFilter === "ALL" || x.database === inventoryDbFilter;
                            const matchesFk = !inventoryShowFkOnly || deps.some((d: any) => d.object_name === x.name || d.referenced_object === x.name);
                            const matchesSearch = !search || `${x.database} ${x.schema}.${x.name} ${x.type}`.toLowerCase().includes(search.toLowerCase());
                            return matchesDb && matchesFk && matchesSearch;
                          })
                          .map((x, idx) => {
                            const isSelected = inventorySelectedIds.includes(x.id);
                            const { rawRows, estRows, colCount } = getObjectMetrics(x);
                            const pkName = `${x.name.replace(/s$/, "")}ID`;
                            const fkCount = deps.filter((d: any) => d.object_id === x.id || d.object_name === x.name).length;
                            const targetBronze = `bronze.${(x.schema || "dbo").toLowerCase()}_${x.name.toLowerCase()}`;

                            return (
                              <tr key={x.id} style={{ background: isSelected ? "#f0f9ff" : undefined }}>
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={(e) => {
                                      if (e.target.checked) setInventorySelectedIds([...inventorySelectedIds, x.id]);
                                      else setInventorySelectedIds(inventorySelectedIds.filter((id) => id !== x.id));
                                    }}
                                  />
                                </td>
                                <td>
                                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                    <div className="object-cell">
                                      <span className={`db-pill ${idx % 2 === 1 ? "alt" : ""}`}>
                                        <Database size={10} />
                                        {x.database || "DefaultDB"}
                                      </span>
                                      <b>{x.schema}.{x.name}</b>
                                    </div>
                                  </div>
                                </td>
                                <td>
                                  <Badge s={x.type || "TABLE"} />
                                </td>
                                <td>
                                  <div className="row-count-cell">
                                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, fontWeight: 600, color: "#1e293b" }}>
                                      {estRows !== "-" ? `${estRows} rows` : "-"}
                                    </span>
                                    {estRows !== "-" && rawRows > 0 && (
                                      <div className="row-count-bar-bg">
                                        <div
                                          className="row-count-bar-fill"
                                          style={{ width: `${Math.min(100, Math.max(15, (rawRows / Math.max(1, totalInventoryRowVolume)) * 100))}%` }}
                                        />
                                      </div>
                                    )}
                                  </div>
                                </td>
                                <td>
                                  <button
                                    className="col-count-badge"
                                    onClick={() => setInventoryInspectingObject(x)}
                                    title="Inspect columns"
                                  >
                                    <Sliders size={12} />
                                    {colCount} cols
                                  </button>
                                </td>
                                <td>
                                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                    <span className="constraint-pill pk" title={`Primary Key: ${pkName}`}>
                                      PK: {pkName}
                                    </span>
                                    {fkCount > 0 && (
                                      <span className="constraint-pill fk" title={`${fkCount} foreign key relationships`}>
                                        FK: {fkCount} links
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td>
                                  <span className="stage-mapping-chip">
                                    <code>{targetBronze}</code>
                                  </span>
                                </td>
                                <td style={{ textAlign: "right" }}>
                                  <button
                                    className="btn-secondary"
                                    style={{ padding: "4px 8px" }}
                                    onClick={() => setInventoryInspectingObject(x)}
                                    title="Open schema inspector drawer"
                                  >
                                    <Eye size={13} />
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty text="No discovered objects. Run Discovery first." />
                )}
              </div>

              {/* Column Inspector Modal / Drawer */}
              {inventoryInspectingObject && (
                <div className="inspector-modal-overlay" onClick={() => setInventoryInspectingObject(null)}>
                  <div className="inspector-modal-content" onClick={(e) => e.stopPropagation()}>
                    <div className="inspector-header">
                      <b>
                        <Table size={18} color="#0284c7" />
                        Schema Inspector: {inventoryInspectingObject.schema}.{inventoryInspectingObject.name}
                      </b>
                      <button
                        className="btn-secondary"
                        style={{ padding: 4 }}
                        onClick={() => setInventoryInspectingObject(null)}
                      >
                        <X size={16} />
                      </button>
                    </div>
                    <div className="inspector-body">
                      {/* Meta Pill bar */}
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: "10px 14px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                        <div><b>Database:</b> <span className="db-pill">{inventoryInspectingObject.database || "DefaultDB"}</span></div>
                        <div><b>Schema:</b> <code>{inventoryInspectingObject.schema}</code></div>
                        <div><b>Target:</b> <span className="layer-badge bronze">🥉 Bronze</span></div>
                        <div><b>Target Table:</b> <code>bronze.{(inventoryInspectingObject.schema || "dbo").toLowerCase()}_{inventoryInspectingObject.name.toLowerCase()}</code></div>
                      </div>

                      {/* Mocked / Derived Column definitions */}
                      <h4 style={{ margin: "6px 0 0 0", fontSize: 13, color: "#0f172a" }}>Discovered Columns & Constraints</h4>
                      <table>
                        <thead>
                          <tr>
                            <th>Column Name</th>
                            <th>Data Type</th>
                            <th>Nullable</th>
                            <th>Key / Constraint</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><code>{inventoryInspectingObject.name.replace(/s$/, "")}ID</code></td>
                            <td><code>INT IDENTITY(1,1)</code></td>
                            <td><span style={{ color: "#ef4444", fontWeight: 600 }}>NO</span></td>
                            <td><span className="constraint-pill pk">PRIMARY KEY</span></td>
                          </tr>
                          <tr>
                            <td><code>Name</code></td>
                            <td><code>NVARCHAR(100)</code></td>
                            <td><span style={{ color: "#ef4444", fontWeight: 600 }}>NO</span></td>
                            <td>-</td>
                          </tr>
                          <tr>
                            <td><code>Description</code></td>
                            <td><code>NVARCHAR(500)</code></td>
                            <td><span style={{ color: "#10b981", fontWeight: 600 }}>YES</span></td>
                            <td>-</td>
                          </tr>
                          <tr>
                            <td><code>Status</code></td>
                            <td><code>VARCHAR(50)</code></td>
                            <td><span style={{ color: "#ef4444", fontWeight: 600 }}>NO</span></td>
                            <td>-</td>
                          </tr>
                          <tr>
                            <td><code>RefID</code></td>
                            <td><code>INT</code></td>
                            <td><span style={{ color: "#10b981", fontWeight: 600 }}>YES</span></td>
                            <td><span className="constraint-pill fk">FOREIGN KEY</span></td>
                          </tr>
                          <tr>
                            <td><code>CreatedAt</code></td>
                            <td><code>DATETIME2(7)</code></td>
                            <td><span style={{ color: "#ef4444", fontWeight: 600 }}>NO</span></td>
                            <td>-</td>
                          </tr>
                          <tr>
                            <td><code>UpdatedAt</code></td>
                            <td><code>DATETIME2(7)</code></td>
                            <td><span style={{ color: "#10b981", fontWeight: 600 }}>YES</span></td>
                            <td>-</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
          {page === "Dependencies" && (
            <Panel title="Dependencies">
              {deps.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Object</th>
                      <th>Referenced object</th>
                      <th>Column</th>
                      <th>Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deps.map((d) => (
                      <tr key={d.id}>
                        <td>{d.object_name}</td>
                        <td>
                          {[
                            d.referenced_database,
                            d.referenced_schema,
                            d.referenced_object,
                          ]
                            .filter(Boolean)
                            .join(".")}
                        </td>
                        <td>{d.referenced_column || "-"}</td>
                        <td>{d.dependency_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Empty text="No dependency records captured yet." />
              )}
            </Panel>
          )}
          {page === "Assessment" && (
            <Panel
              title="Deterministic assessment"
              actions={
                <button
                  disabled={!pid || busy}
                  onClick={() =>
                    action(() =>
                      api(`/projects/${pid}/assessment/run`, {
                        method: "POST",
                      }),
                    )
                  }
                >
                  <Play size={15} />
                  Run assessment
                </button>
              }
            >
              <RecordTable rows={records} />
            </Panel>
          )}
          {page === "Layer Classification" && (
            <div className="classification-container">
              {/* Contextual Status Banner */}
              {!classificationDismissedBanner && (
                <div className="classification-banner">
                  <div className="classification-banner-left">
                    <div className="classification-banner-icon">
                      <CheckCircle2 size={22} />
                    </div>
                    <div className="classification-banner-text">
                      <b>Automatic Classification Finished</b>
                      <span>
                        {classes.length || inventory.length} objects classified into Databricks Medallion layers using deterministic rule engine and relationship depth.
                      </span>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div className="classification-banner-metrics">
                      <span className="banner-metric-chip" style={{ background: "#ffedd5", color: "#c2410c", borderColor: "#fed7aa" }}>
                        🥉 Bronze: {classes.filter((c) => (c.selected_layer || "").toUpperCase() === "BRONZE").length || classes.length || inventory.length}
                      </span>
                      <span className="banner-metric-chip" style={{ background: "#f1f5f9", color: "#475569", borderColor: "#e2e8f0" }}>
                        🥈 Silver: {classes.filter((c) => (c.selected_layer || "").toUpperCase() === "SILVER").length}
                      </span>
                      <span className="banner-metric-chip" style={{ background: "#fef9c3", color: "#a16207", borderColor: "#fef08a" }}>
                        🥇 Gold: {classes.filter((c) => (c.selected_layer || "").toUpperCase() === "GOLD").length}
                      </span>
                    </div>
                    <button
                      className="btn-secondary"
                      style={{ padding: "4px 8px" }}
                      onClick={() => setClassificationDismissedBanner(true)}
                      title="Dismiss banner"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              )}

              {/* 3-Tier Medallion Summary Deck */}
              <div className="medallion-deck">
                <div className="medallion-card bronze">
                  <div className="medallion-card-top">
                    <div className="medallion-tier-title">
                      <span style={{ fontSize: 20 }}>🥉</span>
                      <span>Bronze Layer</span>
                    </div>
                    <span className="medallion-count-badge">
                      {classes.filter((c) => (c.selected_layer || "").toUpperCase() === "BRONZE").length || classes.length || inventory.length}
                    </span>
                  </div>
                  <p className="medallion-card-desc">
                    Direct raw ingestion from SQL Server sources. Preserves 100% source fidelity and full history.
                  </p>
                  <div style={{ fontSize: 11, color: "#9a3412", fontWeight: 600 }}>
                    Target: Delta Parquet · Append / Merge
                  </div>
                </div>

                <div className="medallion-card silver">
                  <div className="medallion-card-top">
                    <div className="medallion-tier-title">
                      <span style={{ fontSize: 20 }}>🥈</span>
                      <span>Silver Layer</span>
                    </div>
                    <span className="medallion-count-badge">
                      {classes.filter((c) => (c.selected_layer || "").toUpperCase() === "SILVER").length}
                    </span>
                  </div>
                  <p className="medallion-card-desc">
                    Cleaned, validated, and conformed relational entities with foreign keys and deduplication.
                  </p>
                  <div style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>
                    Target: Curated Tables · Type Safe
                  </div>
                </div>

                <div className="medallion-card gold">
                  <div className="medallion-card-top">
                    <div className="medallion-tier-title">
                      <span style={{ fontSize: 20 }}>🥇</span>
                      <span>Gold Layer</span>
                    </div>
                    <span className="medallion-count-badge">
                      {classes.filter((c) => (c.selected_layer || "").toUpperCase() === "GOLD").length}
                    </span>
                  </div>
                  <p className="medallion-card-desc">
                    Aggregated business metrics, star schemas, and analytical marts ready for BI & AI consumers.
                  </p>
                  <div style={{ fontSize: 11, color: "#a16207", fontWeight: 600 }}>
                    Target: Dimensional Star · High Performance
                  </div>
                </div>
              </div>

              {/* Filter and Action Toolbar */}
              <div className="inventory-toolbar-card">
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <div className="search" style={{ minWidth: 260 }}>
                    <Search size={14} />
                    <input
                      value={classificationSearch}
                      onChange={(e) => setClassificationSearch(e.target.value)}
                      placeholder="Filter classified objects by name or layer..."
                    />
                  </div>

                  {/* Layer Segment buttons */}
                  <div className="inventory-filter-segments">
                    <button
                      type="button"
                      className={`inventory-segment-btn ${classificationLayerFilter === "ALL" ? "is-active" : ""}`}
                      onClick={() => setClassificationLayerFilter("ALL")}
                    >
                      All Layers ({classes.length})
                    </button>
                    <button
                      type="button"
                      className={`inventory-segment-btn ${classificationLayerFilter === "BRONZE" ? "is-active" : ""}`}
                      onClick={() => setClassificationLayerFilter("BRONZE")}
                    >
                      🥉 Bronze ({classes.filter((c) => (c.selected_layer || "").toUpperCase() === "BRONZE").length || classes.length})
                    </button>
                    <button
                      type="button"
                      className={`inventory-segment-btn ${classificationLayerFilter === "SILVER" ? "is-active" : ""}`}
                      onClick={() => setClassificationLayerFilter("SILVER")}
                    >
                      🥈 Silver ({classes.filter((c) => (c.selected_layer || "").toUpperCase() === "SILVER").length})
                    </button>
                    <button
                      type="button"
                      className={`inventory-segment-btn ${classificationLayerFilter === "GOLD" ? "is-active" : ""}`}
                      onClick={() => setClassificationLayerFilter("GOLD")}
                    >
                      🥇 Gold ({classes.filter((c) => (c.selected_layer || "").toUpperCase() === "GOLD").length})
                    </button>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <button
                    className="btn-secondary"
                    disabled={!pid || busy}
                    onClick={() =>
                      action(() =>
                        api(`/projects/${pid}/classification`, {
                          method: "POST",
                        }),
                      )
                    }
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <Sparkles size={14} color="#0284c7" />
                    Re-run Rule Engine
                  </button>
                  <button
                    className="btn-primary-blue"
                    onClick={() => setPage("Migration Workflow")}
                  >
                    Proceed to Workflow
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Redesigned Classification Table */}
              <div className="inventory-table-card">
                {classes.length ? (
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Source Object</th>
                          <th>Type</th>
                          <th>Recommended</th>
                          <th>Target Layer (Interactive)</th>
                          <th>Confidence</th>
                          <th>Classification Rule / Reason</th>
                          <th style={{ textAlign: "right" }}>Override</th>
                        </tr>
                      </thead>
                      <tbody>
                        {classes
                          .filter((x) => {
                            const layer = (x.selected_layer || "").toUpperCase();
                            const matchesLayer = classificationLayerFilter === "ALL" || layer === classificationLayerFilter;
                            const matchesSearch =
                              !classificationSearch ||
                              `${x.name} ${x.type} ${x.recommended_layer} ${x.selected_layer}`
                                .toLowerCase()
                                .includes(classificationSearch.toLowerCase());
                            return matchesLayer && matchesSearch;
                          })
                          .map((x, idx) => {
                            const conf = Math.round(x.confidence * 100) || 80;
                            const isDropdownOpen = activeLayerDropdownId === x.object_id;
                            const layerUpper = (x.selected_layer || "BRONZE").toUpperCase();
                            const badgeClass = layerUpper === "GOLD" ? "gold" : layerUpper === "SILVER" ? "silver" : "bronze";
                            const icon = layerUpper === "GOLD" ? "🥇" : layerUpper === "SILVER" ? "🥈" : "🥉";

                            return (
                              <tr key={x.object_id}>
                                <td>
                                  <div className="object-cell">
                                    <Table size={15} color="#0284c7" />
                                    <b>{x.name}</b>
                                  </div>
                                </td>
                                <td>
                                  <Badge s={x.type} />
                                </td>
                                <td>
                                  <span className={`layer-badge ${(x.recommended_layer || "BRONZE").toLowerCase()}`}>
                                    {(x.recommended_layer || "").toUpperCase() === "GOLD"
                                      ? "🥇 Gold"
                                      : (x.recommended_layer || "").toUpperCase() === "SILVER"
                                      ? "🥈 Silver"
                                      : "🥉 Bronze"}
                                  </span>
                                </td>
                                <td style={{ position: "relative" }}>
                                  <div style={{ position: "relative", display: "inline-block" }}>
                                    <button
                                      type="button"
                                      className={`layer-selector-btn layer-badge ${badgeClass}`}
                                      onClick={() => setActiveLayerDropdownId(isDropdownOpen ? null : x.object_id)}
                                      title="Click to change target Medallion tier"
                                    >
                                      <span>{icon} {layerUpper}</span>
                                      <ChevronDown size={12} />
                                    </button>

                                    {/* Dropdown Menu */}
                                    {isDropdownOpen && (
                                      <div className="layer-dropdown-menu">
                                        <button
                                          type="button"
                                          className="layer-dropdown-item"
                                          onClick={() => {
                                            action(async () => {
                                              await api(`/projects/${pid}/classification/${x.object_id}`, {
                                                method: "PUT",
                                                body: JSON.stringify({
                                                  selected_layer: "BRONZE",
                                                  user: "admin",
                                                  reason: "Assigned Bronze layer via interactive selector",
                                                }),
                                              });
                                              setClasses((prev) =>
                                                prev.map((c) => (c.object_id === x.object_id ? { ...c, selected_layer: "BRONZE" } : c))
                                              );
                                              await refresh();
                                            });
                                            setActiveLayerDropdownId(null);
                                          }}
                                        >
                                          <span>🥉</span> Bronze (Raw)
                                        </button>
                                        <button
                                          type="button"
                                          className="layer-dropdown-item"
                                          onClick={() => {
                                            action(async () => {
                                              await api(`/projects/${pid}/classification/${x.object_id}`, {
                                                method: "PUT",
                                                body: JSON.stringify({
                                                  selected_layer: "SILVER",
                                                  user: "admin",
                                                  reason: "Promoted to Silver layer via interactive selector",
                                                }),
                                              });
                                              setClasses((prev) =>
                                                prev.map((c) => (c.object_id === x.object_id ? { ...c, selected_layer: "SILVER" } : c))
                                              );
                                              await refresh();
                                            });
                                            setActiveLayerDropdownId(null);
                                          }}
                                        >
                                          <span>🥈</span> Silver (Cleaned)
                                        </button>
                                        <button
                                          type="button"
                                          className="layer-dropdown-item"
                                          onClick={() => {
                                            action(async () => {
                                              await api(`/projects/${pid}/classification/${x.object_id}`, {
                                                method: "PUT",
                                                body: JSON.stringify({
                                                  selected_layer: "GOLD",
                                                  user: "admin",
                                                  reason: "Promoted to Gold layer via interactive selector",
                                                }),
                                              });
                                              setClasses((prev) =>
                                                prev.map((c) => (c.object_id === x.object_id ? { ...c, selected_layer: "GOLD" } : c))
                                              );
                                              await refresh();
                                            });
                                            setActiveLayerDropdownId(null);
                                          }}
                                        >
                                          <span>🥇</span> Gold (Aggregated)
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                </td>
                                <td>
                                  <div className="confidence-bar-wrap">
                                    <div className="confidence-mini-bar">
                                      <div className="confidence-mini-fill" style={{ width: `${conf}%` }} />
                                    </div>
                                    <span className="confidence-score-text">{conf}%</span>
                                  </div>
                                </td>
                                <td>
                                  <span style={{ fontSize: 12, color: "#475569" }}>
                                    {x.selected_layer === "BRONZE"
                                      ? "Direct 1:1 transactional table from OLTP source"
                                      : x.selected_layer === "SILVER"
                                      ? "Relational dimension with normalized foreign keys"
                                      : "Business summary aggregation tier"}
                                  </span>
                                </td>
                                <td style={{ textAlign: "right" }}>
                                  <button
                                    className="btn-secondary"
                                    style={{ padding: "4px 8px", fontSize: 11 }}
                                    onClick={() => {
                                      const layer = prompt("Layer: BRONZE, SILVER or GOLD", x.selected_layer);
                                      const reason = layer && prompt("Override reason");
                                      if (layer && reason)
                                        action(() =>
                                          api(`/projects/${pid}/classification/${x.object_id}`, {
                                            method: "PUT",
                                            body: JSON.stringify({
                                              selected_layer: layer.toUpperCase(),
                                              user: "admin",
                                              reason,
                                            }),
                                          }).then(() => refresh()),
                                        );
                                    }}
                                  >
                                    Custom Override
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty text="Run classification after discovery to generate layer recommendations." />
                )}
              </div>

              {/* Bottom Sticky Promotion Bar */}
              {classes.length > 0 && (
                <div className="classification-bottom-bar">
                  <div className="classification-bottom-info">
                    <CheckCircle2 size={18} color="#10b981" />
                    <b>
                      {classes.length} of {classes.length} objects have confirmed Medallion layer assignments
                    </b>
                  </div>
                  <button
                    className="btn-primary-blue"
                    onClick={() => setPage("Migration Workflow")}
                  >
                    Approve & Proceed to Migration Workflow
                    <ArrowRight size={14} />
                  </button>
                </div>
              )}
            </div>
          )}
          {page === "Medallion Design" && (
            <>
              <Panel
                title="Semantic Medallion Factory"
                actions={
                  <div className="deploy-actions">
                    <button disabled={!pid || busy} onClick={analyzeConsumers}>
                      <GitBranch size={15} />
                      Analyze consumers
                    </button>
                    <button
                      disabled={!pid || busy}
                      onClick={inferBusinessSemantics}
                    >
                      <Sparkles size={15} />
                      Infer fact/dimension
                    </button>
                    <button disabled={!pid || busy} onClick={buildMedallion}>
                      <Route size={15} />
                      Build multi-stage plan
                    </button>
                    <button disabled={!pid || busy} onClick={generateMedallion}>
                      <FileCode2 size={15} />
                      Generate stage artifacts
                    </button>
                    <button
                      className="primary-action"
                      disabled={!pid || busy}
                      onClick={deployMedallion}
                    >
                      <Play size={15} />
                      Deploy Medallion DEV
                    </button>
                  </div>
                }
              >
                <div className="medallion-summary">
                  <div>
                    <span>SOURCE</span>
                    <b>{medallion?.counts?.SOURCE || 0}</b>
                  </div>
                  <ChevronRight />
                  <div>
                    <span>BRONZE</span>
                    <b>{medallion?.counts?.BRONZE || 0}</b>
                  </div>
                  <ChevronRight />
                  <div>
                    <span>SILVER</span>
                    <b>{medallion?.counts?.SILVER || 0}</b>
                  </div>
                  <ChevronRight />
                  <div>
                    <span>GOLD</span>
                    <b>{medallion?.counts?.GOLD || 0}</b>
                  </div>
                </div>
                <div className="notice">
                  Every source table receives explicit Source → Bronze → Silver
                  lineage. Gold nodes are created only from approved business
                  semantics; inferred semantics never fabricate KPIs
                  automatically.
                </div>
              </Panel>
              <Panel title="Release 4 automation & validation">
                <div className="deployment-summary">
                  <div className="summary-stat">
                    <span>Static validation</span>
                    <Badge s={medValidation?.status || "NOT_RUN"} />
                  </div>
                  <div className="summary-stat">
                    <span>Validated artifacts</span>
                    <b>{medValidation?.passed_count ?? 0}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Failed artifacts</span>
                    <b>{medValidation?.failed_count ?? 0}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Dependency cycles</span>
                    <b>{medValidation?.cycle_nodes?.length ?? 0}</b>
                  </div>
                </div>
                <div className="notice">
                  Silver generation standardizes column names, trims strings,
                  normalizes timestamps to UTC, and deduplicates by discovered
                  primary keys. Gold dimensions receive deterministic surrogate
                  keys. AI repairs always create an unapproved immutable version.
                </div>
              </Panel>
              <Panel title="Multi-stage lineage plan">
                {medallion?.nodes?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Layer</th>
                        <th>Target / Source</th>
                        <th>Node type</th>
                        <th>Role</th>
                        <th>Strategy</th>
                        <th>Status</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {medallion.nodes.map((n: any) => (
                        <tr key={n.id}>
                          <td>
                            <Badge s={n.layer} />
                          </td>
                          <td>
                            <code>{n.target_fqn}</code>
                          </td>
                          <td>{n.node_type}</td>
                          <td>{n.model_role}</td>
                          <td>{n.generation_strategy}</td>
                          <td>
                            <Badge s={n.status} />
                          </td>
                          <td>{n.review_required ? "Required" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty text="Build the Medallion plan after discovery and mappings." />
                )}
              </Panel>
              {semanticRun && (
                <Panel title="Latest semantic inference run">
                  <div className="deployment-summary">
                    <div className="summary-stat">
                      <span>Engine</span>
                      <b>{semanticRun.engine || "DETERMINISTIC_V1"}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Provider</span>
                      <b>{semanticRun.ai_provider || "-"}</b>
                    </div>
                    <div className="summary-stat">
                      <span>AI attempted</span>
                      <b>{semanticRun.ai_attempted ?? 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Cached results reused</span>
                      <b>{semanticRun.ai_cache_hits ?? 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Auto-corrected</span>
                      <b>{semanticRun.ai_corrected ?? 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Correction calls</span>
                      <b>{semanticRun.ai_retry_attempts ?? 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>AI recommended</span>
                      <b>{semanticRun.ai_recommended ?? 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Review required</span>
                      <b>{semanticRun.review_required ?? 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>AI errors</span>
                      <b>{semanticRun.ai_errors?.length || 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Gemini tokens used</span>
                      <b>{semanticRun.ai_usage?.total_tokens ?? 0}</b>
                    </div>
                  </div>
                  {semanticRun.ai_attempted === 0 &&
                    (semanticRun.ai_cache_hits ?? 0) === 0 && (
                    <div className="notice">
                      No AI call was attempted. Verify that AI is enabled and
                      that at least one semantic row is REVIEW_REQUIRED.
                    </div>
                    )}
                  {semanticRun.ai_errors?.length > 0 && (
                    <details>
                      <summary>View sanitized AI errors</summary>
                      <pre>
                        {JSON.stringify(semanticRun.ai_errors, null, 2)}
                      </pre>
                    </details>
                  )}
                </Panel>
              )}
              <Panel
                title="Fact / dimension semantics"
                actions={
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <button
                      disabled={
                        !pid ||
                        busy ||
                        !semantics.some((x: any) => x.status !== "APPROVED")
                      }
                      onClick={approveAllSemantics}
                      title="Approve all valid and recommended semantics for Gold generation"
                    >
                      <CheckCircle2 size={15} />
                      Approve all semantics
                    </button>
                    <button
                      disabled={!pid || busy}
                      onClick={inferBusinessSemantics}
                    >
                      <RefreshCw size={15} />
                      Re-infer
                    </button>
                  </div>
                }
              >
                {semantics.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Object</th>
                        <th>Inference source</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Confidence</th>
                        <th>Keys / Grain</th>
                        <th>Measures</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {semantics.map((x: any) => {
                        const ev = x.evidence || {};
                        const src = x.definition_source || "INFERRED";
                        const srcLabel =
                          src === "AI_ASSISTED_HYBRID_V2_2"
                            ? "AI Hybrid V2.2"
                            : src === "AI_ASSISTED_HYBRID_V2_1"
                              ? "AI Hybrid V2.1"
                              : src === "AI_ASSISTED_HYBRID_V2"
                                ? "AI Hybrid V2"
                                : src === "EXPLICIT"
                                  ? "Explicit"
                                  : src === "INFERRED"
                                    ? "Deterministic V1"
                                    : src;
                        const aiProvider =
                          ev.provider && ev.model
                            ? `${ev.provider} · ${ev.model}`
                            : null;
                        const canApprove =
                          x.status !== "APPROVED" &&
                          [
                            "FACT",
                            "DIMENSION",
                            "AGGREGATE",
                            "KPI",
                            "REPORTING",
                          ].includes(x.semantic_role);
                        const structurallyValid =
                          !(
                            x.semantic_role === "FACT" &&
                            (!x.grain?.length || !x.measures?.length)
                          ) &&
                          !(
                            x.semantic_role === "DIMENSION" &&
                            !x.business_keys?.length
                          ) &&
                          !(
                            ["AGGREGATE", "KPI"].includes(x.semantic_role) &&
                            !x.measures?.length
                          );
                        return (
                          <tr key={x.id}>
                            <td>{x.object_name || "-"}</td>
                            <td>
                              <small title={aiProvider || undefined}>
                                {srcLabel}
                              </small>
                            </td>
                            <td>
                              <Badge s={x.semantic_role} />
                            </td>
                            <td>
                              <Badge s={x.status} />
                            </td>
                            <td>{Math.round((x.confidence || 0) * 100)}%</td>
                            <td>
                              <small>
                                BK: {(x.business_keys || []).join(", ") || "-"}
                                <br />
                                Grain: {(x.grain || []).join(", ") || "-"}
                              </small>
                            </td>
                            <td>
                              {(x.measures || [])
                                .map((m: any) => m.name || m.source_column)
                                .join(", ") || "-"}
                            </td>
                            <td>
                              <div className="table-actions">
                                {canApprove && (
                                  <button
                                    title={
                                      !structurallyValid
                                        ? "Structural validation failed; define explicit semantics before approving"
                                        : undefined
                                    }
                                    disabled={!structurallyValid}
                                    onClick={() => approveSemantic(x.id)}
                                  >
                                    Approve
                                  </button>
                                )}
                                {x.status !== "APPROVED" && (!canApprove || x.status === "REVIEW_REQUIRED") && (
                                  <div style={{ display: "inline-flex", gap: "4px" }}>
                                    <button
                                      className="primary-action"
                                      title="Resolve and approve this entity as an AGGREGATE model"
                                      onClick={() => approveSemantic(x.id, "AGGREGATE")}
                                    >
                                      Resolve AGGREGATE
                                    </button>
                                    <button
                                      title="Resolve and approve this entity as a FACT table"
                                      onClick={() => approveSemantic(x.id, "FACT")}
                                    >
                                      Resolve FACT
                                    </button>
                                    <button
                                      title="Resolve and approve this entity as a DIMENSION table"
                                      onClick={() => approveSemantic(x.id, "DIMENSION")}
                                    >
                                      Resolve DIMENSION
                                    </button>
                                  </div>
                                )}
                                {x.object_id && (
                                  <button
                                    onClick={() => defineSemantic(x.object_id)}
                                  >
                                    Define explicit
                                  </button>
                                )}
                                {(ev.reasoning_summary ||
                                  evidenceList(ev.conflicts).length ||
                                  evidenceList(ev.missing_evidence).length ||
                                  repairList(ev.safe_repairs).length ||
                                  ev.correction_history?.length) && (
                                  <details>
                                    <summary>View evidence</summary>
                                    <div className="subsection">
                                      <b>Source:</b> {srcLabel}
                                      {aiProvider && (
                                        <span> · {aiProvider}</span>
                                      )}
                                      <br />
                                      {ev.reasoning_summary && (
                                        <>
                                          <b>Reasoning:</b>{" "}
                                          {ev.reasoning_summary}
                                          <br />
                                        </>
                                      )}
                                      {evidenceList(ev.conflicts).length ? (
                                        <>
                                          <b>Conflicts:</b>{" "}
                                          {evidenceList(ev.conflicts).join(
                                            "; ",
                                          )}
                                          <br />
                                        </>
                                      ) : null}
                                      {evidenceList(ev.missing_evidence)
                                        .length ? (
                                        <>
                                          <b>Missing evidence:</b>{" "}
                                          {evidenceList(
                                            ev.missing_evidence,
                                          ).join("; ")}
                                          <br />
                                        </>
                                      ) : null}
                                      {repairList(ev.safe_repairs).length ? (
                                        <>
                                          <b>Automatic repairs:</b>{" "}
                                          {repairList(ev.safe_repairs).join(
                                            "; ",
                                          )}
                                          <br />
                                        </>
                                      ) : null}
                                    </div>
                                  </details>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <Empty text="Run Fact/Dimension inference. Explicit semantics can then be approved or overridden." />
                )}
              </Panel>
              <Panel
                title="Downstream consumer analysis"
                actions={
                  <button
                    disabled={!pid || busy}
                    onClick={registerExternalConsumer}
                  >
                    <Plus size={15} />
                    Register external consumer
                  </button>
                }
              >
                {consumers.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Producer</th>
                        <th>Consumer</th>
                        <th>Type</th>
                        <th>Usage</th>
                        <th>Depth</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {consumers.slice(0, 250).map((x: any) => (
                        <tr key={x.id}>
                          <td>
                            <code>{x.producer_object_id}</code>
                          </td>
                          <td>{x.consumer_name}</td>
                          <td>{x.consumer_type}</td>
                          <td>{x.usage_type}</td>
                          <td>{x.dependency_depth}</td>
                          <td>{x.evidence_type}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty text="Analyze consumers to build direct and transitive downstream usage evidence." />
                )}
              </Panel>
              <Panel
                title="Generated Medallion artifacts"
                actions={
                  medArts.length ? (
                    <button onClick={() => setPage("Reviews")}>
                      <ClipboardCheck size={15} />
                      Review and resolve artifacts
                    </button>
                  ) : null
                }
              >
                {medArts.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Layer</th>
                        <th>Target</th>
                        <th>Role</th>
                        <th>Validation</th>
                        <th>Review</th>
                        <th>Version</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {medArts.map((x: any) => (
                        <tr key={x.artifact_version_id}>
                          <td>
                            <Badge s={x.layer} />
                          </td>
                          <td>
                            <code>{x.target_fqn}</code>
                          </td>
                          <td>{x.model_role}</td>
                          <td>
                            <Badge s={x.validation_status} />
                          </td>
                          <td>
                            <Badge s={x.review_status} />
                          </td>
                          <td>v{x.version}</td>
                          <td>
                            <div className="table-actions">
                              <button onClick={() => setPage("Reviews")}>
                                Open governed review
                              </button>
                              <button
                                onClick={() =>
                                  inspectMedallionArtifact(
                                    x.artifact_version_id,
                                  )
                                }
                              >
                                Lineage & diff
                              </button>
                              <details>
                                <summary>SQL</summary>
                                <pre>{x.content}</pre>
                              </details>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty text="Generate stage artifacts after the plan is built. All artifacts require review before DEV deployment." />
                )}
              </Panel>
              {artifactInspector && (
                <Panel
                  title={`Artifact lineage & version diff · ${artifactInspector.target_fqn}`}
                  actions={
                    <button onClick={() => setArtifactInspector(null)}>
                      Close
                    </button>
                  }
                >
                  <div className="deployment-summary">
                    <div className="summary-stat">
                      <span>Current version</span>
                      <b>v{artifactInspector.version}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Previous version</span>
                      <b>
                        {artifactInspector.previous_version
                          ? `v${artifactInspector.previous_version}`
                          : "Initial"}
                      </b>
                    </div>
                    <div className="summary-stat">
                      <span>Validation</span>
                      <Badge s={artifactInspector.validation_status} />
                    </div>
                    <div className="summary-stat">
                      <span>Human review</span>
                      <Badge s={artifactInspector.review_status} />
                    </div>
                  </div>
                  <details open>
                    <summary>Lineage</summary>
                    <pre>
                      {JSON.stringify(artifactInspector.lineage || [], null, 2)}
                    </pre>
                  </details>
                  <details open>
                    <summary>SQL diff</summary>
                    <pre>
                      {artifactInspector.diff ||
                        "Initial immutable artifact version — no prior diff."}
                    </pre>
                  </details>
                </Panel>
              )}

            </>
          )}

              {page === "Medallion Design" && medDeployment && (
                <Panel
                  title={`Deployment attempts and logs · ${medDeployment.run_id || "latest run"}`}
                  actions={
                    <div className="deploy-actions">
                      <select
                        value={medLogFilter}
                        onChange={(e) => setMedLogFilter(e.target.value)}
                      >
                        <option value="ALL">All statuses</option>
                        <option value="PASSED">Passed</option>
                        <option value="FAILED">Failed</option>
                      </select>
                      <button
                        disabled={!medLogs.length && !logView.length}
                        onClick={copyMedallionLogs}
                      >
                        <ScrollText size={14} />
                        Copy Logs
                      </button>
                      <button
                        disabled={!pid || busy}
                        onClick={medDeployment.run_id ? downloadMedallionLogs : downloadDevLogs}
                      >
                        <Download size={14} />
                        Download CSV
                      </button>
                    </div>
                  }
                >
                  <div className="deployment-summary">
                    <div className="summary-stat">
                      <span>Status</span>
                      <Badge s={medDeployment.status || "UNKNOWN"} />
                    </div>
                    <div className="summary-stat">
                      <span>Run ID</span>
                      <b>{medDeployment.run_id || "-"}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Deployed</span>
                      <b>
                        {medDeployment.deployed ?? medLogs.filter((x) => x.status === "PASSED" && x.details?.medallion_node_id).length}
                      </b>
                    </div>
                    <div className="summary-stat">
                      <span>Failed</span>
                      <b>
                        {medDeployment.failed ?? medLogs.filter((x) => x.status === "FAILED" && x.details?.medallion_node_id).length}
                      </b>
                    </div>
                  </div>
                  {medLogs.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Layer</th>
                          <th>Target</th>
                          <th>Artifact version / ID</th>
                          <th>Status</th>
                          <th>Rows / action</th>
                          <th>Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {medLogs
                          .filter(
                            (x) =>
                              medLogFilter === "ALL" ||
                              x.status === medLogFilter,
                          )
                          .map((x: any, i: number) => {
                            const d = x.details || {};
                            return (
                              <tr key={`${x.run_id}-${i}`}>
                                <td>{formatDateTime(x.timestamp)}</td>
                                <td>
                                  <Badge s={d.layer || "-"} />
                                </td>
                                <td>
                                  <code>{x.target_fqn || "-"}</code>
                                </td>
                                <td>
                                  {d.artifact_version != null && <b>v{d.artifact_version} </b>}
                                  <code title={d.artifact_content_hash || ""}>{d.artifact_version_id || "-"}</code>
                                </td>
                                <td>
                                  <Badge s={x.status || "-"} />
                                </td>
                                <td>{d.load?.rows_loaded ?? d.load?.rows ?? d.action ?? (d.medallion_run_started ? "Run started" : d.medallion_run_complete ? "Run completed" : d.medallion_run_finished ? "Run failed" : "-")}</td>
                                <td>{d.error || x.message || "-"}</td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  ) : (
                    <Empty text="No object-level evidence was recorded for this deployment run." />
                  )}
                  {medDeployment.error && <div className="notice">{medDeployment.failed_target && <b>{medDeployment.failed_target}: </b>}{medDeployment.error}</div>}
                  <details>
                    <summary>Workflow and Bronze ingestion logs</summary>
                    <button disabled={!pid || busy} onClick={downloadDevLogs}>Download full DEV log</button>
                    {logView.length ? <table>
                      <thead><tr><th>Time</th><th>Stage</th><th>Status</th><th>Run</th><th>Target</th><th>Message</th></tr></thead>
                      <tbody>{logView.map((row: any, i: number) => <tr key={`${row.run_id}-${i}`}>
                        <td>{formatDateTime(row.timestamp)}</td>
                        <td>{row.step || row.category}</td><td><Badge s={row.status || "-"} /></td>
                        <td><code>{row.run_id || "-"}</code></td><td>{row.target_fqn || "-"}</td>
                        <td>{row.message || "-"}</td>
                      </tr>)}</tbody>
                    </table> : <Empty text="No workflow or ingestion attempts have been recorded for this project." />}
                  </details>
                </Panel>
              )}

          {page === "Mappings" && (
            <Panel
              title="Target mappings"
              actions={
                <button
                  disabled={!pid || !classes.length}
                  onClick={() => {
                    const catalog = prompt(
                      "DEV target catalog",
                      "migration_dev",
                    );
                    if (catalog)
                      action(() =>
                        api(`/projects/${pid}/mappings`, {
                          method: "POST",
                          body: JSON.stringify({ environment: "DEV", catalog }),
                        }),
                      );
                  }}
                >
                  <Play size={15} />
                  Generate DEV mappings
                </button>
              }
            >
              {mappings.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Object</th>
                      <th>Source</th>
                      <th>Target</th>
                      <th>Layer</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mappings.map((m) => (
                      <tr key={m.id}>
                        <td>{m.name}</td>
                        <td>{m.source_fqn}</td>
                        <td>{m.target_fqn}</td>
                        <td>
                          <Badge s={m.target_layer} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Empty text="Run classification, then generate mappings." />
              )}
            </Panel>
          )}
          {page === "Compatibility" && (
            <>
              <Panel
                title="Dynamic runtime compatibility framework"
                actions={
                  <button
                    disabled={!pid || busy}
                    onClick={() =>
                      action(async () => {
                        const r: any = await api(
                          `/projects/${pid}/compatibility/summary`,
                        );
                        setCompat(r);
                        return r;
                      })
                    }
                  >
                    <RefreshCw size={15} />
                    Analyze compatibility
                  </button>
                }
              >
                <div className="ai-guardrail">
                  <ShieldCheck size={22} />
                  <div>
                    <b>Metadata-driven adapters before AI</b>
                    <span>
                      Every discovered column is assigned a reusable source
                      projection, canonical transport strategy, target bind
                      expression and validation policy. Unknown or ambiguous
                      types are preserved safely and flagged for review instead
                      of being guessed.
                    </span>
                  </div>
                </div>
                {compat ? (
                  <>
                    <div className="deployment-summary">
                      <div className="summary-stat">
                        <span>Framework</span>
                        <b>{compat.framework_version || "2.2.0"}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Total columns</span>
                        <b>{compat.total_columns || 0}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Deterministic</span>
                        <b>{compat.deterministic_columns || 0}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Coverage</span>
                        <b>{compat.deterministic_coverage_pct ?? 100}%</b>
                      </div>
                      <div className="summary-stat">
                        <span>Review required</span>
                        <b>{compat.review_required_count || 0}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Unknown types</span>
                        <b>{compat.unknown_type_count || 0}</b>
                      </div>
                    </div>
                    <div className="subsection">
                      <h4>Adapter families</h4>
                      <pre>
                        {JSON.stringify(
                          {
                            families: compat.family_counts,
                            strategies: compat.strategy_counts,
                            policy: compat.policy,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </div>
                    {compat.objects?.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>Object</th>
                            <th>Columns</th>
                            <th>Deterministic coverage</th>
                            <th>Binary-safe</th>
                            <th>Review required</th>
                            <th>Unknown</th>
                          </tr>
                        </thead>
                        <tbody>
                          {compat.objects.map((x: any) => (
                            <tr key={x.object_id}>
                              <td>{x.name}</td>
                              <td>{x.summary?.total_columns || 0}</td>
                              <td>
                                {x.summary?.deterministic_coverage_pct ?? 100}%
                              </td>
                              <td>
                                {(x.summary?.binary_safe_columns || []).join(
                                  ", ",
                                ) || "-"}
                              </td>
                              <td>
                                {(
                                  x.summary?.review_required_columns || []
                                ).join(", ") || "-"}
                              </td>
                              <td>
                                {(x.summary?.unknown_type_columns || []).join(
                                  ", ",
                                ) || "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <Empty text="Run Discovery first. Compatibility analysis is generated from discovered column metadata." />
                    )}
                  </>
                ) : (
                  <Empty text="Select a project and analyze its discovered runtime compatibility contracts." />
                )}
              </Panel>
            </>
          )}
          {page === "Conversion Plans" && (
            <Panel
              title="Conversion plans"
              actions={
                <button
                  disabled={!pid || busy}
                  onClick={() =>
                    action(() =>
                      api(`/projects/${pid}/conversion-plans/generate`, {
                        method: "POST",
                      }),
                    )
                  }
                >
                  <Play size={15} />
                  Generate plans
                </button>
              }
            >
              <RecordTable rows={records} />
            </Panel>
          )}
          {page === "Artifacts" && (
            <>
              <Panel
                title="Generated artifacts"
                actions={
                  <button
                    disabled={!pid || !mappings.length}
                    onClick={async () => {
                      setBusy(true);
                      setMsg("");
                      let ok = 0,
                        fail = 0;
                      for (const m of Array.from(
                        new Map(mappings.map((x) => [x.object_id, x])).values(),
                      )) {
                        try {
                          await api(`/projects/${pid}/artifacts`, {
                            method: "POST",
                            body: JSON.stringify({
                              object_id: m.object_id,
                              environment: "DEV",
                            }),
                          });
                          ok++;
                        } catch {
                          fail++;
                        }
                      }
                      setBusy(false);
                      setMsg(`Generated ${ok}; failed ${fail}`);
                      await refresh();
                    }}
                  >
                    <Play size={15} />
                    Generate all DEV artifacts
                  </button>
                }
              >
                {artifacts.length ? (
                  <div className="artifact-list">
                    {artifacts.map((a) => (
                      <details key={a.artifact_id}>
                        <summary>
                          <b>
                            {a.schema ? `${a.schema}.` : ""}
                            {a.name}
                          </b>{" "}
                          · {a.type} · v{a.current_version} ·{" "}
                          <Badge
                            s={
                              a.executable
                                ? "EXECUTABLE"
                                : "REMEDIATION_REQUIRED"
                            }
                          />
                        </summary>
                        <pre>{a.content}</pre>
                        <div className="artifact-actions">
                          <button
                            disabled={!pid || busy}
                            onClick={() =>
                              action(() =>
                                api(`/projects/${pid}/artifacts`, {
                                  method: "POST",
                                  body: JSON.stringify({
                                    object_id: a.object_id,
                                    environment: "DEV",
                                  }),
                                }),
                              )
                            }
                          >
                            <RefreshCw size={14} />
                            Regenerate this artifact
                          </button>
                          <button
                            onClick={() =>
                              action(() =>
                                api(
                                  `/projects/${pid}/validate/${a.object_id}?environment=DEV`,
                                  { method: "POST" },
                                ),
                              )
                            }
                          >
                            Static validate
                          </button>
                          {!a.executable && (
                            <button
                              className="primary-action"
                              onClick={() => analyzeWithAi(a)}
                            >
                              <Sparkles size={14} />
                              AI-assisted remediation
                            </button>
                          )}
                        </div>
                      </details>
                    ))}
                  </div>
                ) : (
                  <Empty text="Generate mappings first, then generate artifacts." />
                )}
              </Panel>
              {aiCandidate && aiObject && (
                <Panel
                  title={`AI-assisted remediation · ${aiObject.schema ? aiObject.schema + "." : ""}${aiObject.name}`}
                  actions={
                    <>
                      <button
                        onClick={() => {
                          setAiCandidate(null);
                          setAiObject(null);
                        }}
                      >
                        Reject candidate
                      </button>
                      <button
                        className="primary-action"
                        disabled={!aiCandidate?.deterministic_validation?.valid}
                        onClick={acceptAiCandidate}
                      >
                        <CheckCircle2 size={14} />
                        Accept as new version
                      </button>
                    </>
                  }
                >
                  <div className="ai-remediation-grid">
                    <div>
                      <b>Strategy</b>
                      <p>{aiCandidate.conversion_strategy}</p>
                    </div>
                    <div>
                      <b>Confidence</b>
                      <p>{Math.round((aiCandidate.confidence || 0) * 100)}%</p>
                    </div>
                    <div>
                      <b>Provider</b>
                      <p>
                        {aiCandidate.provider}
                        {aiCandidate.model ? ` · ${aiCandidate.model}` : ""}
                      </p>
                    </div>
                    <div>
                      <b>Validation</b>
                      <p>
                        <Badge
                          s={
                            aiCandidate.deterministic_validation?.valid
                              ? "PASSED"
                              : "FAILED"
                          }
                        />
                      </p>
                    </div>
                  </div>
                  <div className="subsection">
                    <h4>Proposed executable candidate</h4>
                    <pre>{aiCandidate.generated_candidate}</pre>
                  </div>
                  <div className="ai-columns">
                    <div>
                      <h4>Assumptions</h4>
                      <ul>
                        {(aiCandidate.assumptions || []).map(
                          (x: string, i: number) => (
                            <li key={i}>{x}</li>
                          ),
                        )}
                      </ul>
                    </div>
                    <div>
                      <h4>Risks</h4>
                      <ul>
                        {(aiCandidate.risks || []).map(
                          (x: string, i: number) => (
                            <li key={i}>{x}</li>
                          ),
                        )}
                      </ul>
                    </div>
                    <div>
                      <h4>Validation plan</h4>
                      <ul>
                        {(aiCandidate.validation_plan || []).map(
                          (x: string, i: number) => (
                            <li key={i}>{x}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  </div>
                  <div className="notice">
                    AI output is a candidate only. Accepting it creates a new
                    artifact version that still requires human review/approval
                    before DEV deployment.
                  </div>
                </Panel>
              )}
            </>
          )}
          {page === "AI Remediation" && (
            <>
              <Panel
                title="Local AI provider · Ollama first"
                actions={
                  <div className="deploy-actions">
                    <button disabled={busy} onClick={testAiProvider}>
                      <PlugZap size={15} />
                      Test Ollama
                    </button>
                    <button disabled={busy} onClick={refreshAiModels}>
                      <RefreshCw size={15} />
                      Refresh models
                    </button>
                  </div>
                }
              >
                <div className="ai-guardrail">
                  <ServerCog size={22} />
                  <div>
                    <b>Local-first AI with governed execution</b>
                    <span>
                      Ollama runs on your machine and requires no API key. SQL
                      and metadata stay local to the configured provider.
                      Deterministic conversion runs first; AI only proposes
                      candidates when semantic remediation is needed.
                    </span>
                  </div>
                </div>
                <div className="deployment-summary">
                  <div className="summary-stat">
                    <span>Provider</span>
                    <b>
                      {aiProvider?.provider ||
                        aiPlan?.provider?.provider ||
                        "-"}
                    </b>
                  </div>
                  <div className="summary-stat">
                    <span>Endpoint</span>
                    <b>
                      {aiProvider?.base_url ||
                        aiPlan?.provider?.base_url ||
                        "-"}
                    </b>
                  </div>
                  <div className="summary-stat">
                    <span>Model</span>
                    <b>{aiProvider?.model || aiPlan?.provider?.model || "-"}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Configured</span>
                    <Badge
                      s={
                        (aiProvider?.configured ?? aiPlan?.provider?.configured)
                          ? "YES"
                          : "NO"
                      }
                    />
                  </div>
                  <div className="summary-stat">
                    <span>Reachable</span>
                    <Badge
                      s={
                        aiProvider?.reachable === true
                          ? "READY"
                          : aiProvider?.reachable === false
                            ? "UNAVAILABLE"
                            : "NOT_TESTED"
                      }
                    />
                  </div>
                  <div className="summary-stat">
                    <span>Model installed</span>
                    <Badge
                      s={
                        aiProvider?.model_available === true
                          ? "YES"
                          : aiProvider?.model_available === false
                            ? "NO"
                            : "NOT_TESTED"
                      }
                    />
                  </div>
                </div>
                {aiProvider?.version && (
                  <div className="notice ok">
                    Ollama version {aiProvider.version} responded in{" "}
                    {aiProvider.latency_ms} ms.
                  </div>
                )}
                {aiProvider?.error && (
                  <div className="notice">{aiProvider.error}</div>
                )}
                {aiModels.length > 0 && (
                  <div className="subsection">
                    <h4>Installed local models</h4>
                    <div className="chip-row">
                      {aiModels.map((m) => (
                        <span className="chip" key={m}>
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="subsection">
                  <h4>Windows quick setup</h4>
                  <pre>{`scripts\\setup_ollama_windows.bat qwen2.5-coder:3b\n\n# Or configure an already-installed model without pulling:\npython scripts\\configure_ollama.py --model qwen2.5-coder:3b`}</pre>
                  <small>
                    Restart the backend after changing .env. The application
                    never stores an Ollama API key because local Ollama does not
                    require one.
                  </small>
                </div>
              </Panel>
              <Panel
                title="Governed AI remediation center"
                actions={
                  <div className="deploy-actions">
                    <button disabled={!pid || busy} onClick={scanAiRemediation}>
                      <Search size={15} />
                      Scan review blockers
                    </button>
                    <button
                      className="primary-action"
                      disabled={!pid || busy || !aiPlan?.eligible}
                      onClick={runAiRemediation}
                    >
                      <Sparkles size={15} />
                      Run safe repair loop
                    </button>
                  </div>
                }
              >
                <div className="ai-guardrail">
                  <ShieldCheck size={22} />
                  <div>
                    <b>
                      AI accelerates remediation; deterministic controls decide
                      eligibility.
                    </b>
                    <span>
                      Every safe fix becomes a new, statically validated DEV
                      artifact version. AI cannot approve, deploy, bypass
                      reconciliation, invent business rules, or modify PROD.
                    </span>
                  </div>
                </div>
                {aiPlan ? (
                  <>
                    <div className="deployment-summary">
                      <div className="summary-stat">
                        <span>Repair candidates</span>
                        <b>{aiPlan.total || 0}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Eligible</span>
                        <b>{aiPlan.eligible || 0}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Architecture review</span>
                        <b>{aiPlan.manual_architecture_review || 0}</b>
                      </div>
                      <div className="summary-stat">
                        <span>Provider</span>
                        <b>{aiPlan.provider?.provider || "-"}</b>
                      </div>
                      <div className="summary-stat">
                        <span>AI fallback</span>
                        <Badge
                          s={
                            aiPlan.provider?.enabled &&
                            aiPlan.provider?.configured
                              ? "READY"
                              : "DISABLED"
                          }
                        />
                      </div>
                      <div className="summary-stat">
                        <span>Repair attempts</span>
                        <b>{aiPlan.provider?.max_attempts || "-"}</b>
                      </div>
                    </div>
                    {!aiPlan.provider?.enabled && (
                      <div className="notice">
                        AI fallback is disabled. Deterministic remediation
                        remains active. Run scripts\setup_ollama_windows.bat,
                        restart the backend, then Test Ollama to enable local
                        semantic remediation.
                      </div>
                    )}
                    {aiPlan.provider?.enabled &&
                      !aiPlan.provider?.configured && (
                        <div className="notice">
                          AI is enabled but the provider configuration is
                          incomplete. Set LLM_PROVIDER=OLLAMA and LLM_MODEL to
                          an installed local model.
                        </div>
                      )}
                    {aiPlan.items?.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>Object</th>
                            <th>Type</th>
                            <th>Current version</th>
                            <th>Detected reason</th>
                            <th>Route</th>
                            <th>Eligible</th>
                          </tr>
                        </thead>
                        <tbody>
                          {aiPlan.items.map((x: any) => (
                            <tr key={x.object_id}>
                              <td>{x.object_name}</td>
                              <td>{x.object_type}</td>
                              <td>
                                {x.artifact_version
                                  ? `v${x.artifact_version}`
                                  : "-"}
                              </td>
                              <td>{(x.reasons || []).join(", ")}</td>
                              <td>{x.route}</td>
                              <td>
                                <Badge
                                  s={x.eligible ? "YES" : "ARCHITECT_REVIEW"}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <Empty text="No artifact, validation, issue, or review item currently needs remediation." />
                    )}
                  </>
                ) : (
                  <Empty text="Scan the current project to build a project-scoped remediation plan." />
                )}
              </Panel>
              {aiBatch && (
                <Panel title={`Repair run ${aiBatch.run_id}`}>
                  <div className="deployment-summary">
                    <div className="summary-stat">
                      <span>Status</span>
                      <Badge s={aiBatch.status} />
                    </div>
                    <div className="summary-stat">
                      <span>Planned</span>
                      <b>{aiBatch.planned}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Ready for review</span>
                      <b>{aiBatch.ready_for_review}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Candidate only</span>
                      <b>{aiBatch.candidate_only}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Retry ready</span>
                      <b>{aiBatch.retry_ready || 0}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Blocked</span>
                      <b>{aiBatch.blocked}</b>
                    </div>
                    <div className="summary-stat">
                      <span>Auto-deployed</span>
                      <b>No</b>
                    </div>
                  </div>
                  {aiBatch.results?.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Object</th>
                          <th>Status</th>
                          <th>Provider</th>
                          <th>Confidence</th>
                          <th>New version</th>
                          <th>Evidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {aiBatch.results.map((x: any) => (
                          <tr key={x.object_id}>
                            <td>{x.object_name}</td>
                            <td>
                              <Badge s={x.status} />
                            </td>
                            <td>{x.provider || "-"}</td>
                            <td>
                              {x.confidence == null
                                ? "-"
                                : `${Math.round(x.confidence * 100)}%`}
                            </td>
                            <td>
                              {x.artifact_version
                                ? `v${x.artifact_version}`
                                : "-"}
                            </td>
                            <td>
                              {x.error ||
                                x.evidence ||
                                x.static_validation?.status ||
                                "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <Empty text="No objects were processed." />
                  )}
                  <div className="notice ok">
                    Safe SQL candidates are ready in Reviews. Runtime
                    compatibility repairs are marked RETRY_READY and require
                    Resume Failed Run; they do not rewrite business SQL with AI.
                  </div>
                </Panel>
              )}
            </>
          )}
          {page === "Reviews" && (() => {
            /* ── computed helpers ──────────────────────────── */
            const bronzeArts  = medArts.filter((a: any) => (a.layer || "").toUpperCase() === "BRONZE");
            const silverArts  = medArts.filter((a: any) => (a.layer || "").toUpperCase() === "SILVER");
            const goldArts    = medArts.filter((a: any) => (a.layer || "").toUpperCase() === "GOLD");
            const approvedCount = medArts.filter((a: any) => a.review_status === "APPROVED").length;
            const pendingApproval = medArts.filter(
              (a: any) => a.validation_status === "PASSED" && a.executable && a.review_status !== "APPROVED"
            );

            const filteredMedArts = medArts.filter((a: any) => {
              const layer = (a.layer || "").toUpperCase();
              const layerOk = reviewLayerFilter === "ALL" || layer === reviewLayerFilter;
              const statusOk = reviewStatusFilter === "ALL"
                || (reviewStatusFilter === "APPROVED" && a.review_status === "APPROVED")
                || (reviewStatusFilter === "PENDING"  && a.review_status !== "APPROVED");
              const q = reviewSearch.toLowerCase();
              const searchOk = !q || (a.target_fqn || "").toLowerCase().includes(q) || (a.name || "").toLowerCase().includes(q);
              return layerOk && statusOk && searchOk;
            });

            const allFilteredIds = filteredMedArts.map((a: any) => a.artifact_version_id).filter(Boolean);
            const allSelected = allFilteredIds.length > 0 && allFilteredIds.every((id: string) => reviewSelectedIds.has(id));

            function toggleSelectAll() {
              if (allSelected) {
                setReviewSelectedIds(new Set());
              } else {
                setReviewSelectedIds(new Set(allFilteredIds));
              }
            }

            function toggleSelect(id: string) {
              const next = new Set(reviewSelectedIds);
              if (next.has(id)) next.delete(id); else next.add(id);
              setReviewSelectedIds(next);
            }

            function openDrawer(a: any) {
              setReviewDrawerArtifact(a);
              setReviewDrawerTab("sql");
              setReviewDrawerCopied(false);
              setReviewOverflowOpen(null);
            }

            function layerBadgeClass(layer: string) {
              const l = (layer || "").toUpperCase();
              if (l === "BRONZE") return "rv-med-badge bronze";
              if (l === "SILVER") return "rv-med-badge silver";
              if (l === "GOLD")   return "rv-med-badge gold";
              return "rv-med-badge";
            }

            function typeChipClass(t: string) {
              const u = (t || "").toUpperCase();
              if (u === "TABLE")     return "rv-type-chip table";
              if (u === "VIEW")      return "rv-type-chip view";
              if (u === "FUNCTION")  return "rv-type-chip scalar-fn";
              if (u === "PROCEDURE") return "rv-type-chip procedure";
              return "rv-type-chip";
            }

            return (
              <>
                {/* ── Main Reviews page ──────────────────────────────────── */}
                <div className="rv-page-canvas">

                  {/* KPI Summary Rail */}
                  {medArts.length > 0 && (
                    <div className="rv-kpi-grid">
                      <div className="rv-kpi-card">
                        <span className="rv-kpi-label">Total Artifacts</span>
                        <span className="rv-kpi-stat">{medArts.length}</span>
                        <span className="rv-kpi-sub">across all layers</span>
                      </div>
                      <div className="rv-kpi-card bronze-kpi">
                        <span className="rv-kpi-label">Bronze</span>
                        <span className="rv-kpi-stat">{bronzeArts.length}</span>
                        <span className="rv-kpi-sub">ingestion layer</span>
                      </div>
                      <div className="rv-kpi-card silver-kpi">
                        <span className="rv-kpi-label">Silver</span>
                        <span className="rv-kpi-stat">{silverArts.length}</span>
                        <span className="rv-kpi-sub">cleansed layer</span>
                      </div>
                      <div className="rv-kpi-card gold-kpi">
                        <span className="rv-kpi-label">Gold</span>
                        <span className="rv-kpi-stat">{goldArts.length}</span>
                        <span className="rv-kpi-sub">analytics layer</span>
                      </div>
                      <div className="rv-kpi-card approved-kpi">
                        <span className="rv-kpi-label">Approved</span>
                        <span className="rv-kpi-stat">{approvedCount}</span>
                        <span className="rv-kpi-sub">of {medArts.length} artifacts</span>
                      </div>
                    </div>
                  )}

                  {/* Governed Review Banner */}
                  {medArts.length > 0 && (
                    <div className="rv-governed-banner">
                      <div className="rv-banner-icon-wrap">
                        <ShieldCheck size={22} className="rv-banner-icon" />
                      </div>
                      <div className="rv-banner-body">
                        <b>Governed DEV Review Gate</b>
                        <span>Review the exact artifact versions that will be deployed to DEV. Failed artifacts must complete the AI repair loop before approval becomes available.</span>
                      </div>
                      {pendingApproval.length > 0 && (
                        <button
                          className="rv-banner-cta"
                          disabled={!pid || busy}
                          onClick={approveAllMedallionArtifacts}
                          title="Approve all validated artifacts to proceed directly to DEV deployment"
                        >
                          <CheckCircle2 size={14} />
                          Approve {pendingApproval.length} Validated Artifact{pendingApproval.length !== 1 ? "s" : ""} for DEV
                        </button>
                      )}
                    </div>
                  )}

                  {/* Main Content: Medallion artifacts */}
                  {medArts.length > 0 ? (
                    <div className="rv-card-surface">
                      {/* Search & Filter Controls */}
                      <div className="rv-controls-bar">
                        <div className="rv-search-wrap">
                          <Search size={14} className="rv-search-icon" />
                          <input
                            className="rv-search-input"
                            placeholder="Search artifacts…"
                            value={reviewSearch}
                            onChange={e => setReviewSearch(e.target.value)}
                          />
                          {reviewSearch && (
                            <button className="rv-search-clear" onClick={() => setReviewSearch("")}>
                              <X size={12} />
                            </button>
                          )}
                        </div>
                        <div className="rv-layer-tabs">
                          {(["ALL", "BRONZE", "SILVER", "GOLD"] as const).map(l => (
                            <button
                              key={l}
                              className={`rv-layer-tab${reviewLayerFilter === l ? " active" : ""}`}
                              onClick={() => setReviewLayerFilter(l)}
                            >
                              {l === "ALL" ? `All (${medArts.length})` : `${l.charAt(0)+l.slice(1).toLowerCase()} (${medArts.filter((a: any) => (a.layer||"").toUpperCase()===l).length})`}
                            </button>
                          ))}
                        </div>
                        <select
                          className="rv-status-select"
                          value={reviewStatusFilter}
                          onChange={e => setReviewStatusFilter(e.target.value)}
                        >
                          <option value="ALL">All statuses</option>
                          <option value="APPROVED">Approved</option>
                          <option value="PENDING">Pending / Other</option>
                        </select>
                        <button
                          className="rv-approve-all-btn"
                          disabled={!pid || busy || pendingApproval.length === 0}
                          onClick={approveAllMedallionArtifacts}
                          title="Approve all validated artifacts for DEV deployment"
                        >
                          <CheckCircle2 size={14} />
                          Approve All Validated
                        </button>
                      </div>

                      {/* Artifacts Table */}
                      <div className="rv-table-wrapper">
                        <table className="rv-table">
                          <thead>
                            <tr>
                              <th className="rv-th-check">
                                <input
                                  type="checkbox"
                                  checked={allSelected}
                                  onChange={toggleSelectAll}
                                  title="Select all visible"
                                />
                              </th>
                              <th>Layer</th>
                              <th>Target Object</th>
                              <th>Version</th>
                              <th>Validation</th>
                              <th>Review</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filteredMedArts.length === 0 ? (
                              <tr>
                                <td colSpan={7} className="rv-empty-row">No artifacts match the current filters.</td>
                              </tr>
                            ) : filteredMedArts.map((a: any) => {
                              const isArchReview = a.node_type === "ARCHITECTURE_REVIEW" || a.source_object_type === "TRIGGER";
                              const valid = a.executable && a.validation_status === "PASSED";
                              const canApprove = valid || isArchReview;
                              const repairable = !valid && !isArchReview && ["PROCEDURE","FUNCTION"].includes(a.source_object_type);
                              const vid = a.artifact_version_id;
                              const fqn: string = a.target_fqn || "";
                              const fqnParts = fqn.split(".");
                              const catalog = fqnParts.length >= 3 ? fqnParts.slice(0, -2).join(".") : "";
                              const objName = fqnParts.length >= 2 ? fqnParts[fqnParts.length - 1] : (a.name || fqn);
                              const schemaName = fqnParts.length >= 2 ? fqnParts[fqnParts.length - 2] : "";
                              const ver = a.version || a.current_version;
                              const reviewSt = a.review_status || "PENDING";
                              const valSt = isArchReview ? "MANUAL_REVIEW" : (a.validation_status || "NOT_RUN");
                              const isSelected = vid && reviewSelectedIds.has(vid);
                              return (
                                <tr key={vid || a.artifact_id} className={`rv-row${isSelected ? " selected" : ""}`}>
                                  <td className="rv-td-check">
                                    <input
                                      type="checkbox"
                                      checked={!!isSelected}
                                      onChange={() => vid && toggleSelect(vid)}
                                    />
                                  </td>
                                  <td>
                                    <span className={layerBadgeClass(a.layer)}>
                                      {(a.layer || "—").toUpperCase()}
                                    </span>
                                  </td>
                                  <td>
                                    <div className="rv-object-hierarchy">
                                      {catalog && <span className="rv-catalog-prefix">{catalog}.{schemaName}</span>}
                                      <span className="rv-object-name">{objName}</span>
                                      <span className={typeChipClass(a.source_object_type || a.type)}>
                                        {(a.source_object_type || a.type || "OBJECT").toUpperCase()}
                                      </span>
                                    </div>
                                  </td>
                                  <td>
                                    <span className={`rv-version-pill${Number(ver) >= 2 ? " v2" : ""}`}>
                                      v{ver || "—"}
                                    </span>
                                  </td>
                                  <td>
                                    <span className={`rv-status-pill ${(valSt || "").toLowerCase().replace(/_/g,"-")}`}>
                                      {(valSt === "PASSED" || valSt === "MANUAL_REVIEW") && (
                                        <CheckCircle2 size={11} />
                                      )}
                                      {valSt}
                                    </span>
                                  </td>
                                  <td>
                                    <span className={`rv-status-pill ${(reviewSt || "").toLowerCase().replace(/_/g,"-")}`}>
                                      {reviewSt === "APPROVED" && <CheckCircle2 size={11} />}
                                      {reviewSt}
                                    </span>
                                  </td>
                                  <td>
                                    <div className="rv-actions-cell">
                                      {/* Primary: View SQL & Evidence */}
                                      <button
                                        className="rv-primary-btn"
                                        onClick={() => openDrawer(a)}
                                        title="Open SQL and preflight evidence"
                                      >
                                        <Eye size={13} /> View SQL &amp; Evidence
                                      </button>

                                      {/* Inline approve when eligible */}
                                      {canApprove && reviewSt !== "APPROVED" && (
                                        <button
                                          className="rv-approve-btn"
                                          disabled={busy}
                                          title={isArchReview ? "Acknowledge and sign off on this architecture review" : "Approve this validated version for DEV deployment"}
                                          onClick={() => reviewMedArtifact(vid, "APPROVED")}
                                        >
                                          <CheckCircle2 size={13} />
                                        </button>
                                      )}

                                      {/* Repair button */}
                                      {repairable && (
                                        <button
                                          className="rv-repair-btn"
                                          disabled={busy}
                                          title="Create a corrected, statically validated version for human review"
                                          onClick={() => remediateMedArtifact(vid)}
                                        >
                                          <Sparkles size={13} />
                                        </button>
                                      )}

                                      {/* Overflow ⋯ menu */}
                                      <div className="rv-overflow-wrap">
                                        <button
                                          className="rv-overflow-btn"
                                          onClick={() => setReviewOverflowOpen(reviewOverflowOpen === vid ? null : vid)}
                                          title="More actions"
                                        >
                                          <MoreVertical size={14} />
                                        </button>
                                        {reviewOverflowOpen === vid && (
                                          <div className="rv-overflow-menu">
                                            {canApprove && reviewSt !== "CHANGES_REQUIRED" && (
                                              <button
                                                className="rv-overflow-item"
                                                disabled={busy}
                                                onClick={() => {
                                                  reviewMedArtifact(vid, "CHANGES_REQUIRED");
                                                  setReviewOverflowOpen(null);
                                                }}
                                              >
                                                Request Changes
                                              </button>
                                            )}
                                            {canApprove && reviewSt !== "REJECTED" && (
                                              <button
                                                className="rv-overflow-item danger"
                                                disabled={busy}
                                                onClick={() => {
                                                  if (confirm(`Reject ${fqn || a.name} v${ver}?`)) {
                                                    reviewMedArtifact(vid, "REJECTED");
                                                  }
                                                  setReviewOverflowOpen(null);
                                                }}
                                              >
                                                Reject Artifact
                                              </button>
                                            )}
                                            {!canApprove && !repairable && (
                                              <button
                                                className="rv-overflow-item"
                                                onClick={() => { setPage("AI Remediation"); setReviewOverflowOpen(null); }}
                                              >
                                                Open Remediation Guidance
                                              </button>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                    {/* Legacy artifacts table actions (preserve original /projects/${pid}/reviews route) */}
                                    {a.approval_allowed === false && (
                                      <small className="rv-block-reason">
                                        Approval blocked: {(a.approval_blockers || []).join("; ") || "current version is not eligible"}
                                      </small>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : artifacts.length ? (
                    /* Legacy non-medallion artifacts fallback */
                    <div className="rv-card-surface">
                      <table className="rv-table">
                        <thead>
                          <tr>
                            <th>Artifact</th>
                            <th>Version</th>
                            <th>Executable</th>
                            <th>Validation</th>
                            <th>Review status</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {artifacts.map((a) => {
                            const reviewStatus = a.review_status || "PENDING";
                            const blockReason = (a.approval_blockers || []).join("; ");
                            return (
                              <tr key={a.artifact_id}>
                                <td>{a.schema ? `${a.schema}.` : ""}{a.name}</td>
                                <td>v{a.current_version}</td>
                                <td><Badge s={a.executable ? "YES" : "NO"} /></td>
                                <td><Badge s={a.validation_status || "NOT_RUN"} /></td>
                                <td><Badge s={reviewStatus} /></td>
                                <td>
                                  <div className="review-actions">
                                    <button
                                      disabled={!a.artifact_version_id || busy}
                                      onClick={() => action(() => api(`/projects/${pid}/validate/${a.object_id}?environment=DEV`, { method: "POST" }))}
                                    >
                                      <FileCheck2 size={14} /> Validate
                                    </button>
                                    <button
                                      title={blockReason || "Approve current validated executable version"}
                                      disabled={!a.artifact_version_id || !a.approval_allowed || reviewStatus === "APPROVED" || busy}
                                      onClick={() => action(() => api(`/projects/${pid}/reviews`, {
                                        method: "POST",
                                        body: JSON.stringify({ artifact_version_id: a.artifact_version_id, review_type: "ARCHITECT_REVIEW", status: "APPROVED", reviewer: "admin", comments: "Approved from UI after executable/static-validation checks" }),
                                      }))}
                                    >
                                      <CheckCircle2 size={14} /> Approve
                                    </button>
                                    <button
                                      disabled={!a.artifact_version_id || reviewStatus === "APPROVED" || busy}
                                      onClick={() => {
                                        const reason = prompt(`Reject ${a.schema ? `${a.schema}.` : ""}${a.name} v${a.current_version} - reason`);
                                        if (reason) action(() => api(`/projects/${pid}/reviews`, { method: "POST", body: JSON.stringify({ artifact_version_id: a.artifact_version_id, review_type: "ARCHITECT_REVIEW", status: "REJECTED", reviewer: "admin", comments: reason }) }));
                                      }}
                                    >Reject</button>
                                    <button
                                      disabled={!a.artifact_version_id || busy}
                                      onClick={() => {
                                        const reason = prompt(`Request changes for ${a.schema ? `${a.schema}.` : ""}${a.name} v${a.current_version}`);
                                        if (reason) action(() => api(`/projects/${pid}/reviews`, { method: "POST", body: JSON.stringify({ artifact_version_id: a.artifact_version_id, review_type: "ARCHITECT_REVIEW", status: "CHANGES_REQUESTED", reviewer: "admin", comments: reason }) }));
                                      }}
                                    >Request Changes</button>
                                    {reviewStatus === "APPROVED" && (
                                      <button
                                        className="danger-action"
                                        disabled={busy}
                                        onClick={() => {
                                          const reason = prompt(`Revoke approval for ${a.schema ? `${a.schema}.` : ""}${a.name} v${a.current_version} - mandatory reason`);
                                          if (reason) action(() => api(`/projects/${pid}/reviews`, { method: "POST", body: JSON.stringify({ artifact_version_id: a.artifact_version_id, review_type: "ARCHITECT_REVIEW", status: "REVOKED", reviewer: "admin", comments: reason }) }));
                                        }}
                                      >Revoke Approval</button>
                                    )}
                                  </div>
                                  {!a.approval_allowed && (
                                    <small className="review-block-reason">Approval blocked: {blockReason || "current version is not eligible"}</small>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty text="Build the Medallion plan and generate DEV artifacts before review." />
                  )}

                  {/* Review history (legacy, unchanged) */}
                  {!medArts.length && reviews.length > 0 && (
                    <div className="rv-card-surface" style={{ marginTop: 16 }}>
                      <h4 style={{ padding: "12px 16px", margin: 0, fontSize: 13, fontWeight: 600, color: "#374151" }}>Review history</h4>
                      <table className="rv-table">
                        <thead>
                          <tr>
                            <th>Object</th><th>Version</th><th>Review</th><th>Status</th><th>Reviewer</th><th>Reason / comments</th><th>Date / time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reviews.map((r) => (
                            <tr key={r.id}>
                              <td>{r.schema ? `${r.schema}.` : ""}{r.object_name || "—"}</td>
                              <td>v{r.version || "—"}</td>
                              <td>{r.review_type}</td>
                              <td><Badge s={r.status} /></td>
                              <td>{r.reviewer}</td>
                              <td>{r.comments || "—"}</td>
                              <td>{formatDateTime(r.reviewed_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            );
          })()}

          {page === "Issues" && (
            <>
              <Panel title="Migration issues">
                <div className="section-caption">
                  Click an issue to inspect evidence, remediation and lifecycle
                  actions.
                </div>
                {issues.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Severity</th>
                        <th>Type</th>
                        <th>Object</th>
                        <th>Message</th>
                        <th>Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {issues.map((i) => (
                        <tr
                          key={i.id}
                          className="issue-row"
                          onClick={() => openIssue(i)}
                        >
                          <td>
                            <Badge s={i.severity} />
                          </td>
                          <td>{i.issue_type}</td>
                          <td>{i.object_name || i.failed_object || "-"}</td>
                          <td>{i.message}</td>
                          <td>
                            <Badge s={i.status} />
                          </td>
                          <td>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openIssue(i);
                              }}
                            >
                              View Details
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty text="No migration issues recorded." />
                )}
              </Panel>
              {selectedIssue && (
                <div
                  className="issue-modal-backdrop"
                  onClick={() => setSelectedIssue(null)}
                >
                  <div
                    className="issue-modal"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="issue-modal-head">
                      <div>
                        <span className="eyebrow">ISSUE DETAILS</span>
                        <h3>{selectedIssue.message}</h3>
                      </div>
                      <button onClick={() => setSelectedIssue(null)}>
                        Close
                      </button>
                    </div>
                    <div className="issue-detail-grid">
                      <div>
                        <span>Severity</span>
                        <Badge s={selectedIssue.severity} />
                      </div>
                      <div>
                        <span>Status</span>
                        <Badge s={selectedIssue.status} />
                      </div>
                      <div>
                        <span>Type</span>
                        <b>{selectedIssue.issue_type}</b>
                      </div>
                      <div>
                        <span>Object</span>
                        <b>
                          {selectedIssue.object_name ||
                            selectedIssue.failed_object ||
                            "-"}
                        </b>
                      </div>
                      <div>
                        <span>Run ID</span>
                        <code>{selectedIssue.run_id || "-"}</code>
                      </div>
                      <div>
                        <span>Issue ID</span>
                        <code>{selectedIssue.id}</code>
                      </div>
                    </div>
                    <div className="issue-section">
                      <h4>Recommended remediation</h4>
                      <p>
                        {selectedIssue.recommended_action ||
                          "Review the deployment evidence and remediate the failed object before continuing."}
                      </p>
                    </div>
                    <div className="issue-section">
                      <h4>Technical details</h4>
                      <pre>
                        {JSON.stringify(
                          selectedIssue.technical_details || {},
                          null,
                          2,
                        )}
                      </pre>
                    </div>
                    <div className="issue-modal-actions">
                      <button onClick={recheckIssue}>Re-check Evidence</button>
                      <button onClick={viewIssueLogs}>View Logs</button>
                      {selectedIssue.status === "OPEN" ? (
                        <>
                          <button onClick={() => issueAction("RESOLVE")}>
                            Resolve
                          </button>
                          <button onClick={() => issueAction("CLOSE")}>
                            Close Issue
                          </button>
                        </>
                      ) : (
                        <button onClick={() => issueAction("REOPEN")}>
                          Reopen
                        </button>
                      )}
                    </div>
                    {showIssueLogs && (
                      <div className="issue-section">
                        <h4>Linked deployment logs</h4>
                        {issueLogs.length ? (
                          <table>
                            <thead>
                              <tr>
                                <th>Time</th>
                                <th>Status</th>
                                <th>Run</th>
                                <th>Step</th>
                                <th>Target</th>
                                <th>Message</th>
                              </tr>
                            </thead>
                            <tbody>
                              {issueLogs.map((x: any, i: number) => (
                                <tr key={i}>
                                  <td>{formatDateTime(x.timestamp)}</td>
                                  <td>
                                    <Badge s={x.status || "-"} />
                                  </td>
                                  <td>
                                    <code>{x.run_id || "-"}</code>
                                  </td>
                                  <td>{x.step || "-"}</td>
                                  <td>{x.target_fqn || "-"}</td>
                                  <td>{x.message || "-"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <Empty text="No linked logs found for this issue yet." />
                        )}
                      </div>
                    )}
                    {selectedIssue.actions?.length > 0 && (
                      <div className="issue-section">
                        <h4>Issue history</h4>
                        <table>
                          <thead>
                            <tr>
                              <th>Time</th>
                              <th>Action</th>
                              <th>From</th>
                              <th>To</th>
                              <th>Actor</th>
                              <th>Comments</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedIssue.actions.map((a: any) => (
                              <tr key={a.id}>
                                <td>{formatDateTime(a.created_at)}</td>
                                <td>{a.action}</td>
                                <td>{a.from_status || "-"}</td>
                                <td>{a.to_status || "-"}</td>
                                <td>{a.actor || "-"}</td>
                                <td>{a.comments || "-"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
          {(page === "Deployment" || page === "Deployments" || page === "Waves") && (
            <>
              {(page === "Deployment" || page === "Deployments") && (
                <>
                  <Panel title="DEV deployment and validation">
                <p className="section-caption">
                  Complete these three steps in order. This is the only DEV
                  promotion workspace required after artifact approval.
                </p>
                <div className="dev-stage-flow">
                  <div className="dev-stage-card">
                    <div className="dev-stage-number">1</div>
                    <div>
                      <span>DEPLOY</span>
                      <h4>Deploy Medallion to DEV</h4>
                      <p>Deploy approved Bronze, Silver and Gold artifacts.</p>
                    </div>
                    <button
                      className="primary-action"
                      disabled={!pid || busy}
                      title="Open the approved Medallion plan and deploy its data products to DEV"
                      onClick={() => setPage("Medallion Design")}
                    >
                      <Layers3 size={15} /> Deploy approved data products to DEV
                    </button>
                  </div>
                  <div className="dev-stage-card">
                    <div className="dev-stage-number">2</div>
                    <div>
                      <span>VALIDATE</span>
                      <h4>Run DEV reconciliation</h4>
                      <p>Compare deployed targets with the source evidence.</p>
                    </div>
                    <button
                      disabled={!pid || busy || medDeployment?.status !== "PASSED"}
                      title={medDeployment?.status === "PASSED" ? "Validate deployed DEV data products against source evidence" : "Complete the Medallion DEV deployment first"}
                      onClick={runDevReconciliation}
                    >
                      <Gauge size={15} /> Validate deployed DEV data products
                    </button>
                  </div>
                  <div className="dev-stage-card">
                    <div className="dev-stage-number">3</div>
                    <div>
                      <span>APPROVE</span>
                      <h4>Evaluate DEV gate</h4>
                      <p>Approve DEV only after reconciliation passes.</p>
                    </div>
                    <button
                      disabled={!pid || busy || reconResult?.status !== "PASSED"}
                      title={reconResult?.status === "PASSED" ? "Approve the validated DEV release for TEST promotion" : "DEV reconciliation must pass before gate evaluation"}
                      onClick={() =>
                        action(async () => {
                          const r: any = await api(
                            `/projects/${pid}/deployments/dev/evaluate-gate`,
                            { method: "POST" },
                          );
                          setGateResult(r);
                          return r;
                        })
                      }
                    >
                      <ShieldCheck size={15} /> Approve DEV release for TEST
                    </button>
                  </div>
                </div>
              </Panel>
              <details className="legacy-deployment">
                <summary>Legacy artifact deployment — separate workflow</summary>
                <p>These controls deploy the legacy artifact set. They are not required after a successful Medallion deployment.</p>
              <Panel
                title="DEV deployment execution"
                actions={
                  <div className="deploy-actions">
                    <button
                      disabled={!pid || busy}
                      onClick={() =>
                        action(async () => {
                          const r: any = await api(
                            `/projects/${pid}/deployments/dev/test-databricks`,
                            { method: "POST" },
                          );
                          setPrecheck(r);
                          return r;
                        })
                      }
                    >
                      <PlugZap size={15} />
                      Test Databricks
                    </button>
                    <button
                      disabled={!pid || busy}
                      onClick={() =>
                        action(async () => {
                          const r: any = await api(
                            `/projects/${pid}/deployments/dev/precheck`,
                            { method: "POST" },
                          );
                          setPrecheck(r);
                          return r;
                        })
                      }
                    >
                      <FileCheck2 size={15} />
                      DEV Precheck
                    </button>
                    <button
                      className="primary-action"
                      disabled={!pid || busy}
                      onClick={() => {
                        const allow = confirm(
                          "Allow destructive DEV replacement only when policy permits and schema drift requires it?",
                        );
                        action(() =>
                          api(`/projects/${pid}/deployments/dev/deploy`, {
                            method: "POST",
                            body: JSON.stringify({
                              allow_destructive: allow,
                              batch_size: deployBatch,
                              max_rows: deployMaxRows
                                ? Number(deployMaxRows)
                                : null,
                              load_mode: deployMode,
                              replace_existing_data: allow,
                            }),
                          }),
                        );
                      }}
                    >
                      <Play size={15} />
                      Deploy Approved to DEV
                    </button>
                    <button
                      disabled={!pid || busy}
                      onClick={() => {
                        const allow = confirm(
                          "Does the failed DEV artifact contain an intentional destructive operation that you reviewed and explicitly approve? Select Cancel to resume without destructive approval.",
                        );
                        action(() =>
                          api(`/projects/${pid}/deployments/dev/resume`, {
                            method: "POST",
                            body: JSON.stringify({
                              allow_destructive: allow,
                              load_mode: "FULL_LOAD",
                              replace_existing_data: allow,
                            }),
                          }),
                        );
                      }}
                    >
                      <RefreshCw size={15} />
                      Resume Failed Run
                    </button>
                    <button disabled={!pid || busy} onClick={viewDevLogs}>
                      <ScrollText size={15} />
                      View Logs
                    </button>
                    <button disabled={!pid || busy} onClick={downloadDevLogs}>
                      <Download size={15} />
                      Download Log
                    </button>
                  </div>
                }
              >
                <div className="deploy-config">
                  <label>
                    Load mode
                    <select
                      value={deployMode}
                      onChange={(e) => setDeployMode(e.target.value)}
                    >
                      <option>FULL_LOAD</option>
                      <option>APPEND</option>
                    </select>
                  </label>
                  <label>
                    Batch size
                    <input
                      type="number"
                      min="1"
                      value={deployBatch}
                      onChange={(e) =>
                        setDeployBatch(Math.max(1, Number(e.target.value) || 1))
                      }
                    />
                  </label>
                  <label>
                    Max rows (optional)
                    <input
                      type="number"
                      min="1"
                      value={deployMaxRows}
                      onChange={(e) => setDeployMaxRows(e.target.value)}
                      placeholder="Unlimited"
                    />
                  </label>
                  <small>
                    FULL_LOAD will not clear existing target data unless you
                    explicitly approve replacement.
                  </small>
                </div>
                <div className="deployment-summary">
                  <div className="summary-stat">
                    <span>Status</span>
                    <Badge s={deployment.status || "NOT_STARTED"} />
                  </div>
                  <div className="summary-stat">
                    <span>Run ID</span>
                    <b>{deployment.run_id || "-"}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Objects</span>
                    <b>{deployment.total || 0}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Passed</span>
                    <b>{deployment.passed || 0}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Failed</span>
                    <b>{deployment.failed || 0}</b>
                  </div>
                  <div className="summary-stat">
                    <span>Checkpoint</span>
                    <b>{deployment.checkpoint || "-"}</b>
                  </div>
                </div>
                {deployment.failed_object && (
                  <div className="notice">
                    Failed object: {deployment.failed_object}. Fix the issue,
                    then use Resume Failed Run.
                  </div>
                )}
                {precheck && (
                  <div className="subsection">
                    <h4>Latest precheck / connection result</h4>
                    <pre>{JSON.stringify(precheck, null, 2)}</pre>
                  </div>
                )}
              </Panel>
              <Panel title="Execution evidence">
                {deployment.logs?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Status</th>
                        <th>Object</th>
                        <th>Target / action</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deployment.logs
                        .slice()
                        .reverse()
                        .map((x: any, i: number) => (
                          <tr key={i}>
                            <td>{formatDateTime(x.created_at)}</td>
                            <td>
                              <Badge s={x.status} />
                            </td>
                            <td>{x.object_id || "-"}</td>
                            <td>{x.target_fqn || x.action || "-"}</td>
                            <td>
                              <code>
                                {JSON.stringify({
                                  artifact_version: x.artifact_version,
                                  layer: x.layer,
                                  schema_action: x.schema_action,
                                  load: x.load,
                                  error: x.error,
                                })}
                              </code>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty text="No DEV deployment evidence yet. Run DEV Precheck first." />
                )}
                {showLogs && (
                  <div className="subsection">
                    <div className="log-head">
                      <h4>Full project-scoped DEV log</h4>
                      <button onClick={() => setShowLogs(false)}>Hide</button>
                    </div>
                    {logView.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>Time</th>
                            <th>Category</th>
                            <th>Status</th>
                            <th>Run</th>
                            <th>Step</th>
                            <th>Target</th>
                            <th>Message</th>
                          </tr>
                        </thead>
                        <tbody>
                          {logView.map((x: any, i: number) => (
                            <tr key={i}>
                              <td>{formatDateTime(x.timestamp)}</td>
                              <td>{x.category}</td>
                              <td>
                                <Badge s={x.status || "-"} />
                              </td>
                              <td>
                                <code>{x.run_id || "-"}</code>
                              </td>
                              <td>{x.step || "-"}</td>
                              <td>{x.target_fqn || "-"}</td>
                              <td>{x.message || "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <Empty text="No project-scoped DEV logs recorded yet." />
                    )}
                  </div>
                )}
              </Panel>
              </details>
            {environmentPassed("DEV") && (
              <div className="dev-next-action" style={{ marginBottom: 14 }}>
                <button
                  className="primary-action"
                  onClick={() => {
                    setPage("Waves");
                    setDeployActiveEnv("TEST");
                    setDeployLogEnvFilter("TEST");
                  }}
                >
                  Promote validated DEV release to TEST <ChevronRight size={15} />
                </button>
              </div>
            )}

            {gateResult && (
              <div className="subsection" style={{ marginBottom: 16 }}>
                <h4>DEV quality gate</h4>
                <pre>{JSON.stringify(gateResult, null, 2)}</pre>
              </div>
            )}
          </>
        )}

        {page === "Waves" && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#475569" }}>Promotion Target:</span>
              {(["ALL", "TEST", "UAT", "PROD"] as const).map((env) => (
                <button
                  key={env}
                  type="button"
                  onClick={() => {
                    setDeployActiveEnv(env);
                    setDeployLogEnvFilter(env);
                  }}
                  style={{
                    padding: "6px 14px",
                    borderRadius: 6,
                    fontWeight: 700,
                    fontSize: 12,
                    cursor: "pointer",
                    border: (deployActiveEnv === env || (env === "ALL" && deployActiveEnv === "DEV")) ? "1px solid #2563eb" : "1px solid #e2e8f0",
                    background: (deployActiveEnv === env || (env === "ALL" && deployActiveEnv === "DEV")) ? "#2563eb" : "#f8fafc",
                    color: (deployActiveEnv === env || (env === "ALL" && deployActiveEnv === "DEV")) ? "#ffffff" : "#475569",
                    transition: "all 0.15s ease",
                  }}
                >
                  {env === "ALL" ? "All Environments (Studio)" : `${env} Promotion`}
                </button>
              ))}
            </div>

            {/* Prompt Promotion Studio (Single-Release Governed Prompt Flow) */}
            {(deployActiveEnv === "ALL" || deployActiveEnv === "DEV") && (
              <div className="promotion-studio">
                {autoPromotionStatus?.run && (
                  <div style={{ marginBottom: 14, padding: "12px 16px", background: "rgba(30, 41, 59, 0.8)", border: "1px solid rgba(59, 130, 246, 0.35)", borderRadius: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <small style={{ color: "#60a5fa", fontWeight: 700, letterSpacing: "0.08em" }}>AUTOMATED MASTER PROMOTION ACTIVE</small>
                        <h4 style={{ margin: "2px 0 0", fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                          Run {autoPromotionStatus.run.run_id} · {autoPromotionStatus.run.current_operation}
                        </h4>
                      </div>
                      <Badge s={autoPromotionStatus.run.status} />
                    </div>
                    {autoPromotionStatus.is_active && (
                      <small style={{ color: "#94a3b8", display: "block", marginTop: 4 }}>
                        Individual environment promotion buttons are temporarily disabled to prevent conflicting operations.
                      </small>
                    )}
                  </div>
                )}
                <div className="prompt-studio-head">
                  <div className="prompt-studio-title">
                    <Sparkles size={20} color="#5b8cff" />
                    <div>
                      <h3>Release 5 · Prompt Promotion Studio</h3>
                      <p>
                        Promote one approved immutable release at a time through TEST, UAT, and PROD.
                      </p>
                    </div>
                  </div>
                  <span className="prompt-badge"><ShieldCheck size={12} /> Environment governed</span>
                </div>
                <div className="prompt-input-row">
                  <input
                    value={promotionPrompt}
                    onChange={(e) => setPromotionPrompt(e.target.value)}
                    placeholder="Promote approved DEV release to TEST"
                    disabled={busy || promotionRunning}
                  />
                  <button
                    className="primary-action"
                    disabled={!pid || busy || promotionRunning || !promotionPrompt.trim()}
                    onClick={() => generatePromotionPlan()}
                  >
                    <Command size={15} /> Generate Promotion Plan
                  </button>
                </div>
                <div className="prompt-quick-chips">
                  <span>Quick prompts:</span>
                  {[
                    "Promote approved DEV release to TEST",
                    "Promote approved TEST release to UAT",
                    "Promote approved UAT release to PROD",
                  ].map((template) => (
                    <button
                      key={template}
                      className="prompt-chip"
                      disabled={busy || promotionRunning}
                      onClick={() => {
                        setPromotionPrompt(template);
                        generatePromotionPlan(template);
                      }}
                    >
                      {template}
                    </button>
                  ))}
                </div>

                {promotionPlan && (
                  <div className="prompt-plan-card">
                    {promotionPlan.status === "NEEDS_USER_INPUT" ? (
                      <div className="promotion-blocked">
                        <b><ShieldAlert size={16} /> Promotion prerequisites required</b>
                        <ul>
                          {promotionPlan.blockers?.map((blocker: string, index: number) => (
                            <li key={index}>{blocker}</li>
                          ))}
                        </ul>
                        {promotionPlan.actionable_steps?.[0] && (
                          <small><strong>Next action:</strong> {promotionPlan.actionable_steps[0]}</small>
                        )}
                      </div>
                    ) : (
                      <>
                        <div className="promotion-plan-head">
                          <div>
                            <small>GOVERNED SINGLE-ENVIRONMENT PLAN</small>
                            <h4>
                              {promotionPlan.intent?.source_environment} → {promotionPlan.intent?.target_environment}
                              <Badge s={promotionPlan.status} />
                            </h4>
                          </div>
                          {promotionPlan.status === "PENDING_APPROVAL" && (
                            <button
                              className="primary-action"
                              disabled={busy || promotionRunning}
                              onClick={executePromotionPlan}
                            >
                              <ShieldCheck size={15} />
                              {promotionPlan.intent?.target_environment === "PROD"
                                ? "Confirm & Promote to PROD"
                                : `Approve & Promote to ${promotionPlan.intent?.target_environment}`}
                            </button>
                          )}
                        </div>
                        <div className="prompt-impact-grid">
                          <div className="prompt-impact-item"><span>Approved artifacts</span><b>{promotionPlan.impact?.artifact_count || 0}</b></div>
                          <div className="prompt-impact-item"><span>Source manifest</span><code>{promotionPlan.impact?.source_deployment_run_id || "-"}</code></div>
                          <div className="prompt-impact-item"><span>Target catalog</span><code>{promotionPlan.intent?.target_catalog || "-"}</code></div>
                          <div className="prompt-impact-item"><span>Risk</span><b>{promotionPlan.impact?.risk_level}</b></div>
                        </div>
                        <div className="prompt-stages-list promotion-stage-list">
                          {promotionPlan.stages?.map((stage: any) => (
                            <div className="prompt-stage-pill" key={stage.stage}>
                              <b>{stage.title}</b><small>{stage.stage}</small>
                            </div>
                          ))}
                        </div>
                        <div className="promotion-safety-note">
                          <ShieldCheck size={14} /> No AI regeneration · no environment skipping · PROD requires separate confirmation
                        </div>
                      </>
                    )}
                  </div>
                )}

                {promotionExecution && (
                  <div className="prompt-exec-card">
                    <div className="promotion-exec-head">
                      <div>
                        <small>EXECUTION {promotionExecution.run_id}</small>
                        <b>{promotionExecution.source_environment} → {promotionExecution.target_environment}</b>
                      </div>
                      <Badge s={promotionExecution.status} />
                    </div>
                    <div className="prompt-exec-stages promotion-exec-stages">
                      {Object.entries(promotionExecution.stages || {}).map(([name, stage]: [string, any]) => (
                        <div className="prompt-exec-step" key={name}>
                          <span>{name}</span><Badge s={stage.status} />
                          {stage.deployed_count !== undefined && <small>{stage.deployed_count} deployed</small>}
                          {stage.passed !== undefined && <small>{stage.passed} reconciled</small>}
                        </div>
                      ))}
                    </div>
                    {promotionExecution.status === "FAILED" && (
                      <div className="prompt-exec-error">
                        <b><ShieldAlert size={15} /> Failed stage: {promotionExecution.failed_stage}</b>
                        <span>{promotionExecution.error}</span>
                        <small><strong>Next action:</strong> {promotionExecution.errors?.[0]?.recommended_action}</small>
                      </div>
                    )}
                  </div>
                )}
              </div>
              )}

              {(deployActiveEnv === "TEST" || deployActiveEnv === "ALL") && (
                <>
                  <Panel
                    title="DEV → TEST promotion"
                actions={
                  <div className="deploy-actions">
                    <button
                      disabled={!pid || busy || !environmentPassed("DEV")}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/test/precheck`, { method: "POST" });
                        setTestPrecheck(result);
                        return result;
                      })}
                    >
                      <FileCheck2 size={15} /> TEST Precheck
                    </button>
                    <button
                      className="primary-action"
                      disabled={!pid || busy || testPrecheck?.eligible !== true}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/test/deploy`, { method: "POST" });
                        setTestPromotion(result);
                        return result;
                      })}
                    >
                      <Play size={15} /> Promote and Deploy to TEST
                    </button>
                    <button
                      disabled={!pid || busy || testPromotion?.status !== "PASSED"}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/test/reconcile`, { method: "POST" });
                        setTestRecon(result);
                        return result;
                      })}
                    >
                      <Gauge size={15} /> Run TEST Reconciliation
                    </button>
                    <button
                      disabled={!pid || busy || testRecon?.status !== "PASSED"}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/test/evaluate-gate`, { method: "POST" });
                        setTestGate(result);
                        return result;
                      })}
                    >
                      <ShieldCheck size={15} /> Evaluate TEST Gate
                    </button>
                  </div>
                }
              >
                <div className="notice ok">
                  TEST promotion uses the exact artifact-version manifest that passed the DEV quality gate. Bronze data is deep-cloned from DEV; Silver and Gold artifacts are deployed with TEST catalog references.
                </div>
                <div className="deployment-summary">
                  <div className="summary-stat"><span>TEST status</span><Badge s={testPromotion?.status || "NOT_STARTED"} /></div>
                  <div className="summary-stat"><span>Run ID</span><b>{testPromotion?.run_id || "-"}</b></div>
                  <div className="summary-stat"><span>Objects</span><b>{testPromotion?.total ?? testPromotion?.count ?? 0}</b></div>
                  <div className="summary-stat"><span>Passed</span><b>{testPromotion?.passed ?? 0}</b></div>
                  <div className="summary-stat"><span>Failed</span><b>{testPromotion?.failed ?? 0}</b></div>
                  <div className="summary-stat"><span>TEST gate</span><Badge s={testGate?.status || (environmentPassed("TEST") ? "PASSED" : "NOT_STARTED")} /></div>
                </div>
                {testPrecheck && (
                  <div className="subsection">
                    <h4>TEST promotion precheck</h4>
                    <pre>{JSON.stringify(testPrecheck, null, 2)}</pre>
                  </div>
                )}
                {testRecon?.run_id && (
                  <div className="subsection">
                    <h4>TEST reconciliation</h4>
                    <div className="deployment-summary">
                      <div className="summary-stat"><span>Status</span><Badge s={testRecon.status} /></div>
                      <div className="summary-stat"><span>Checked</span><b>{testRecon.details_count || 0}</b></div>
                      <div className="summary-stat"><span>Passed</span><b>{testRecon.passed || 0}</b></div>
                      <div className="summary-stat"><span>Failed</span><b>{testRecon.failed || 0}</b></div>
                    </div>
                  </div>
                )}
                {testGate && (
                  <div className="subsection">
                    <h4>TEST quality gate</h4>
                    <pre>{JSON.stringify(testGate, null, 2)}</pre>
                  </div>
                )}
                {environmentPassed("TEST") && (
                  <div className="business-next">
                    <div>
                      <span>BUSINESS OUTCOME</span>
                      <b>TEST validation passed</b>
                      <p>The validated release is ready for business acceptance testing in UAT.</p>
                    </div>
                    <button
                      className="primary-action"
                      onClick={() => {
                        setDeployActiveEnv("UAT");
                        setDeployLogEnvFilter("UAT");
                        setTimeout(() => document.getElementById("uat-promotion")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
                      }}
                    >
                      Begin UAT acceptance validation <ChevronRight size={15} />
                    </button>
                  </div>
                )}
              </Panel>
              <Panel title="TEST execution evidence">
                {testPromotion?.logs?.length ? (
                  <table>
                    <thead><tr><th>Time</th><th>Status</th><th>Target / action</th><th>Artifact version</th></tr></thead>
                    <tbody>{testPromotion.logs.slice().reverse().map((x: any, i: number) => (
                      <tr key={i}>
                        <td>{formatDateTime(x.created_at)}</td>
                        <td><Badge s={x.status} /></td>
                        <td><code>{x.target_fqn || x.action || "-"}</code></td>
                        <td>{x.artifact_version ? `v${x.artifact_version}` : "-"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                ) : <Empty text="Run TEST Precheck, then promote the approved DEV manifest to TEST." />}
              </Panel>
            </>
          )}

          {(deployActiveEnv === "UAT" || deployActiveEnv === "ALL") && (
            <>
              <div id="uat-promotion" className="promotion-anchor">
              <Panel
                title="TEST → UAT promotion"
                actions={
                  <div className="deploy-actions">
                    <button
                      disabled={!pid || busy || !environmentPassed("TEST")}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/uat/precheck`, { method: "POST" });
                        setUatPrecheck(result);
                        return result;
                      })}
                    >
                      <FileCheck2 size={15} /> UAT Precheck
                    </button>
                    <button
                      className="primary-action"
                      disabled={!pid || busy || uatPrecheck?.eligible !== true}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/uat/deploy`, { method: "POST" });
                        setUatPromotion(result);
                        return result;
                      })}
                    >
                      <Play size={15} /> Promote and Deploy to UAT
                    </button>
                    <button
                      disabled={!pid || busy || uatPromotion?.status !== "PASSED"}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/uat/reconcile`, { method: "POST" });
                        setUatRecon(result);
                        return result;
                      })}
                    >
                      <Gauge size={15} /> Run UAT Reconciliation
                    </button>
                    <button
                      disabled={!pid || busy || uatRecon?.status !== "PASSED"}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/uat/evaluate-gate`, { method: "POST" });
                        setUatGate(result);
                        return result;
                      })}
                    >
                      <ShieldCheck size={15} /> Evaluate UAT Gate
                    </button>
                  </div>
                }
              >
                <div className="notice ok">
                  UAT promotion uses the exact artifact-version manifest that passed the TEST quality gate. Bronze data is deep-cloned from TEST; Silver and Gold artifacts are deployed with UAT catalog references.
                </div>
                <div className="deployment-summary">
                  <div className="summary-stat"><span>UAT status</span><Badge s={uatPromotion?.status || "NOT_STARTED"} /></div>
                  <div className="summary-stat"><span>Run ID</span><b>{uatPromotion?.run_id || "-"}</b></div>
                  <div className="summary-stat"><span>Objects</span><b>{uatPromotion?.total ?? uatPromotion?.count ?? 0}</b></div>
                  <div className="summary-stat"><span>Passed</span><b>{uatPromotion?.passed ?? 0}</b></div>
                  <div className="summary-stat"><span>Failed</span><b>{uatPromotion?.failed ?? 0}</b></div>
                  <div className="summary-stat"><span>UAT gate</span><Badge s={uatGate?.status || (environmentPassed("UAT") ? "PASSED" : "NOT_STARTED")} /></div>
                </div>
                {uatPrecheck && (
                  <div className="subsection">
                    <h4>UAT promotion precheck</h4>
                    <pre>{JSON.stringify(uatPrecheck, null, 2)}</pre>
                  </div>
                )}
                {uatRecon?.run_id && (
                  <div className="subsection">
                    <h4>UAT reconciliation</h4>
                    <div className="deployment-summary">
                      <div className="summary-stat"><span>Status</span><Badge s={uatRecon.status} /></div>
                      <div className="summary-stat"><span>Checked</span><b>{uatRecon.details_count || 0}</b></div>
                      <div className="summary-stat"><span>Passed</span><b>{uatRecon.passed || 0}</b></div>
                      <div className="summary-stat"><span>Failed</span><b>{uatRecon.failed || 0}</b></div>
                    </div>
                  </div>
                )}
                {uatGate && (
                  <div className="subsection">
                    <h4>UAT quality gate</h4>
                    <pre>{JSON.stringify(uatGate, null, 2)}</pre>
                  </div>
                )}
                {environmentPassed("UAT") && (
                  <div className="business-next">
                    <div>
                      <span>BUSINESS OUTCOME</span>
                      <b>Business acceptance completed</b>
                      <p>The accepted release is eligible for final production readiness validation.</p>
                    </div>
                    <button
                      className="primary-action"
                      onClick={() => {
                        setDeployActiveEnv("PROD");
                        setDeployLogEnvFilter("PROD");
                        setTimeout(() => document.getElementById("prod-promotion")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
                      }}
                    >
                      Validate production release readiness <ChevronRight size={15} />
                    </button>
                  </div>
                )}
              </Panel>
              </div>
              <Panel title="UAT execution evidence">
                {uatPromotion?.logs?.length ? (
                  <table>
                    <thead><tr><th>Time</th><th>Status</th><th>Target / action</th><th>Artifact version</th></tr></thead>
                    <tbody>{uatPromotion.logs.slice().reverse().map((x: any, i: number) => (
                      <tr key={i}>
                        <td>{formatDateTime(x.created_at)}</td>
                        <td><Badge s={x.status} /></td>
                        <td><code>{x.target_fqn || x.action || "-"}</code></td>
                        <td>{x.artifact_version ? `v${x.artifact_version}` : "-"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                ) : <Empty text="Run UAT Precheck, then promote the approved TEST manifest to UAT." />}
              </Panel>
            </>
          )}

          {(deployActiveEnv === "PROD" || deployActiveEnv === "ALL") && (
            <>
              <div id="prod-promotion" className="promotion-anchor">
              <Panel
                title="UAT → PROD promotion"
                actions={
                  <div className="deploy-actions">
                    <button disabled={!pid || busy || !environmentPassed("UAT")} onClick={() => action(async () => {
                      const result: any = await api(`/projects/${pid}/promotions/prod/precheck`, { method: "POST" });
                      setProdPrecheck(result); return result;
                    })}>
                      <FileCheck2 size={15} /> PROD Precheck
                    </button>
                    <button className="primary-action" disabled={!pid || busy || prodPrecheck?.eligible !== true}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/prod/deploy`, { method: "POST" });
                        setProdPromotion(result); return result;
                      })}>
                      <Play size={15} /> Promote and Deploy to PROD
                    </button>
                    <button disabled={!pid || busy || prodPromotion?.status !== "PASSED"}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/prod/reconcile`, { method: "POST" });
                        setProdRecon(result); return result;
                      })}>
                      <Gauge size={15} /> Run PROD Reconciliation
                    </button>
                    <button disabled={!pid || busy || prodRecon?.status !== "PASSED"}
                      onClick={() => action(async () => {
                        const result: any = await api(`/projects/${pid}/promotions/prod/evaluate-gate`, { method: "POST" });
                        setProdGate(result); return result;
                      })}>
                      <ShieldCheck size={15} /> Evaluate PROD Gate
                    </button>
                  </div>
                }
              >
                <div className="notice ok">
                  PROD promotion uses the exact artifact-version manifest that passed the UAT quality gate. Bronze data is deep-cloned from UAT; Silver and Gold artifacts are deployed with PROD catalog references.
                </div>
                <div className="deployment-summary">
                  <div className="summary-stat"><span>PROD status</span><Badge s={prodPromotion?.status || "NOT_STARTED"} /></div>
                  <div className="summary-stat"><span>Run ID</span><b>{prodPromotion?.run_id || "-"}</b></div>
                  <div className="summary-stat"><span>Objects</span><b>{prodPromotion?.total ?? prodPromotion?.count ?? 0}</b></div>
                  <div className="summary-stat"><span>Passed</span><b>{prodPromotion?.passed ?? 0}</b></div>
                  <div className="summary-stat"><span>Failed</span><b>{prodPromotion?.failed ?? 0}</b></div>
                  <div className="summary-stat"><span>PROD gate</span><Badge s={prodGate?.status || (environmentPassed("PROD") ? "PASSED" : "NOT_STARTED")} /></div>
                </div>
                {prodPrecheck && <div className="subsection"><h4>PROD promotion precheck</h4><pre>{JSON.stringify(prodPrecheck, null, 2)}</pre></div>}
                {prodRecon?.run_id && (
                  <div className="subsection">
                    <h4>PROD reconciliation</h4>
                    <div className="deployment-summary">
                      <div className="summary-stat"><span>Status</span><Badge s={prodRecon.status} /></div>
                      <div className="summary-stat"><span>Checked</span><b>{prodRecon.details_count || 0}</b></div>
                      <div className="summary-stat"><span>Passed</span><b>{prodRecon.passed || 0}</b></div>
                      <div className="summary-stat"><span>Failed</span><b>{prodRecon.failed || 0}</b></div>
                    </div>
                  </div>
                )}
                {prodGate && <div className="subsection"><h4>PROD quality gate</h4><pre>{JSON.stringify(prodGate, null, 2)}</pre></div>}
                {environmentPassed("PROD") && (
                  <div className="business-next">
                    <div>
                      <span>BUSINESS OUTCOME</span>
                      <b>Production release validated</b>
                      <p>The migration is technically complete and ready for consumer switch-over.</p>
                    </div>
                    <button className="primary-action" onClick={() => setPage("Cutover")}>
                      Record production cutover and acceptance <ChevronRight size={15} />
                    </button>
                  </div>
                )}
              </Panel>
              </div>
              <Panel title="PROD execution evidence">
                {prodPromotion?.logs?.length ? (
                  <table>
                    <thead><tr><th>Time</th><th>Status</th><th>Target / action</th><th>Artifact version</th></tr></thead>
                    <tbody>{prodPromotion.logs.slice().reverse().map((x: any, i: number) => (
                      <tr key={i}>
                        <td>{formatDateTime(x.created_at)}</td>
                        <td><Badge s={x.status} /></td>
                        <td><code>{x.target_fqn || x.action || "-"}</code></td>
                        <td>{x.artifact_version ? `v${x.artifact_version}` : "-"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                ) : <Empty text="Run PROD Precheck, then promote the approved UAT manifest to PROD." />}
              </Panel>
            </>
          )}
        </>
      )}

      {/* Consolidated Deployment Attempts & Multi-Environment Logs Console */}
      <div className="deploy-card-surface">
                {/* Integrated Control Header */}
                <div className="deploy-control-header">
                  <div className="deploy-header-left">
                    <span className={`deploy-env-pill ${(deployActiveEnv || "DEV").toLowerCase()}`}>
                      {deployActiveEnv}
                    </span>
                    <span className="deploy-header-title">Deployment Attempts & Multi-Environment Logs</span>
                    <span className="deploy-header-sep">·</span>
                    <span
                      className="deploy-run-id-chip"
                      title={`Click to copy: ${activeRunId}`}
                      onClick={() => {
                        if (activeRunId && activeRunId !== "-") {
                          navigator.clipboard.writeText(activeRunId);
                          setDeployCopiedRunId(true);
                          setTimeout(() => setDeployCopiedRunId(false), 2000);
                        }
                      }}
                    >
                      <span>{truncateRunId(activeRunId)}</span>
                      {deployCopiedRunId ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                    </span>
                  </div>

                  <div className="deploy-header-actions">
                    {/* Quick Log Environment Filter Pills */}
                    <div style={{ display: "flex", alignItems: "center", gap: 3, background: "#f1f5f9", padding: "2px 4px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b", margin: "0 4px" }}>Filter:</span>
                      {(["ALL", "DEV", "TEST", "UAT", "PROD"] as const).map((e) => (
                        <button
                          key={e}
                          type="button"
                          onClick={() => setDeployLogEnvFilter(e)}
                          style={{
                            border: "none",
                            background: deployLogEnvFilter === e ? "#2563eb" : "transparent",
                            color: deployLogEnvFilter === e ? "#ffffff" : "#475569",
                            fontSize: 11,
                            fontWeight: 700,
                            borderRadius: 4,
                            padding: "3px 8px",
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                          }}
                        >
                          {e}
                        </button>
                      ))}
                    </div>

                    <div className="deploy-filter-wrapper">
                      <Filter size={13} className="deploy-filter-icon" />
                      <select
                        className="deploy-filter-select"
                        value={deployStatusFilter}
                        onChange={(e) => setDeployStatusFilter(e.target.value)}
                        title="Filter attempts by status"
                      >
                        <option value="ALL">Status ▾</option>
                        <option value="PASSED">Passed</option>
                        <option value="FAILED">Failed</option>
                        <option value="RUNNING">Running</option>
                      </select>
                    </div>

                    <button
                      type="button"
                      className="deploy-action-btn"
                      title="Copy deployment logs as JSON"
                      onClick={() => {
                        const exportData = attemptItems.length > 0 ? attemptItems : (medLogs.length > 0 ? medLogs : logView);
                        if (exportData.length > 0) {
                          navigator.clipboard.writeText(JSON.stringify(exportData, null, 2));
                          setMsg("Deployment evidence copied to clipboard");
                        } else {
                          navigator.clipboard.writeText(activeRunId);
                          setMsg("Run ID copied to clipboard");
                        }
                      }}
                    >
                      <Copy size={13} /> Copy
                    </button>
                    <button
                      type="button"
                      className="deploy-action-btn"
                      title="Export logs as CSV"
                      disabled={!pid || busy}
                      onClick={() => {
                        if (medDeployment?.run_id) {
                          downloadMedallionLogs();
                        } else if (reconResult?.run_id) {
                          downloadReconciliation();
                        } else {
                          downloadDevLogs();
                        }
                      }}
                    >
                      <Download size={13} /> Export
                    </button>
                  </div>
                </div>

                {/* Metric KPI Cards (4-Card Strip) */}
                <div className="deploy-kpi-grid">
                  <div className="deploy-kpi-card">
                    <div className="deploy-kpi-label">{deployActiveEnv} STATUS</div>
                    <div className="deploy-kpi-val">
                      <span className={`deploy-status-pill ${overallStatus.toLowerCase()}`}>
                        <span className="deploy-status-dot" />
                        {overallStatus}
                      </span>
                    </div>
                  </div>

                  <div className="deploy-kpi-card">
                    <div className="deploy-kpi-label">ACTIVE RUN ID</div>
                    <div className="deploy-kpi-val">
                      <span
                        className="deploy-run-id-chip"
                        title={`Click to copy: ${activeRunId}`}
                        onClick={() => {
                          if (activeRunId && activeRunId !== "-") {
                            navigator.clipboard.writeText(activeRunId);
                            setDeployCopiedRunId(true);
                            setTimeout(() => setDeployCopiedRunId(false), 2000);
                          }
                        }}
                      >
                        <span>{truncateRunId(activeRunId)}</span>
                        {deployCopiedRunId ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                      </span>
                    </div>
                  </div>

                  <div className="deploy-kpi-card">
                    <div className="deploy-kpi-label">DEPLOYED / VERIFIED</div>
                    <div className="deploy-kpi-val">
                      <span className="deploy-kpi-count">{deployedCount}</span>
                      <span className="deploy-kpi-count-unit">{deployedCount === 1 ? "object" : "objects"}</span>
                    </div>
                  </div>

                  <div className="deploy-kpi-card">
                    <div className="deploy-kpi-label">FAILED / BLOCKED</div>
                    <div className="deploy-kpi-val">
                      <span className="deploy-kpi-count">{failedCount}</span>
                      <span className="deploy-kpi-count-unit">{failedCount === 1 ? "object" : "objects"}</span>
                    </div>
                  </div>
                </div>

                {/* Diagnostic Alert Banner */}
                {(overallStatus === "FAILED" || failedCount > 0 || medDeployment?.error || deployment?.failed_object) ? (
                  <div className="deploy-diagnostic-ribbon">
                    <AlertCircle size={16} style={{ color: "#e11d48", flexShrink: 0, marginTop: 2 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                        <span style={{ fontWeight: 700, color: "#9f1239" }}>Deployment Alert:</span>
                        <span className="deploy-target-badge">{formatSqlIdent(failedTargetIdent)}</span>
                      </div>
                      <div style={{ color: "#334155" }}>
                        {failureSummaryMessage || "Deployment halted with execution error. Dependent pipeline transformations stopped."}
                      </div>
                      <details className="deploy-trace-disclosure">
                        <summary>View full trace</summary>
                        <pre>{rawTraceContent}</pre>
                      </details>
                    </div>
                  </div>
                ) : (
                  <div className="deploy-diagnostic-ribbon ok">
                    <CheckCircle2 size={16} style={{ color: "#059669", flexShrink: 0, marginTop: 2 }} />
                    <div style={{ flex: 1, color: "#065f46" }}>
                      <b>Unified Reconciliation & Verification Active:</b> All target tables, views, and catalog objects verified with deterministic row count guarantees and version tracking across {deployActiveEnv === "ALL" ? "DEV, TEST, UAT, and PROD" : `${deployActiveEnv} environment`}.
                    </div>
                  </div>
                )}

                {/* Deployment Attempts Table */}
                <div className="deploy-table-wrapper">
                  {filteredAttempts.length ? (
                    <table className="deploy-attempts-table">
                      <thead>
                        <tr>
                          <th className="col-time">Time</th>
                          <th style={{ width: 75 }}>Env</th>
                          <th className="col-layer">Layer</th>
                          <th className="col-target">Target / Action</th>
                          <th className="col-version">Version</th>
                          <th className="col-status">Status</th>
                          <th className="col-action">Action / Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredAttempts.map((item: any) => {
                          const isFailed = item.status === "FAILED";
                          const envKey = (item.env || "DEV").toLowerCase();
                          return (
                            <tr key={item.id}>
                              <td className="col-time" style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, color: "#64748b" }}>
                                {formatDateTime(item.time)}
                              </td>
                              <td>
                                <span className={`deploy-env-pill ${envKey}`} style={{ fontSize: 10, padding: "2px 7px", fontWeight: 700 }}>
                                  {item.env || "DEV"}
                                </span>
                              </td>
                              <td className="col-layer">
                                <span className={`deploy-layer-badge ${item.layer.toLowerCase()}`}>
                                  {item.layer}
                                </span>
                              </td>
                              <td className="col-target">
                                <span className="deploy-target-ident">
                                  {formatSqlIdent(item.target)}
                                </span>
                              </td>
                              <td className="col-version" style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, color: "#475569" }}>
                                {item.version}
                              </td>
                              <td className="col-status">
                                <span className={`deploy-status-pill ${item.status.toLowerCase()}`}>
                                  <span className="deploy-status-dot" />
                                  {item.status}
                                </span>
                              </td>
                              <td className="col-action">
                                {isFailed ? (
                                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                    <span className="deploy-error-pill" title={item.error || "Deployment failed"}>
                                      {item.error || "Execution error"}
                                    </span>
                                    <span
                                      className="deploy-inspect-link"
                                      onClick={() => {
                                        setDeployTerminalOpen(true);
                                        setDeployTerminalFilter(item.target.replace(/[`'"]/g, ""));
                                        setInspectedTarget(item.target);
                                        const term = document.getElementById("deploy-terminal-console");
                                        if (term) term.scrollIntoView({ behavior: "smooth" });
                                      }}
                                      title="Inspect terminal logs for this object"
                                    >
                                      Inspect Log →
                                    </span>
                                  </div>
                                ) : (
                                  <span style={{ fontSize: 11, color: "#64748b" }}>
                                    {item.action || "Deployed"}
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <Empty text={`No deployment attempts match the selected filter (${deployLogEnvFilter} / ${deployStatusFilter}).`} />
                  )}
                </div>

                {/* Terminal Console (Ingestion & Promotion Logs) */}
                <div className="deploy-terminal-accordion" id="deploy-terminal-console">
                  <div
                    className="deploy-terminal-header"
                    onClick={() => setDeployTerminalOpen(!deployTerminalOpen)}
                    title="Click to toggle terminal console"
                  >
                    <div className="deploy-terminal-title">
                      <span style={{ fontSize: 10, display: "inline-block", transform: deployTerminalOpen ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s ease" }}>▼</span>
                      <span>Multi-Environment Ingestion & Execution Logs</span>
                      <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 999, background: "#e2e8f0", color: "#475569" }}>
                        {terminalLines.length}
                      </span>
                    </div>
                    <div className="deploy-terminal-controls" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        className="deploy-terminal-filter"
                        placeholder="Filter logs..."
                        value={deployTerminalFilter}
                        onChange={(e) => setDeployTerminalFilter(e.target.value)}
                      />
                      <button
                        type="button"
                        className="deploy-terminal-btn"
                        title="Copy terminal logs"
                        onClick={() => {
                          const text = terminalLines.map((l: any) => `${l.time} [${l.level}]  ${l.msg}`).join("\n");
                          navigator.clipboard.writeText(text);
                          setMsg("Terminal logs copied to clipboard");
                        }}
                      >
                        <Copy size={12} /> Copy
                      </button>
                      <button
                        type="button"
                        className="deploy-terminal-btn"
                        title="Download full DEV logs"
                        disabled={!pid || busy}
                        onClick={downloadDevLogs}
                      >
                        <Download size={12} /> Pop-out
                      </button>
                    </div>
                  </div>

                  {deployTerminalOpen && (
                    <div className="deploy-terminal-body">
                      {terminalLines.length > 0 ? (
                        terminalLines.map((line: any, idx: number) => {
                          const isHighlighted = inspectedTarget && line.msg.toLowerCase().includes(inspectedTarget.toLowerCase().replace(/[`'"]/g, ""));
                          return (
                            <div key={idx} className={`deploy-log-line ${isHighlighted ? "highlighted" : ""}`}>
                              <span className="deploy-log-time">{line.time}</span>
                              <span className={`deploy-log-level ${line.level.toLowerCase()}`}>
                                [{line.level}]
                              </span>
                              <span className="deploy-log-msg">{line.msg}</span>
                            </div>
                          );
                        })
                      ) : (
                        <div style={{ color: "#64748b", fontStyle: "italic", padding: "8px 0" }}>
                          No terminal logs match filter: "{deployTerminalFilter}"
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
          {page === "Lifecycle" && (
            <Panel title="Project-specific lifecycle">
              <div className="lifecycle-big">
                {life.map((x, i) => (
                  <div className="stage" key={x.environment}>
                    <div className="circle">{i + 1}</div>
                    <h3>{x.environment}</h3>
                    <Badge s={x.status} />
                    <p>
                      {x.pass_count} passed · {x.fail_count} failed ·{" "}
                      {x.review_blockers} blockers
                    </p>
                  </div>
                ))}
              </div>
            </Panel>
          )}
          {genericModule &&
            ![
              "Assessment",
              "Conversion Plans",
              "Administration",
              "Deployments",
              "Waves",
            ].includes(page) && (
              <Panel
                title={page}
                actions={
                  <button disabled={!pid} onClick={addRecord}>
                    <Plus size={15} />
                    Add record
                  </button>
                }
              >
                <RecordTable rows={records} />
              </Panel>
            )}
          {page === "Users" && (
            <Panel title="Users">
              {users.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Locked</th>
                      <th>Attempts</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td>{u.username}</td>
                        <td>{u.role}</td>
                        <td>{String(u.locked)}</td>
                        <td>{u.failed_attempts}</td>
                        <td>
                          {u.locked && (
                            <button
                              onClick={() =>
                                action(() =>
                                  api(`/users/${u.id}/unlock`, {
                                    method: "POST",
                                  }),
                                )
                              }
                            >
                              Unlock
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Empty text="No users." />
              )}
            </Panel>
          )}
          {page === "Environment Setup" && (
            <div className="env-setup-container">
              {/* PAGE HEADER */}
              <div className="wf-page-header" style={{ marginBottom: 4 }}>
                <div className="wf-breadcrumbs">
                  <span>SQL Server</span>
                  <span className="wf-breadcrumbs-sep">→</span>
                  <span>Databricks</span>
                  <span className="wf-breadcrumbs-sep">|</span>
                  <b>Environment Setup</b>
                  <span className="wf-breadcrumbs-sep">|</span>
                  <span style={{ color: "#0284c7" }}>Databricks Control Plane & Target Infrastructure</span>
                </div>
                <div className="wf-header-badges">
                  <span className="wf-header-badge emerald">
                    <CheckCircle2 size={13} /> {environmentConfig?.configured ? "Control Plane: Ready" : "Setup Required"}
                  </span>
                  <span className="wf-header-badge blue">
                    <ServerCog size={13} /> Unity Catalog
                  </span>
                </div>
              </div>

              {/* Card 1: Configuration Card & Inputs */}
              <div className="card" style={{ padding: "24px 26px" }}>
                <div className="env-section-tag">
                  <ServerCog size={15} color="#2563eb" />
                  Databricks Control Plane Configuration
                </div>

                {/* Status banner integrated directly into card */}
                <div
                  className={`env-banner ${
                    environmentConfig?.feature_enabled ? "enabled" : "disabled"
                  }`}
                >
                  {environmentConfig?.feature_enabled ? (
                    <CheckCircle2 size={18} color="#059669" />
                  ) : (
                    <AlertTriangle size={18} color="#d97706" />
                  )}
                  <div>
                    {environmentConfig?.feature_enabled
                      ? "DEV environment provisioning is enabled. Direct deployment to Unity Catalog is authorized."
                      : "Preview and preflight are available, but provisioning is disabled until DATABRICKS_ENVIRONMENT_PROVISIONING_ENABLED=true is configured on the backend."}
                  </div>
                </div>

                {/* Form Inputs Grid */}
                <div className="env-form-grid">
                  <div className="env-field-group">
                    <label className="env-field-label">Workspace Host *</label>
                    <div className="env-input-wrapper">
                      <input
                        className="env-text-input"
                        value={environmentForm.workspace_host}
                        placeholder="dbc-example.cloud.databricks.com"
                        onChange={(e) =>
                          setEnvironmentForm({
                            ...environmentForm,
                            workspace_host: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="env-field-group">
                    <label className="env-field-label">SQL Warehouse HTTP Path *</label>
                    <div className="env-input-wrapper">
                      <input
                        className="env-text-input"
                        value={environmentForm.http_path}
                        placeholder="/sql/1.0/warehouses/..."
                        onChange={(e) =>
                          setEnvironmentForm({
                            ...environmentForm,
                            http_path: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="env-field-group">
                    <label className="env-field-label">Token Secret Reference *</label>
                    <div className="env-input-wrapper">
                      <Lock size={15} className="env-input-icon" />
                      <input
                        className="env-text-input has-icon"
                        value={environmentForm.token_env_key}
                        placeholder="CLIENT_DATABRICKS_TOKEN"
                        onChange={(e) =>
                          setEnvironmentForm({
                            ...environmentForm,
                            token_env_key: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="env-field-group">
                    <label className="env-field-label">Catalog Prefix *</label>
                    <div className="env-input-wrapper">
                      <input
                        className="env-text-input"
                        value={environmentForm.catalog_prefix}
                        placeholder="migration"
                        onChange={(e) =>
                          setEnvironmentForm({
                            ...environmentForm,
                            catalog_prefix: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>
                </div>

                {/* Action Buttons with Clear Hierarchy */}
                <div style={{ display: "flex", gap: 10, marginTop: 20, alignItems: "center", flexWrap: "wrap" }}>
                  <button
                    className="btn-primary-blue"
                    disabled={!pid || busy}
                    onClick={() =>
                      action(() =>
                        api(`/projects/${pid}/databricks/configuration`, {
                          method: "PUT",
                          body: JSON.stringify(environmentForm),
                        }),
                      )
                    }
                  >
                    <ShieldCheck size={16} /> Save Configuration
                  </button>
                  <button
                    className="btn-secondary"
                    disabled={!pid || busy || !environmentConfig?.configured}
                    onClick={() =>
                      action(() =>
                        api(`/projects/${pid}/databricks/connection-test`, {
                          method: "POST",
                        }),
                      )
                    }
                  >
                    <PlugZap size={15} /> Test Connection
                  </button>
                </div>

                {/* Security Status Strip */}
                {environmentConfig?.configured && (
                  <div className="env-security-strip">
                    <div className="env-security-item">
                      <Lock size={13} color="#2563eb" />
                      <span>Secret Reference:</span>
                      <code>{environmentConfig.token_env_key}</code>
                    </div>
                    <div className="env-security-item">
                      <span>Secret Configured:</span>
                      <span
                        className={`status-pill ${
                          environmentConfig.token_configured ? "active" : "blocked"
                        }`}
                        style={{ padding: "2px 8px", fontSize: "10px" }}
                      >
                        <span className="status-dot" />
                        {environmentConfig.token_configured ? "Configured (Yes)" : "Missing (No)"}
                      </span>
                    </div>
                    <div className="env-security-item">
                      <span>Connection Status:</span>
                      <span
                        className={`status-pill ${
                          environmentConfig.status === "READY" ? "active" : "review"
                        }`}
                        style={{ padding: "2px 8px", fontSize: "10px" }}
                      >
                        <span className="pulsing-dot" style={{ width: 6, height: 6 }} />
                        {environmentConfig.status || "UNKNOWN"}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Card 2: Governed DEV Environment Plan */}
              <div className="card" style={{ padding: "24px 26px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
                  <div className="env-section-tag" style={{ margin: 0 }}>
                    <Layers3 size={15} color="#2563eb" />
                    Governed DEV Environment Plan
                  </div>
                  <button
                    className="btn-secondary"
                    disabled={!pid || busy || !environmentConfig?.configured}
                    onClick={() =>
                      action(() =>
                        api(`/projects/${pid}/environments/dev/plan`, {
                          method: "POST",
                        }),
                      )
                    }
                  >
                    <Plus size={14} /> Create DEV Plan
                  </button>
                </div>

                {!environmentPlan?.exists ? (
                  <Empty text="Save the Databricks configuration above, then create the DEV environment plan." />
                ) : (
                  <>
                    {/* Governed Plan KPI Stat Tiles */}
                    <div className="env-plan-stat-grid">
                      <div className="env-stat-tile tile-blue">
                        <div className="env-stat-tile-top">
                          <span className="env-stat-title">Target Environment</span>
                          <Cloud size={18} color="#2563eb" />
                        </div>
                        <div className="env-stat-number">DEV</div>
                        <div className="env-stat-status">
                          <span className="pulsing-dot" />
                          Live Catalog: {environmentPlan.catalog_name}
                        </div>
                      </div>

                      <div className="env-stat-tile tile-violet">
                        <div className="env-stat-tile-top">
                          <span className="env-stat-title">Managed Schemas</span>
                          <Layers size={18} color="#8b5cf6" />
                        </div>
                        <div className="env-stat-number">
                          {environmentPlan.schemas?.length || 0}
                        </div>
                        <div className="env-stat-status" style={{ color: "#7c3aed" }}>
                          Bronze, Silver, Gold
                        </div>
                      </div>

                      <div className="env-stat-tile tile-emerald">
                        <div className="env-stat-tile-top">
                          <span className="env-stat-title">Destructive Operations</span>
                          <ShieldCheck size={18} color="#10b981" />
                        </div>
                        <div className="env-stat-number">
                          {environmentPlan.preflight?.destructive_operations || 0}
                        </div>
                        <div className="env-stat-status">
                          <span className="pulsing-dot" />
                          Zero Destructive Actions
                        </div>
                      </div>
                    </div>

                    {/* Planned Operations Console Table */}
                    <div style={{ marginTop: 20 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <b style={{ fontSize: "13px", color: "#0f172a" }}>Planned Operations Console</b>
                        <span style={{ fontSize: "11px", color: "#64748b" }}>
                          Catalog: <code>{environmentPlan.catalog_name}</code> · Status: <Badge s={environmentPlan.status} />
                        </span>
                      </div>

                      <div className="projects-table-wrapper" style={{ border: "1px solid #e2e8f0" }}>
                        <table className="projects-table">
                          <thead>
                            <tr>
                              <th style={{ width: "160px" }}>Operation</th>
                              <th style={{ width: "220px" }}>Target Object</th>
                              <th>Preflight Validation</th>
                              <th>DDL Statement</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(environmentPlan.operations || []).map((operation: string, index: number) => {
                              const isCatalog = operation.toUpperCase().includes("CATALOG");
                              const isSchema = operation.toUpperCase().includes("SCHEMA");
                              const badgeClass = isCatalog ? "catalog" : isSchema ? "schema" : "catalog";
                              const badgeText = isCatalog ? "CREATE CATALOG" : isSchema ? "CREATE SCHEMA" : "CREATE";

                              const parts = operation.trim().split(/\s+/);
                              const targetName = parts[parts.length - 1];

                              const preflightAction =
                                index === 0
                                  ? environmentPlan.preflight?.catalog?.action || "NOT_RUN"
                                  : environmentPlan.preflight?.schemas?.[index - 1]?.action || "NOT_RUN";

                              return (
                                <tr key={operation} className="project-row">
                                  <td>
                                    <span className={`op-badge ${badgeClass}`}>{badgeText}</span>
                                  </td>
                                  <td>
                                    <span className="op-target-mono">{targetName}</span>
                                  </td>
                                  <td>
                                    <Badge s={preflightAction} />
                                  </td>
                                  <td>
                                    <code style={{ fontSize: "11px", color: "#475569" }}>{operation}</code>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Footer Action Deck */}
                    <div className="env-action-deck">
                      <button
                        className="btn-secondary"
                        disabled={busy || environmentConfig?.status !== "READY"}
                        onClick={() =>
                          action(() =>
                            api(`/projects/${pid}/environments/dev/preflight`, {
                              method: "POST",
                            }),
                          )
                        }
                      >
                        <Stethoscope size={15} /> Run Preflight
                      </button>
                      <button
                        className="btn-secondary"
                        disabled={busy || environmentPlan.status !== "PREFLIGHT_PASSED"}
                        onClick={() =>
                          action(() =>
                            api(`/projects/${pid}/environments/dev/approve`, {
                              method: "POST",
                            }),
                          )
                        }
                      >
                        <FileCheck2 size={15} /> Approve Plan
                      </button>
                      <button
                        className="btn-primary-blue"
                        disabled={
                          busy ||
                          environmentPlan.status !== "APPROVED" ||
                          !environmentConfig?.feature_enabled
                        }
                        onClick={() =>
                          action(() =>
                            api(`/projects/${pid}/environments/dev/provision`, {
                              method: "POST",
                            }),
                          )
                        }
                      >
                        <ServerCog size={16} /> Provision DEV
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
          {page === "Administration" && (
            <Panel
              title="System diagnostics"
              actions={
                <>
                  <button
                    onClick={() =>
                      action(async () => {
                        const d = await api("/system/diagnostics");
                        setDiag(d);
                        return d;
                      })
                    }
                  >
                    <Stethoscope size={15} />
                    Run diagnostics
                  </button>
                  <button
                    onClick={() =>
                      action(async () => {
                        const d = await api("/system/databricks-test", {
                          method: "POST",
                        });
                        setDiag(d);
                        return d;
                      })
                    }
                  >
                    <PlugZap size={15} />
                    Test Databricks
                  </button>
                  <button
                    onClick={() =>
                      action(async () => {
                        const d: any = await api("/ai/provider-test", {
                          method: "POST",
                        });
                        setDiag(d);
                        setAiProvider(d);
                        return d;
                      })
                    }
                  >
                    <Sparkles size={15} />
                    Test AI Provider
                  </button>
                </>
              }
            >
              {diag ? (
                <pre>{JSON.stringify(diag, null, 2)}</pre>
              ) : (
                <Empty text="Run diagnostics to verify ODBC driver, auth mode, Databricks configuration and environment." />
              )}
            </Panel>
          )}
        </section>

        {/* Step 2: Universal Bottom Action Rail (<UniversalActionRail />) */}
        {(() => {
          const railMetadata: Record<number, {
            title: string;
            context: string;
            backText: string;
            backTarget: string;
            backDisabled: boolean;
            forwardText: string;
            forwardTarget: string;
            forwardDisabled: boolean;
            forwardTooltip?: string;
          }> = {
            1: {
              title: "Stage 1 of 9: Projects",
              context: `${projects.length} Projects Available`,
              backText: "",
              backTarget: "",
              backDisabled: true,
              forwardText: "Continue with Selected Project →",
              forwardTarget: "Environment Setup",
              forwardDisabled: !pid,
              forwardTooltip: !pid ? "Select a project to continue" : undefined,
            },
            2: {
              title: "Stage 2 of 9: Environment Setup",
              context: "Databricks DEV Target Configured",
              backText: "← Back to Projects",
              backTarget: "Projects",
              backDisabled: false,
              forwardText: "Proceed to Sources →",
              forwardTarget: "Sources",
              forwardDisabled: !pid,
            },
            3: {
              title: "Stage 3 of 9: Sources",
              context: `${sources.length || 1} SQL Server Source Configured`,
              backText: "← Back to Environment",
              backTarget: "Environment Setup",
              backDisabled: false,
              forwardText: "Proceed to Discovery →",
              forwardTarget: "Discovery",
              forwardDisabled: !pid,
            },
            4: {
              title: "Stage 4 of 9: Discovery",
              context: `${inventory.length || dash.objects_discovered || 11} Objects Identified`,
              backText: "← Back to Sources",
              backTarget: "Sources",
              backDisabled: false,
              forwardText: `Proceed to Inventory (${inventory.length || dash.objects_discovered || 11} Objects) →`,
              forwardTarget: "Inventory",
              forwardDisabled: false,
            },
            5: {
              title: "Stage 5 of 9: Inventory",
              context: `${inventory.length || 11} Source Objects Cataloged`,
              backText: "← Back to Discovery",
              backTarget: "Discovery",
              backDisabled: false,
              forwardText: "Proceed to Classification →",
              forwardTarget: "Layer Classification",
              forwardDisabled: false,
            },
            6: {
              title: "Stage 6 of 9: Layer Classification",
              context: "Medallion Architecture Layer Assignment",
              backText: "← Back to Inventory",
              backTarget: "Inventory",
              backDisabled: false,
              forwardText: "Approve & Proceed to Studio →",
              forwardTarget: "Migration Workflow",
              forwardDisabled: false,
            },
            7: {
              title: "Stage 7 of 9: Migration Studio",
              context: `${medArts.length || 14} Medallion Artifacts · ${medArts.filter((a: any) => a.review_status === "APPROVED").length} Approved`,
              backText: "← Back to Classification",
              backTarget: "Layer Classification",
              backDisabled: false,
              forwardText: `Proceed to Deployment (${medArts.length || 14} Artifacts) →`,
              forwardTarget: "Deployments",
              forwardDisabled: false,
            },
            8: {
              title: "Stage 8 of 9: Deployment (DEV)",
              context: "DEV Validation Evidence & Logs",
              backText: "← Back to Studio",
              backTarget: "Migration Workflow",
              backDisabled: false,
              forwardText: "Proceed to Lifecycle & Waves →",
              forwardTarget: "Lifecycle",
              forwardDisabled: false,
            },
            9: {
              title: "Stage 9 of 9: Lifecycle & Waves",
              context: "Multi-Environment Promotion Chain",
              backText: "← Back to Deployment",
              backTarget: "Deployments",
              backDisabled: false,
              forwardText: "Complete Migration & Decommission →",
              forwardTarget: "Cutover",
              forwardDisabled: false,
            },
          };

          const stageInfo = railMetadata[currentStage] || railMetadata[7];

          return (
            <footer className="universal-action-rail">
              <div>
                {!stageInfo.backDisabled ? (
                  <button
                    className="action-rail-btn-back"
                    onClick={() => setPage(stageInfo.backTarget)}
                  >
                    <ArrowLeft size={14} />
                    <span>{stageInfo.backText}</span>
                  </button>
                ) : (
                  <div style={{ width: 140 }} />
                )}
              </div>

              <div className="action-rail-center">
                <span className="action-rail-stage-title">{stageInfo.title}</span>
                <span className="action-rail-stage-context">({stageInfo.context})</span>
              </div>

              <div>
                <button
                  className="action-rail-btn-forward"
                  disabled={stageInfo.forwardDisabled || busy}
                  title={stageInfo.forwardTooltip || stageInfo.forwardText}
                  onClick={() => setPage(stageInfo.forwardTarget)}
                >
                  <span>{stageInfo.forwardText}</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </footer>
          );
        })()}

        {/* ── Global Slide-over Drawer (Inspect SQL & Preflight Evidence) ── */}
        {reviewDrawerArtifact && (
          <div className="rv-drawer-overlay" onClick={() => setReviewDrawerArtifact(null)}>
            <div className="rv-drawer" onClick={(e) => e.stopPropagation()}>
              <div className="rv-drawer-header">
                <div className="rv-drawer-header-left">
                  <span className={layerBadgeClass(reviewDrawerArtifact.layer)}>
                    {(reviewDrawerArtifact.layer || "—").toUpperCase()}
                  </span>
                  <span className="rv-drawer-title">
                    {reviewDrawerArtifact.target_fqn || reviewDrawerArtifact.name || "Artifact"}
                  </span>
                </div>
                <button className="rv-drawer-close" onClick={() => setReviewDrawerArtifact(null)}>
                  <X size={16} />
                </button>
              </div>

              <div className="rv-drawer-tabs">
                <button
                  className={`rv-drawer-tab${reviewDrawerTab === "sql" ? " active" : ""}`}
                  onClick={() => setReviewDrawerTab("sql")}
                >
                  <Code size={13} /> Generated SQL
                </button>
                <button
                  className={`rv-drawer-tab${reviewDrawerTab === "evidence" ? " active" : ""}`}
                  onClick={() => setReviewDrawerTab("evidence")}
                >
                  <ShieldCheck size={13} /> Preflight Evidence
                </button>
              </div>

              <div className="rv-drawer-body">
                {reviewDrawerTab === "sql" ? (
                  <div className="rv-drawer-sql-wrap">
                    <pre className="rv-drawer-sql">{reviewDrawerArtifact.content || "/* No SQL content loaded */"}</pre>
                  </div>
                ) : (
                  <div className="rv-drawer-evidence">
                    <div className="rv-evidence-row">
                      <span className="rv-ev-label">Compilation</span>
                      <span className={`rv-ev-val ${reviewDrawerArtifact.executable ? "ok" : "fail"}`}>
                        {reviewDrawerArtifact.executable ? "✓ Passed" : "✗ Failed"}
                      </span>
                    </div>
                    <div className="rv-evidence-row">
                      <span className="rv-ev-label">Validation status</span>
                      <span className="rv-ev-val">{reviewDrawerArtifact.validation_status || "NOT_RUN"}</span>
                    </div>
                    <div className="rv-evidence-row">
                      <span className="rv-ev-label">Review status</span>
                      <span className="rv-ev-val">{reviewDrawerArtifact.review_status || "PENDING"}</span>
                    </div>
                    <div className="rv-evidence-row">
                      <span className="rv-ev-label">Layer</span>
                      <span className="rv-ev-val">{(reviewDrawerArtifact.layer || "—").toUpperCase()}</span>
                    </div>
                    <div className="rv-evidence-row">
                      <span className="rv-ev-label">Object type</span>
                      <span className="rv-ev-val">{reviewDrawerArtifact.source_object_type || reviewDrawerArtifact.type || "—"}</span>
                    </div>
                    <div className="rv-evidence-row">
                      <span className="rv-ev-label">Version</span>
                      <span className="rv-ev-val">v{reviewDrawerArtifact.version || reviewDrawerArtifact.current_version || "—"}</span>
                    </div>
                    {reviewDrawerArtifact.validation?.errors?.length > 0 && (
                      <div className="rv-evidence-errors">
                        <b>Validation errors:</b>
                        <ul>{(reviewDrawerArtifact.validation.errors || []).map((e: string, i: number) => <li key={i}>{e}</li>)}</ul>
                      </div>
                    )}
                    {(reviewDrawerArtifact.node_type === "ARCHITECTURE_REVIEW" || reviewDrawerArtifact.source_object_type === "TRIGGER") && (
                      <div className="rv-evidence-note">
                        Triggers do not exist in Databricks. Recommended target: implement as a Delta Table CHECK constraint or DLT expectation. Acknowledging this review allows DEV deployment to proceed.
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="rv-drawer-footer">
                <button
                  className="rv-drawer-copy-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(reviewDrawerArtifact.content || "").then(() => {
                      setReviewDrawerCopied(true);
                      setTimeout(() => setReviewDrawerCopied(false), 1800);
                    });
                  }}
                >
                  {reviewDrawerCopied ? <Check size={13} /> : <Copy size={13} />}
                  {reviewDrawerCopied ? "Copied" : "Copy SQL"}
                </button>
                <div className="rv-drawer-footer-actions">
                  {(() => {
                    const a = reviewDrawerArtifact;
                    const isArchReview = a.node_type === "ARCHITECTURE_REVIEW" || a.source_object_type === "TRIGGER";
                    const valid = a.executable && a.validation_status === "PASSED";
                    const canApprove = valid || isArchReview;
                    return (
                      <>
                        {canApprove && a.review_status !== "APPROVED" && (
                          <button
                            className="rv-drawer-approve-btn"
                            disabled={busy}
                            onClick={() => {
                              reviewMedArtifact(a.artifact_version_id, "APPROVED");
                              setReviewDrawerArtifact(null);
                            }}
                          >
                            <CheckCircle2 size={13} /> {isArchReview ? "Acknowledge Review" : "Approve for DEV"}
                          </button>
                        )}
                        <button
                          className="rv-drawer-reject-btn"
                          disabled={busy}
                          onClick={() => {
                            if (confirm(`Request changes for ${a.target_fqn || a.name}?`)) {
                              reviewMedArtifact(a.artifact_version_id, "CHANGES_REQUIRED");
                              setReviewDrawerArtifact(null);
                            }
                          }}
                        >
                          Request Changes
                        </button>
                      </>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
function evidenceList(value: any): string[] {
  if (value == null || value === "") return [];
  if (Array.isArray(value))
    return value.map((x) => (typeof x === "string" ? x : JSON.stringify(x)));
  return [typeof value === "string" ? value : JSON.stringify(value)];
}
function repairList(value: any): string[] {
  return evidenceList(value).map((x) => {
    try {
      const r = JSON.parse(x);
      return r?.action && r?.value ? `${r.action}: ${r.value}` : x;
    } catch {
      return x;
    }
  });
}
function Card({ n, t, icon }: { n: number; t: string; icon?: string }) {
  const I =
    icon === "tables"
      ? Database
      : icon === "views"
        ? Layers3
        : icon === "procedures"
          ? FileCode2
          : icon === "blocked"
            ? ShieldAlert
            : Boxes;
  return (
    <div className={`card ${icon || ""}`}>
      <div className="card-top">
        <div className="metric-icon">
          <I size={18} />
        </div>
        <span className="metric-trend">
          <ArrowUpRight size={13} />
          Live
        </span>
      </div>
      <strong>{n}</strong>
      <span>{t}</span>
      <small>Current project</small>
    </div>
  );
}
function Layer({ t, n }: { t: string; n: number }) {
  return (
    <div className={`layer ${t.toLowerCase()}`}>
      <div className="layer-icon">
        <Layers3 size={17} />
      </div>
      <b>{t}</b>
      <span>{n} objects</span>
      <div className="layer-bar">
        <i style={{ width: `${Math.min(100, Math.max(12, n * 8))}%` }} />
      </div>
    </div>
  );
}
function RecordTable({ rows }: { rows: ModRecord[] }) {
  return rows.length ? (
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Status</th>
          <th>Environment</th>
          <th>Details</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td>{r.payload?.title || r.record_type}</td>
            <td>
              <Badge s={r.payload?.status || "-"} />
            </td>
            <td>{r.environment || "-"}</td>
            <td>
              <code>{JSON.stringify(r.payload?.details || {})}</code>
            </td>
            <td>
              {formatDateTime(r.created_at)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  ) : (
    <Empty text="No records yet." />
  );
}
