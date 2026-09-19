import { useState, useCallback, useEffect, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  NavLink,
  Routes,
  Route,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  LayoutDashboard,
  FolderKanban,
  ListTodo,
  ScanEye,
  Database,
  Activity,
  Settings as SettingsIcon,
  ChevronsUpDown,
  Search,
  LogOut,
  ChevronRight,
  Command,
  Menu,
  X,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { api, send, setToken, human } from "./api";
import type { User, Project } from "./types";
import { AppContext } from "./context";
import {
  Button,
  Input,
  Select,
  Modal,
  Skeleton,
  ErrorState,
  Toast,
  PageHeading,
} from "./components/ui";
import Overview from "./pages/Overview";
import Projects, { ProjectDetail } from "./pages/Projects";
import Tasks from "./pages/Tasks";
import TaskDetail from "./pages/TaskDetail";
import Queue from "./pages/Queue";
import Settings from "./pages/Settings";
const links = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  { path: "/projects", label: "Projects", icon: FolderKanban },
  { path: "/tasks", label: "Tasks", icon: ListTodo },
  { path: "/queue", label: "Annotation Queue", icon: ScanEye },
  { path: "/datasets", label: "Datasets", icon: Database },
  { path: "/monitoring", label: "Monitoring", icon: Activity },
];
export default function App() {
  const qc = useQueryClient(),
    [logged, setLogged] = useState(!!sessionStorage.getItem("argus-token")),
    [project, setProject] = useState(""),
    [toast, setToast] = useState(""),
    [searchOpen, setSearchOpen] = useState(false),
    [search, setSearch] = useState(""),
    [mobile, setMobile] = useState(false),
    location = useLocation(),
    navigate = useNavigate();
  const user = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    enabled: logged,
    retry: false,
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
    enabled: !!user.data,
  });
  const closeToast = useCallback(() => setToast(""), []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const logout = () => {
    setToken(null);
    setLogged(false);
    setProject("");
    qc.clear();
    navigate("/");
  };
  if (!logged)
    return (
      <Auth
        onLogin={() => {
          setLogged(true);
          qc.invalidateQueries();
        }}
      />
    );
  if (user.isPending)
    return (
      <div className="auth-loading">
        <Skeleton />
      </div>
    );
  if (user.error)
    return (
      <div className="auth-loading">
        <ErrorState error={user.error} retry={() => user.refetch()} />
        <Button onClick={logout}>Return to sign in</Button>
      </div>
    );
  const current =
    links.find((l) =>
      l.path === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(l.path),
    )?.label || "Settings";
  return (
    <AppContext.Provider
      value={{ user: user.data, project, setProject, notify: setToast, logout }}
    >
      <div className="app-shell">
        <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
          <Link className="brand" to="/">
            <span className="brand-symbol">Λ</span>
            <span>ARGUS</span>
            <span className="version">/ 01</span>
          </Link>
          <div className="workspace-label">
            <span className="workspace-avatar">A</span>
            <div>
              Argus workspace<small>Training data platform</small>
            </div>
            <ChevronsUpDown size={14} />
          </div>
          <div className="nav-caption">WORKSPACE</div>
          <nav>
            {links.map((l) => (
              <NavLink
                key={l.path}
                end={l.path === "/"}
                to={l.path}
                onClick={() => setMobile(false)}
              >
                <l.icon size={18} />
                <span>{l.label}</span>
                {["Datasets", "Monitoring"].includes(l.label) && (
                  <small>SOON</small>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-note">
              <span className="live-dot" />
              Human oversight, by design.
              <p>Build a more reliable feedback loop.</p>
            </div>
            <NavLink className="settings-link" to="/settings">
              <SettingsIcon size={17} />
              Settings
            </NavLink>
            <div className="profile">
              <span className="avatar">{user.data.full_name.slice(0, 1)}</span>
              <div>
                <strong>{user.data.full_name}</strong>
                <small>{human(user.data.role)}</small>
              </div>
              <button onClick={logout} title="Sign out" aria-label="Sign out">
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <div className="breadcrumbs">
              <button
                className="mobile-toggle"
                onClick={() => setMobile(!mobile)}
                aria-label="Toggle navigation"
              >
                {mobile ? <X size={19} /> : <Menu size={19} />}
              </button>
              <span>Workspace</span>
              <ChevronRight size={13} />
              <strong>{current}</strong>
              {location.pathname.split("/").length > 2 && (
                <>
                  <ChevronRight size={13} />
                  <code>{location.pathname.split("/")[2].slice(0, 8)}</code>
                </>
              )}
            </div>
            <div className="topbar-actions">
              <Select
                aria-label="Global project selector"
                value={project}
                onChange={(e) => setProject(e.target.value)}
              >
                <option value="">All projects</option>
                {projects.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
              <button
                className="command-button"
                onClick={() => setSearchOpen(true)}
                aria-label="Search workspace"
              >
                <Search size={15} />
                <span>Search</span>
                <kbd>
                  <Command size={10} /> K
                </kbd>
              </button>
            </div>
          </header>
          <main key={project}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/projects/:id" element={<ProjectDetail />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/tasks/:id" element={<TaskDetail />} />
              <Route path="/queue" element={<Queue />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/datasets" element={<Future type="datasets" />} />
              <Route
                path="/monitoring"
                element={<Future type="monitoring" />}
              />
              <Route
                path="*"
                element={
                  <div className="empty">
                    <h1>Page not found</h1>
                    <Link to="/">Return to overview</Link>
                  </div>
                }
              />
            </Routes>
          </main>
          <footer className="app-footer">
            <span>
              ARGUS <span> / </span> Human-in-the-loop infrastructure
            </span>
            <span>
              <span className="live-dot" />
              Phase 01 · Core platform
            </span>
          </footer>
        </div>
        {toast && <Toast message={toast} onClose={closeToast} />}{" "}
        {searchOpen && (
          <Modal title="Search workspace" onClose={() => setSearchOpen(false)}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                navigate("/tasks");
                setSearchOpen(false);
              }}
            >
              <Input
                autoFocus
                placeholder="Find a page or project…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </form>
            <div className="command-results">
              {[
                ...links.map((l) => ({ name: l.label, path: l.path })),
                ...(projects.data || []).map((p) => ({
                  name: p.name,
                  path: `/projects/${p.id}`,
                })),
              ]
                .filter((l) =>
                  l.name.toLowerCase().includes(search.toLowerCase()),
                )
                .map((l) => (
                  <Link
                    key={l.path}
                    to={l.path}
                    onClick={() => setSearchOpen(false)}
                  >
                    {l.name}
                    <ArrowUpRight size={14} />
                  </Link>
                ))}
            </div>
          </Modal>
        )}
      </div>
    </AppContext.Provider>
  );
}
function Auth({ onLogin }: { onLogin: () => void }) {
  const [register, setRegister] = useState(false),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [name, setName] = useState(""),
    [org, setOrg] = useState(""),
    [error, setError] = useState<Error | null>(null),
    [pending, setPending] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const r = await send<{ access_token: string }>(
        register ? "/auth/register" : "/auth/login",
        {
          email,
          password,
          ...(register ? { full_name: name, organization_name: org } : {}),
        },
      );
      setToken(r.access_token);
      onLogin();
    } catch (e) {
      setError(e as Error);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="auth-page">
      <div className="auth-story">
        <Link to="/" className="brand">
          <span className="brand-symbol">Λ</span>ARGUS
        </Link>
        <div>
          <div className="eyebrow">HUMAN JUDGMENT. BETTER AGENTS.</div>
          <h1>
            Close the loop
            <br />
            on agent quality.
          </h1>
          <p>
            From the first trajectory to trusted training data.
            <br />
            One workspace for every human decision.
          </p>
          <div className="auth-flow">
            <span>Observe</span>
            <ChevronRight />
            <span>Annotate</span>
            <ChevronRight />
            <span>Approve</span>
          </div>
        </div>
        <small>
          <ShieldCheck size={16} />
          Human oversight built into every step.
        </small>
      </div>
      <div className="auth-form">
        <div className="eyebrow">WELCOME TO ARGUS</div>
        <h2>
          {register ? "Create your workspace" : "Sign in to your workspace"}
        </h2>
        <p>
          {register
            ? "Start your human feedback loop."
            : "Your next improvement starts with a closer look."}
        </p>
        <form onSubmit={submit}>
          {register && (
            <>
              <label>
                Full name
                <Input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                />
              </label>
              <label>
                Organization name
                <Input
                  required
                  value={org}
                  onChange={(e) => setOrg(e.target.value)}
                />
              </label>
            </>
          )}
          <label>
            Email address
            <Input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </label>
          <label>
            Password
            <Input
              type="password"
              required
              minLength={register ? 12 : undefined}
              autoComplete={register ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <ErrorState error={error} />}
          <Button disabled={pending}>
            {pending
              ? "Please wait…"
              : register
                ? "Create workspace"
                : "Sign in"}
            <ArrowUpRight size={16} />
          </Button>
        </form>
        <button
          className="auth-switch"
          onClick={() => {
            setRegister(!register);
            setError(null);
          }}
        >
          {register
            ? "Already have an account? Sign in"
            : "New here? Create a workspace"}
        </button>
        <p className="auth-fine">
          Secure access · Role-based permissions · Full provenance
        </p>
      </div>
    </div>
  );
}
function Future({ type }: { type: "datasets" | "monitoring" }) {
  const dataset = type === "datasets";
  const Icon = dataset ? Database : Activity;
  return (
    <>
      <PageHeading
        eyebrow="ON THE ROADMAP"
        title={dataset ? "Training datasets" : "Platform monitoring"}
        description={
          dataset
            ? "A trusted foundation for your next training run."
            : "A clearer view into the systems behind your feedback loop."
        }
      />
      <section className="future panel">
        <div className="future-icon">
          <Icon size={36} />
        </div>
        <span className="eyebrow">COMING IN A FUTURE PHASE</span>
        <h2>
          {dataset
            ? "From reviewed examples to reproducible datasets."
            : "Observe the whole feedback loop."}
        </h2>
        <p>
          {dataset
            ? "Dataset versioning and RL-ready exports will bring approved examples together with their complete provenance."
            : "Queue metrics, service telemetry, and quality signals will come together with Prometheus and Grafana integrations."}
        </p>
        <div className="future-features">
          {(dataset
            ? ["Versioned snapshots", "RL-ready exports", "Review provenance"]
            : ["Service metrics", "Queue observability", "Quality signals"]
          ).map((t) => (
            <span key={t}>
              <ShieldCheck size={15} />
              {t}
            </span>
          ))}
        </div>
        <Link to={dataset ? "/tasks" : "/"} className="button secondary">
          {dataset ? "Explore your tasks" : "View live operations"}
          <ArrowUpRight size={15} />
        </Link>
      </section>
    </>
  );
}
