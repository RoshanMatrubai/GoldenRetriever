import { motion } from "motion/react";
import { Shield, Activity, Lock, ArrowRight } from "lucide-react";

// ─── Motion presets ───────────────────────────────────────────────────────────

const EXPO = [0.16, 1, 0.3, 1] as const;

const blurUp = {
  hidden: { opacity: 0, y: 18, filter: "blur(6px)" },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.65, delay: i * 0.09, ease: EXPO },
  }),
};

const stagger = (delay = 0, gap = 0.09) => ({
  hidden: {},
  show: { transition: { staggerChildren: gap, delayChildren: delay } },
});

// ─── Content ──────────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Shield,
    title: "Cryptographic scope",
    desc: "Every token carries a signed allow-list. An agent with read access cannot purchase — not by policy, by math.",
  },
  {
    icon: Activity,
    title: "Full audit trail",
    desc: "Every grant, denial, and revocation is logged. Scope, agent, timestamp — provable accountability.",
  },
  {
    icon: Lock,
    title: "Instant revocation",
    desc: "Kill any live token mid-session. Agent's next call returns 410 Gone. No grace period.",
  },
];

const STEPS = [
  { label: "Agent requests access", desc: "Calls request_access(service, task). No raw credentials, ever." },
  { label: "Scope derived", desc: "Policy engine computes the minimum permission set the task requires." },
  { label: "Admin approves", desc: "Dashboard shows the derived scope. One click to approve or deny." },
  { label: "Token auto-expires", desc: "Ed25519-signed JWT. Expires at session end. Never renewable." },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function OverviewScreen({ onNavigate }: {
  onNavigate: (s: string) => void;
}) {
  return (
    <div className="min-h-full bg-background">
      <div className="max-w-2xl mx-auto px-10 py-20">

        {/* ── Hero ───────────────────────────────────────────────────── */}
        <motion.div
          initial="hidden"
          animate="show"
          variants={stagger(0.05)}
          className="mb-16"
        >
          <motion.p
            custom={0}
            variants={blurUp}
            className="text-[11px] text-muted-foreground uppercase tracking-[2px] mb-8 font-['DM_Mono',monospace]"
          >
            Doberman · Zero-Trust Access Broker
          </motion.p>

          <motion.h1
            custom={1}
            variants={blurUp}
            className="text-[52px] font-bold tracking-[-2px] text-foreground font-['Outfit',sans-serif] leading-[1.07] mb-6"
          >
            Your AI agents,<br />
            with guardrails.
          </motion.h1>

          <motion.p
            custom={2}
            variants={blurUp}
            className="text-[15.5px] text-muted-foreground leading-[1.78] max-w-[460px] mb-10"
          >
            A scoped access broker between your agents and the services they
            use. Every action is cryptographically approved, session-bound, and
            instantly revocable.
          </motion.p>

          <motion.div custom={3} variants={blurUp}>
            <button
              onClick={() => onNavigate("requests")}
              className="inline-flex items-center gap-2 text-[13.5px] font-medium text-foreground hover:text-muted-foreground transition-colors duration-200 group"
            >
              Open Dashboard
              <motion.span
                animate={{ x: 0 }}
                whileHover={{ x: 3 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
              >
                <ArrowRight size={14} />
              </motion.span>
            </button>
          </motion.div>
        </motion.div>

        {/* ── Animated rule ──────────────────────────────────────────── */}
        <div className="relative mb-16 overflow-hidden">
          <motion.div
            className="h-px bg-border"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            style={{ originX: 0 }}
            transition={{ duration: 0.9, delay: 0.55, ease: EXPO }}
          />
        </div>

        {/* ── Feature cards ──────────────────────────────────────────── */}
        <motion.div
          initial="hidden"
          animate="show"
          variants={stagger(0.6)}
          className="grid grid-cols-3 gap-4 mb-16"
        >
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              custom={i}
              variants={blurUp}
              whileHover={{
                y: -5,
                boxShadow: "0 16px 36px rgba(0,0,0,0.07)",
                transition: { type: "spring", stiffness: 380, damping: 22 },
              }}
              className="border border-border rounded-xl p-5 bg-card cursor-default"
            >
              <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center mb-4">
                <f.icon size={15} className="text-foreground" />
              </div>
              <h3 className="text-[13px] font-semibold text-foreground mb-1.5 font-['Outfit',sans-serif] tracking-tight">
                {f.title}
              </h3>
              <p className="text-[12px] text-muted-foreground leading-[1.65]">
                {f.desc}
              </p>
            </motion.div>
          ))}
        </motion.div>

        {/* ── How it works ───────────────────────────────────────────── */}
        <motion.div
          initial="hidden"
          animate="show"
          variants={stagger(0.88, 0.08)}
        >
          <motion.p
            custom={0}
            variants={blurUp}
            className="text-[11px] text-muted-foreground uppercase tracking-[2px] mb-6 font-['DM_Mono',monospace]"
          >
            How it works
          </motion.p>

          {STEPS.map((step, i) => (
            <motion.div
              key={step.label}
              custom={i}
              variants={blurUp}
              className="flex gap-5 py-4 border-b border-border last:border-0"
            >
              <span className="text-[11px] text-muted-foreground font-['DM_Mono',monospace] shrink-0 mt-[3px] w-5 select-none">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <div className="text-[13.5px] font-medium text-foreground mb-0.5 font-['Outfit',sans-serif]">
                  {step.label}
                </div>
                <div className="text-[12.5px] text-muted-foreground leading-[1.6]">
                  {step.desc}
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>

      </div>
    </div>
  );
}
