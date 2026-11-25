// Scripted replay of the four lifecycle paths of runbook section 7 item 3 on a LOCAL validator:
//   unsampled  : create, accept, commit, draw (not sampled), release
//   pass       : create, accept, commit, draw (sampled), verdict commit, verdict reveal = pass, release
//   dispute    : ... verdict = fail, escalate, second verifier commit, reveal = fail, slash
//   timeout    : create, accept, (execution deadline passes), timeout_refund
// Paths are interleaved (shuffled order in each round). For every transaction it records the
// signature, signature count, compute units, fee and time to "confirmed". Setup transactions
// (config updates that force p = 0 or 1 for the next job, bonds, token accounts) are not counted.
//
//   npx ts-node scripts/replay.ts --n 100 [--url http://127.0.0.1:8899] [--run-id ID] [--admin KEYPAIR]
//
// Only a local validator is accepted; Devnet runs are a separate step (runbook section 7 item 3)
// and Mainnet is never used.
import { Connection, Keypair, PublicKey } from "@solana/web3.js";
import { createHash } from "crypto";
import { execSync } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { ConfigParams, Escrow, PROGRAM_ID, TxRecord, stateName } from "../client/escrow";

type PathName = "unsampled" | "pass" | "dispute" | "timeout";
const PATHS: PathName[] = ["unsampled", "pass", "dispute", "timeout"];

function arg(name: string, def?: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : def;
}

const URL = arg("url", "http://127.0.0.1:8899")!;
const N = Number(arg("n", "100"));
const SEED = Number(arg("seed", "1"));
const host = new globalThis.URL(URL).hostname;
if (!["127.0.0.1", "localhost", "0.0.0.0"].includes(host)) {
  console.error(`refusing ${URL}: this replay runs on a local validator only`);
  process.exit(2);
}

const REPO = path.resolve(__dirname, "../../..");
const P = 1_000_000;
const FEE = 100_000;
const B = 500_000;

function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

function sh(cmd: string): string {
  try {
    return execSync(cmd, { cwd: REPO, stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "unknown";
  }
}

function today() {
  return new Date().toISOString().slice(0, 10).replace(/-/g, "");
}

function runId(): string {
  const given = arg("run-id");
  if (given) return given;
  const stem = `${today()}-wp5-escrow-replay-local`;
  for (let n = 1; ; n++) {
    const id = `${stem}-${String(n).padStart(2, "0")}`;
    if (!fs.existsSync(path.join(REPO, "experiments/runs", id))) return id;
  }
}

function stats(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b);
  const q = (p: number) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  const mean = s.reduce((a, b) => a + b, 0) / s.length;
  return { n: s.length, mean: +mean.toFixed(2), min: s[0], median: q(0.5), p95: q(0.95), max: s[s.length - 1] };
}

async function main() {
  const rid = runId();
  const dir = path.join(REPO, "experiments/runs", rid);
  fs.mkdirSync(path.join(dir, "logs"), { recursive: true });
  const start = new Date().toISOString();
  const git = { commit: sh("git rev-parse HEAD"), dirty: sh("git status --porcelain -- code/program") !== "" };

  const conn = new Connection(URL, "confirmed");
  // admin: a local dev keypair (default ~/.config/solana/id.json), so reruns on one validator can update Config
  const adminFile = arg("admin", path.join(os.homedir(), ".config/solana/id.json"))!;
  const admin = Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(adminFile, "utf8"))));
  const esc = new Escrow(conn, admin);
  await esc.airdrop(admin.publicKey, 100);
  const [requester, prov, v1, v2, orch] = [0, 1, 2, 3, 4].map(() => Keypair.generate());
  for (const k of [requester, prov, v1, v2, orch]) await esc.airdrop(k.publicKey, 100);

  const base: ConfigParams = {
    orchestrator: orch.publicKey,
    sampleProb: 0,
    drawDelay: Number(arg("delay", "2")),
    execTimeout: 60,
    disputeTimeout: 200,
    verifiers: [v1.publicKey, v2.publicKey],
  };
  await esc.init(base);
  if (!esc.mint.equals((await esc.config()).mint)) throw new Error("config mint mismatch");
  await esc.fundTokens(requester.publicKey, 10_000_000_000);
  await esc.fundTokens(prov.publicKey, 10_000_000_000);
  for (const k of [v1, v2]) await esc.fundTokens(k.publicKey, 0);
  await esc.openBond(prov);
  await esc.depositBond(prov, 5_000_000_000);

  const h32 = (s: string) => createHash("sha256").update(s).digest();
  let nextId = 1;
  const out = fs.createWriteStream(path.join(dir, "txs.jsonl"));
  const perJob: { path: PathName; job_id: number; recs: TxRecord[]; final_state: string; ok: boolean }[] = [];

  async function runPath(p: PathName) {
    // force the draw outcome for the next job (p snapshotted at create_job); not counted
    await esc.updateConfig({ ...base, sampleProb: p === "unsampled" ? 0 : 1, execTimeout: p === "timeout" ? 2 : 60 });
    const id = nextId++;
    const n0 = esc.records.length;
    await esc.createJob(requester, id, P, FEE, B);
    await esc.acceptJob(prov, id);
    if (p === "timeout") {
      const j = await esc.job(id);
      await esc.waitSlotAfter(j.execDeadline.toNumber());
      await esc.settle("timeoutRefund", orch, id);
    } else {
      await esc.commitResult(prov, id, h32(`root${id}`), h32(`out${id}`));
      await esc.drawSample(orch, id);
      if (p !== "unsampled") {
        await esc.submitVerdict(v1, id, { commit: h32(`c1-${id}`) });
        await esc.submitVerdict(v1, id, { reveal: p === "pass" ? "pass" : "fail" });
      }
      if (p === "dispute") {
        await esc.escalate(prov, id);
        await esc.finalVerdict(v2, id, { commit: h32(`c2-${id}`) });
        await esc.finalVerdict(v2, id, { reveal: "fail" });
        await esc.settle("slash", orch, id);
      } else {
        await esc.settle("release", orch, id);
      }
    }
    const recs = esc.records.slice(n0);
    const j = await esc.job(id);
    const want = { unsampled: "closedPaid", pass: "closedPaid", dispute: "closedRefunded", timeout: "closedRefunded" }[p];
    const st = stateName(j.state);
    const ok = st === want && j.settled && j.sampled === (p === "pass" || p === "dispute");
    perJob.push({ path: p, job_id: id, recs, final_state: st, ok });
    for (const r of recs) out.write(JSON.stringify({ path: p, job_id: id, ...r }) + "\n");
  }

  const rand = rng(SEED);
  for (let round = 0; round < N; round++) {
    const order = [...PATHS].sort(() => rand() - 0.5);
    for (const p of order) await runPath(p);
    if ((round + 1) % 10 === 0 || round === N - 1) console.log(`round ${round + 1}/${N}`);
  }
  out.end();

  const summary: any = { cluster: "localnet", paths: {} };
  for (const p of PATHS) {
    const jobs = perJob.filter((j) => j.path === p);
    const ixs: Record<string, number[]> = {};
    for (const j of jobs) for (const r of j.recs) (ixs[r.name] ??= []).push(r.cu ?? NaN);
    summary.paths[p] = {
      n_jobs: jobs.length,
      n_ok: jobs.filter((j) => j.ok).length,
      instructions: [...new Set(jobs[0]?.recs.map((r) => r.name))],
      tx_per_job: stats(jobs.map((j) => j.recs.length)),
      signatures_per_job: stats(jobs.map((j) => j.recs.reduce((a, r) => a + r.nsig, 0))),
      compute_units_per_job: stats(jobs.map((j) => j.recs.reduce((a, r) => a + (r.cu ?? 0), 0))),
      fee_lamports_per_job: stats(jobs.map((j) => j.recs.reduce((a, r) => a + (r.fee ?? 0), 0))),
      ms_to_confirmed_per_job_local: stats(jobs.map((j) => j.recs.reduce((a, r) => a + r.ms_confirmed, 0))),
      compute_units_by_instruction: Object.fromEntries(Object.entries(ixs).map(([k, v]) => [k, stats(v)])),
    };
  }
  fs.writeFileSync(path.join(dir, "summary.json"), JSON.stringify(summary, null, 1) + "\n");

  const so = path.resolve(__dirname, "../target/deploy/trajescrow.so");
  const version = await conn.getVersion();
  const manifest = {
    run_id: rid,
    wp: "wp5",
    purpose:
      "Scripted replay of the four escrow lifecycle paths (runbook section 7 item 3) on a local solana-test-validator. " +
      "Signature counts, compute units and fees are properties of the program and transactions; latencies on a local validator are not reported in the paper.",
    git_commit: git.commit,
    program_tree_dirty: git.dirty,
    cluster: "localnet (solana-test-validator)",
    rpc_endpoint: "local",
    solana_core: version["solana-core"],
    feature_set: version["feature-set"],
    program_id: PROGRAM_ID.toBase58(),
    program_so_sha256: fs.existsSync(so) ? createHash("sha256").update(fs.readFileSync(so)).digest("hex") : "unknown",
    anchor_cli: sh("anchor --version"),
    solana_cli: sh("solana --version"),
    node: process.version,
    os: `${os.platform()} ${os.release()}`,
    cpu_isa: os.arch(),
    cpu_model: os.cpus()[0]?.model ?? "unknown",
    params: { n_per_path: N, interleave_seed: SEED, payment: P, verifier_fee: FEE, bond: B, draw_delay_slots: base.drawDelay,
              exec_timeout_slots_timeout_path: 2, priority_fee: "none (no compute-budget instruction)" },
    start_time: start,
    end_time: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(dir, "manifest.json"), JSON.stringify(manifest, null, 1) + "\n");
  console.log(JSON.stringify(Object.fromEntries(PATHS.map((p) => [p, {
    ok: `${summary.paths[p].n_ok}/${summary.paths[p].n_jobs}`,
    sigs: summary.paths[p].signatures_per_job.median,
    cu: summary.paths[p].compute_units_per_job.median,
  }])), null, 1));
  console.log(`wrote ${dir}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
