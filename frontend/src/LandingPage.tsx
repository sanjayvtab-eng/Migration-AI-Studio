import { motion, type Variants } from "framer-motion";
import {
  ArrowRight,
  Database,
  Search,
  Sparkles,
  Layers,
  ShieldCheck,
  ShieldAlert,
  Server,
  KeyRound,
  FileCheck,
  Activity,
  GitBranch,
  Boxes,
  Lock,
  Workflow,
  CheckCircle2,
} from "lucide-react";

interface LandingPageProps {
  onLaunch: () => void;
}

export default function LandingPage({ onLaunch }: LandingPageProps) {
  // Motion animation variants for calm enterprise feel
  const fadeUp: Variants = {
    hidden: { opacity: 0, y: 24 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.55, ease: "easeOut" },
    },
  };

  const containerStagger: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  };

  const flowSteps = [
    {
      icon: Server,
      title: "1. Connect",
      desc: "Zero-trust outbound agent (migration-agent.exe) connects SQL Server without exposing cloud credentials.",
    },
    {
      icon: Search,
      title: "2. Discover",
      desc: "Automated schema extraction, primary/foreign key lineage, and data type compatibility analysis.",
    },
    {
      icon: Sparkles,
      title: "3. Ground",
      desc: "AI prompt engine grounds natural language requests deterministically into verified database objects.",
    },
    {
      icon: Layers,
      title: "4. Transform",
      desc: "Medallion architecture generation: Bronze raw delta tables, Silver SCD2 MERGE, and Gold analytics views.",
    },
    {
      icon: ShieldCheck,
      title: "5. Promote",
      desc: "Governed deployment promotion across DEV → TEST → UAT → PROD with automated quality gates.",
    },
  ];

  const capabilities = [
    {
      icon: Database,
      title: "Automated Schema Cataloging",
      desc: "Instant cataloging of tables, columns, constraints, dependencies, and complex SQL Server data types.",
    },
    {
      icon: Sparkles,
      title: "Natural Language Prompt-to-SQL",
      desc: "Describe business requirements in plain English; studio generates verified, executable Databricks SQL.",
    },
    {
      icon: GitBranch,
      title: "Idempotent SCD Type 2 MERGE",
      desc: "Generates high-performance Delta MERGE statements with surrogate keys and active flag tracking.",
    },
    {
      icon: KeyRound,
      title: "Binary & RowVersion Transport",
      desc: "Hex-normalized, memory-safe data transport for SQL Server binary, image, and rowversion columns.",
    },
    {
      icon: Boxes,
      title: "Dynamic Multi-Domain Intelligence",
      desc: "Tested across diverse schemas: University Education, Payroll, Healthcare, Retail, and Hospitality.",
    },
    {
      icon: Lock,
      title: "Zero Credential Exposure",
      desc: "SQL Server passwords and connection strings never leave your machine; all communication is outbound HTTPS.",
    },
    {
      icon: FileCheck,
      title: "Deterministic Preflight Validation",
      desc: "Validates target Databricks catalogs, schemas, cluster runtimes, and permissions prior to deployment.",
    },
    {
      icon: Workflow,
      title: "Governed 4-Stage Promotion Pipeline",
      desc: "Audit-ready progression with confirmation gates, stage rollback controls, and deployment evidence logs.",
    },
    {
      icon: Activity,
      title: "Continuous Reconciliation & Drift",
      desc: "Verifies row counts, checksum hashes, and schema definitions between source and target Delta tables.",
    },
  ];

  const limitations = [
    "Spatial Types & Custom UDTs: GEOMETRY, GEOGRAPHY, and user-defined types require human review fallback.",
    "Encrypted Routines & CLR Assemblies: Encrypted stored procedures and compiled .NET CLR code require manual refactoring.",
    "Large Streaming Payloads: Individual transaction streaming results exceeding 3.5 MB require configured batch sizing.",
    "Production Cutover Synchronization: Live cutover requires a scheduled maintenance window for distributed replication lag.",
  ];

  const guidanceSteps = [
    {
      step: 1,
      title: "Create or Select a Migration Project",
      detail: "Launch the studio and initialize an enterprise project workspace for your target database.",
    },
    {
      step: 2,
      title: "Download & Run the Standalone Agent",
      detail: "Download 'migration-agent.exe' on your SQL Server machine and connect using Windows or SQL Authentication.",
    },
    {
      step: 3,
      title: "Run Schema Discovery & Ground Prompts",
      detail: "Discover all source tables and enter natural language prompts describing your target Medallion requirements.",
    },
    {
      step: 4,
      title: "Review & Validate Generated Artifacts",
      detail: "Inspect generated Bronze, Silver SCD2, and Gold SQL scripts with automated Databricks preflight checks.",
    },
    {
      step: 5,
      title: "Execute DEV Deployment & Promote",
      detail: "Deploy to DEV, review data reconciliation, and promote verified artifacts to TEST, UAT, and PROD.",
    },
  ];

  return (
    <div className="landing-root">
      {/* Top Navbar */}
      <header className="landing-navbar">
        <div className="landing-brand">
          <div className="landing-brandmark">MF</div>
          <div className="landing-brand-text">
            <span className="brand-title">Databricks Migration AI Studio</span>
            <span className="brand-subtitle">Intelligent Lakehouse Modernization</span>
          </div>
        </div>
        <div className="landing-nav-actions">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={onLaunch}
            className="landing-signin-btn"
          >
            Sign In to Studio
          </motion.button>
        </div>
      </header>

      {/* 1. Hero Section (Centered, ~90vh) */}
      <section className="landing-hero-section">
        <motion.div
          initial="hidden"
          animate="visible"
          variants={fadeUp}
          className="landing-hero-content"
        >
          {/* Pill Badge with pulsing dot */}
          <div className="landing-pill-badge">
            <span className="pulsing-dot" />
            <span>Next-Gen Migration Engine</span>
          </div>

          {/* Huge Headline (6xl–8xl feel) */}
          <h1 className="landing-headline">
            Migrate Legacy SQL Server to{" "}
            <span className="landing-gradient-text">Databricks Lakehouse</span>{" "}
            faster than ever.
          </h1>

          {/* One-Line Subtitle */}
          <p className="landing-subtitle">
            Deterministic metadata-first discovery, AI prompt grounding, and automated Medallion promotion with zero cloud credential exposure.
          </p>

          {/* Big Primary CTA */}
          <div className="landing-cta-wrapper">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onLaunch}
              className="landing-primary-btn"
            >
              <span>Launch Application</span>
              <ArrowRight size={20} />
            </motion.button>
          </div>
        </motion.div>
      </section>

      {/* 2. Architecture Flow (5 Icon Cards in a Row) */}
      <section className="landing-flow-section">
        <div className="landing-container">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            variants={fadeUp}
            className="landing-section-header"
          >
            <div className="landing-section-eyebrow">ARCHITECTURE & PIPELINE</div>
            <h2 className="landing-section-title">End-to-End Migration Flow</h2>
            <p className="landing-section-desc">
              From on-premises discovery to production lakehouse in five governed stages.
            </p>
          </motion.div>

          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            variants={containerStagger}
            className="landing-flow-grid"
          >
            {flowSteps.map((item, idx) => {
              const Icon = item.icon;
              return (
                <motion.div
                  key={idx}
                  variants={fadeUp}
                  className="landing-flow-card"
                >
                  <div className="flow-card-icon-wrap">
                    <Icon size={24} />
                  </div>
                  <h3 className="flow-card-title">{item.title}</h3>
                  <p className="flow-card-desc">{item.desc}</p>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </section>

      {/* 3. Achievements / Capabilities (3x3 Grid of simple clean cards) */}
      <section className="landing-capabilities-section">
        <div className="landing-container">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            variants={fadeUp}
            className="landing-section-header"
          >
            <div className="landing-section-eyebrow">AUTOMATED CAPABILITIES</div>
            <h2 className="landing-section-title">What the Studio Automates Today</h2>
            <p className="landing-section-desc">
              Production-tested capabilities eliminating weeks of repetitive manual migration tasks.
            </p>
          </motion.div>

          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            variants={containerStagger}
            className="landing-capabilities-grid"
          >
            {capabilities.map((item, idx) => {
              const Icon = item.icon;
              return (
                <motion.div
                  key={idx}
                  variants={fadeUp}
                  whileHover={{ y: -6 }}
                  transition={{ duration: 0.25 }}
                  className="landing-cap-card"
                >
                  <div className="cap-card-header">
                    <div className="cap-icon-box">
                      <Icon size={20} />
                    </div>
                    <h3 className="cap-card-title">{item.title}</h3>
                  </div>
                  <p className="cap-card-desc">{item.desc}</p>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </section>

      {/* 4. Current Limitations (Soft red-tinted band with shield icon) */}
      <section className="landing-limitations-section">
        <div className="landing-container">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            variants={fadeUp}
            className="landing-limitations-box"
          >
            <div className="limitations-header">
              <div className="limitations-icon">
                <ShieldAlert size={26} />
              </div>
              <div>
                <h3 className="limitations-title">Current Scope & Governed Boundaries</h3>
                <p className="limitations-subtitle">
                  We build trust through radical honesty. The following scenarios require human review or configured batch thresholds:
                </p>
              </div>
            </div>
            <ul className="limitations-list">
              {limitations.map((lim, idx) => (
                <li key={idx} className="limitations-item">
                  <span className="limitations-bullet" />
                  <span>{lim}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </section>

      {/* 5. User Guidance (Numbered Vertical Steps 1–5 + Dark Launch Button) */}
      <section className="landing-guidance-section">
        <div className="landing-container">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            variants={fadeUp}
            className="landing-section-header"
          >
            <div className="landing-section-eyebrow">GETTING STARTED</div>
            <h2 className="landing-section-title">How to Use the Application</h2>
            <p className="landing-section-desc">
              Follow these five simple steps to execute your first end-to-end database migration.
            </p>
          </motion.div>

          <div className="landing-steps-container">
            {guidanceSteps.map((s, idx) => (
              <motion.div
                key={idx}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-50px" }}
                variants={fadeUp}
                className="guidance-step-row"
              >
                <div className="step-number-badge">{s.step}</div>
                <div className="step-content">
                  <h4 className="step-title">{s.title}</h4>
                  <p className="step-detail">{s.detail}</p>
                </div>
              </motion.div>
            ))}
          </div>

          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-50px" }}
            variants={fadeUp}
            className="guidance-cta-wrap"
          >
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onLaunch}
              className="landing-dark-launch-btn"
            >
              <span>Launch Application</span>
              <ArrowRight size={18} />
            </motion.button>
          </motion.div>
        </div>
      </section>

      {/* 6. Footer (One Line: Brand © Year) */}
      <footer className="landing-footer">
        <p>Databricks Migration AI Studio © 2026. All rights reserved.</p>
      </footer>
    </div>
  );
}
