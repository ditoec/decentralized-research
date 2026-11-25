// Transaction relay for the orchestrator (code/orchestrator/relay.py): reads one JSON request per
// line on stdin, sends the transaction with the named signer, and writes one JSON response per line
// on stdout: {"id", "ok", "rec"?: TxRecord, "job"?: {...}, "error"?: string}.
//
//   npx ts-node scripts/relay.ts --url http://127.0.0.1:8899 --keys keys.json
//
// keys.json maps signer names to keypair files: {"admin": "...", "orchestrator": "...", "<node>": "..."}.
// Mainnet URLs are refused.
import { Connection, Keypair, PublicKey } from "@solana/web3.js";
import * as fs from "fs";
import * as readline from "readline";
import { Escrow, stateName } from "../client/escrow";

const argv = process.argv;
const opt = (n: string, d?: string) => (argv.includes(`--${n}`) ? argv[argv.indexOf(`--${n}`) + 1] : d);
const url = opt("url", "http://127.0.0.1:8899")!;
if (/mainnet/i.test(url)) {
  console.error("mainnet is never used");
  process.exit(2);
}
const keyFiles: Record<string, string> = JSON.parse(fs.readFileSync(opt("keys")!, "utf8"));
const keys: Record<string, Keypair> = {};
for (const [name, file] of Object.entries(keyFiles))
  keys[name] = Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(file, "utf8"))));
const esc = new Escrow(new Connection(url, "confirmed"), keys.admin);
const hex = (s: string) => Buffer.from(s, "hex");
const pk = (s: string) => new PublicKey(s);
const signer = (n: string) => {
  if (!keys[n]) throw new Error(`unknown signer ${n}`);
  return keys[n];
};

function jobView(j: any) {
  return {
    job_id: j.jobId.toString(), state: stateName(j.state), requester: j.requester.toBase58(),
    provider: j.provider.toBase58(), payment: j.payment.toString(), verifier_fee: j.verifierFee.toString(),
    bond: j.bond.toString(), sample_ppm: j.samplePpm, commit_slot: j.commitSlot.toNumber(),
    exec_deadline: j.execDeadline.toNumber(), final_deadline: j.finalDeadline.toNumber(),
    draw_slot: j.drawSlot.toNumber(), draw_seed: Buffer.from(j.drawSeed).toString("hex"), sampled: j.sampled,
    verifier1: j.verifier1.toBase58(), v1_verdict: Object.keys(j.v1Verdict)[0], escalated: j.escalated,
    verifier2: j.verifier2.toBase58(), v2_verdict: Object.keys(j.v2Verdict)[0], slashed: j.slashed, settled: j.settled,
  };
}

async function handle(r: any): Promise<any> {
  const a = r.args ?? {};
  switch (r.op) {
    case "pubkeys":
      return { pubkeys: Object.fromEntries(Object.entries(keys).map(([n, k]) => [n, k.publicKey.toBase58()])) };
    case "init":
      await esc.init({ ...a, orchestrator: pk(a.orchestrator), verifiers: a.verifiers.map(pk) });
      return { mint: esc.mint.toBase58() };
    case "setup_node": {
      // local validator only: SOL, a token account, and for providers a funded bond
      const k = signer(a.node);
      await esc.airdrop(k.publicKey, a.sol ?? 10);
      await esc.fundTokens(k.publicKey, BigInt(a.tokens ?? 0));
      if (a.bond) {
        await esc.openBond(k);
        await esc.depositBond(k, a.bond);
      }
      return {};
    }
    case "slot":
      return { slot: await esc.slot() };
    case "get_job":
      return { job: jobView(await esc.job(a.job_id)) };
    case "create_job":
      return { rec: await esc.createJob(signer(r.signer), a.job_id, a.payment, a.verifier_fee, a.bond) };
    case "accept_job":
      return { rec: await esc.acceptJob(signer(r.signer), a.job_id) };
    case "commit_result":
      return { rec: await esc.commitResult(signer(r.signer), a.job_id, hex(a.merkle_root), hex(a.output_digest)) };
    case "draw_sample":
      return { rec: await esc.drawSample(signer(r.signer), a.job_id) };
    case "submit_verdict":
    case "final_verdict": {
      const m = a.commitment ? { commit: hex(a.commitment) } : { reveal: a.verdict };
      const f = r.op === "submit_verdict" ? esc.submitVerdict.bind(esc) : esc.finalVerdict.bind(esc);
      return { rec: await f(signer(r.signer), a.job_id, m as any) };
    }
    case "escalate":
      return { rec: await esc.escalate(signer(r.signer), a.job_id) };
    case "release":
    case "refund":
    case "slash":
    case "timeout_refund":
      return { rec: await esc.settle(r.op === "timeout_refund" ? "timeoutRefund" : r.op, signer(r.signer), a.job_id) };
    default:
      throw new Error(`unknown op ${r.op}`);
  }
}

async function main() {
  const rl = readline.createInterface({ input: process.stdin });
  for await (const line of rl) {
    if (!line.trim()) continue;
    let r: any = {};
    try {
      r = JSON.parse(line);
      const res = await handle(r);
      if (r.args?.job_id !== undefined && r.op !== "get_job" && res.rec) res.job = jobView(await esc.job(r.args.job_id));
      process.stdout.write(JSON.stringify({ id: r.id, ok: true, ...res }) + "\n");
    } catch (e: any) {
      process.stdout.write(JSON.stringify({ id: r.id, ok: false, error: String(e?.message ?? e), logs: e?.logs }) + "\n");
    }
  }
}

main();
