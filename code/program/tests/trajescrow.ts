// One test per row of the state-machine table in docs/07-runbook.md section 7 item 1,
// run on the local validator (`anchor test --skip-build`). Negative cases sit next to the
// transition they guard.
import * as anchor from "@anchor-lang/core";
import { BN } from "@anchor-lang/core";
import { Keypair, PublicKey } from "@solana/web3.js";
import { expect } from "chai";
import { createHash } from "crypto";
import { ConfigParams, Escrow, VerdictName, anchorError, pdas, stateName } from "../client/escrow";

const P = 1_000_000;
const FEE = 100_000;
const B = 500_000;

const provider = anchor.AnchorProvider.env();
const admin = (provider.wallet as anchor.Wallet).payer;
const esc = new Escrow(provider.connection, admin);
esc.measure = false;

const requester = Keypair.generate();
const prov = Keypair.generate();
const poorProv = Keypair.generate(); // opened bond, nothing deposited
const v1 = Keypair.generate();
const v2 = Keypair.generate();
const v3 = Keypair.generate();
const orch = Keypair.generate();
const stranger = Keypair.generate();
// a node that is both a provider and a registered verifier: it must never verify its own job
const dual = Keypair.generate();

let nextId = Date.now() % 1_000_000_000;
const newId = () => new BN(nextId++);
const h32 = (s: string) => createHash("sha256").update(s).digest();

const base: ConfigParams = {
  orchestrator: orch.publicKey,
  sampleProb: 0,
  drawDelay: 2,
  execTimeout: 40,
  disputeTimeout: 150,
  verifiers: [v1.publicKey, v2.publicKey, v3.publicKey, dual.publicKey],
};
const cfg = (o: Partial<ConfigParams> = {}) => esc.updateConfig({ ...base, ...o });

async function expectErr(p: Promise<any>, code: string) {
  try {
    await p;
  } catch (e) {
    expect(anchorError(e)).to.contain(code);
    return;
  }
  throw new Error(`expected ${code}`);
}

async function state(id: BN) {
  return stateName((await esc.job(id)).state);
}

/** Drives a fresh job to `upto` with sampling probability p. */
async function jobTo(upto: "funded" | "assigned" | "committed" | "drawn", p = 0, who = prov) {
  await cfg({ sampleProb: p });
  const id = newId();
  await esc.createJob(requester, id, P, FEE, B);
  if (upto === "funded") return id;
  await esc.acceptJob(who, id);
  if (upto === "assigned") return id;
  await esc.commitResult(who, id, h32(`root${id}`), h32(`out${id}`));
  if (upto === "committed") return id;
  await esc.drawSample(admin, id);
  return id;
}

async function verdict1(id: BN, v: VerdictName, who = v1) {
  await esc.submitVerdict(who, id, { commit: h32(`v1commit${id}`) });
  await esc.submitVerdict(who, id, { reveal: v });
}

async function verdict2(id: BN, v: VerdictName, who = v2) {
  await esc.finalVerdict(who, id, { commit: h32(`v2commit${id}`) });
  await esc.finalVerdict(who, id, { reveal: v });
}

const bal = (k: PublicKey) => esc.tokenBalance(esc.ata(k));

describe("trajescrow state machine (runbook section 7)", () => {
  before(async () => {
    for (const k of [requester, prov, poorProv, v1, v2, v3, orch, stranger, dual]) await esc.airdrop(k.publicKey);
    await esc.init(base);
    await esc.fundTokens(requester.publicKey, 1_000_000_000);
    for (const k of [prov, dual]) {
      await esc.fundTokens(k.publicKey, 50_000_000);
      await esc.openBond(k);
      await esc.depositBond(k, 20_000_000);
    }
    for (const k of [poorProv, v1, v2, v3, stranger]) await esc.fundTokens(k.publicKey, 0);
    await esc.openBond(poorProv);
  });

  it("— create_job → Funded: P + verifier fee locked in the vault", async () => {
    const before = await bal(requester.publicKey);
    const id = await jobTo("funded");
    expect(await state(id)).to.eq("funded");
    expect(await esc.tokenBalance(pdas.vault(pdas.job(id)))).to.eq(BigInt(P + FEE));
    expect(await bal(requester.publicKey)).to.eq(before - BigInt(P + FEE));
  });

  it("Funded → accept_job → Assigned: bond B locked", async () => {
    const id = await jobTo("funded");
    const b0 = await esc.bond(prov.publicKey);
    await expectErr(esc.acceptJob(poorProv, id), "InsufficientBond");
    await esc.acceptJob(prov, id);
    expect(await state(id)).to.eq("assigned");
    const b1 = await esc.bond(prov.publicKey);
    expect(b1.locked.sub(b0.locked).toNumber()).to.eq(B);
    await expectErr(esc.acceptJob(dual, id), "BadState");
  });

  it("Funded → requester cancels → Closed-refunded: P returned", async () => {
    const id = await jobTo("funded");
    await expectErr(esc.settle("refund", stranger, id), "Unauthorized");
    const before = await bal(requester.publicKey);
    await esc.settle("refund", requester, id);
    const j = await esc.job(id);
    expect(stateName(j.state)).to.eq("closedRefunded");
    expect(j.settled).to.eq(true);
    expect(await bal(requester.publicKey)).to.eq(before + BigInt(P + FEE));
  });

  it("Assigned → commit_result → Committed: Merkle root, output digest and slot recorded", async () => {
    const id = await jobTo("assigned");
    await expectErr(esc.commitResult(dual, id, h32("x"), h32("y")), "Unauthorized");
    await esc.commitResult(prov, id, h32("root"), h32("out"));
    const j = await esc.job(id);
    expect(stateName(j.state)).to.eq("committed");
    expect(Buffer.from(j.merkleRoot)).to.deep.eq(h32("root"));
    expect(Buffer.from(j.outputDigest)).to.deep.eq(h32("out"));
    expect(j.commitSlot.toNumber()).to.be.greaterThan(0);
  });

  it("Assigned → deadline passes → Closed-refunded: P returned, B returned", async () => {
    await cfg({ execTimeout: 3 });
    const id = newId();
    await esc.createJob(requester, id, P, FEE, B);
    await esc.acceptJob(prov, id);
    const locked = (await esc.bond(prov.publicKey)).locked;
    const j = await esc.job(id);
    // before the deadline the refund is refused
    if ((await esc.slot()) < j.execDeadline.toNumber() - 1)
      await expectErr(esc.settle("timeoutRefund", stranger, id), "TimeoutNotReached");
    await esc.waitSlotAfter(j.execDeadline.toNumber());
    await expectErr(esc.commitResult(prov, id, h32("late"), h32("late")), "DeadlinePassed");
    const before = await bal(requester.publicKey);
    await esc.settle("timeoutRefund", stranger, id);
    expect(await state(id)).to.eq("closedRefunded");
    expect(await bal(requester.publicKey)).to.eq(before + BigInt(P + FEE));
    expect((await esc.bond(prov.publicKey)).locked.toNumber()).to.eq(locked.toNumber() - B);
  });

  it("Committed → draw_sample, not sampled → Closed-paid; release: P to provider, B returned", async () => {
    const id = await jobTo("committed", 0);
    await expectErr(esc.drawSample(admin, id, false), "DrawTooEarly");
    await esc.drawSample(admin, id);
    const j = await esc.job(id);
    expect(stateName(j.state)).to.eq("closedPaid");
    expect(j.sampled).to.eq(false);
    expect(j.drawSlot.toNumber()).to.be.at.least(j.commitSlot.toNumber() + 2);
    const [p0, r0, b0] = [await bal(prov.publicKey), await bal(requester.publicKey), await esc.bond(prov.publicKey)];
    await esc.settle("release", stranger, id);
    expect(await bal(prov.publicKey)).to.eq(p0 + BigInt(P));
    expect(await bal(requester.publicKey)).to.eq(r0 + BigInt(FEE)); // no verification: fee back
    expect((await esc.bond(prov.publicKey)).locked.toNumber()).to.eq(b0.locked.toNumber() - B);
    expect((await esc.job(id)).settled).to.eq(true);
    expect(await esc.connection.getAccountInfo(pdas.vault(pdas.job(id)))).to.eq(null);
  });

  it("Committed → draw_sample, sampled → UnderVerification; seed = H(slot_hash ‖ job_id)", async () => {
    const id = await jobTo("drawn", 1);
    const j = await esc.job(id);
    expect(stateName(j.state)).to.eq("underVerification");
    expect(j.sampled).to.eq(true);
    expect(Buffer.from(j.drawSeed).equals(Buffer.alloc(32))).to.eq(false);
    await expectErr(esc.drawSample(admin, id, false), "BadState");
  });

  it("UnderVerification → submit_verdict = pass → Closed-paid: P to provider, B returned, fee to verifier", async () => {
    const id = await jobTo("drawn", 1);
    await expectErr(esc.submitVerdict(stranger, id, { commit: h32("c") }), "NotVerifier");
    await expectErr(esc.submitVerdict(v1, id, { reveal: "pass" }), "Unauthorized"); // reveal before commit
    await esc.submitVerdict(v1, id, { commit: h32("c1") });
    expect(await state(id)).to.eq("underVerification");
    await expectErr(esc.submitVerdict(v2, id, { commit: h32("c2") }), "CommitOrder");
    await esc.submitVerdict(v1, id, { reveal: "pass" });
    expect(await state(id)).to.eq("closedPaid");
    const [p0, f0] = [await bal(prov.publicKey), await bal(v1.publicKey)];
    await esc.settle("release", stranger, id);
    expect(await bal(prov.publicKey)).to.eq(p0 + BigInt(P));
    expect(await bal(v1.publicKey)).to.eq(f0 + BigInt(FEE));
  });

  it("a node never verifies itself (SelfVerification)", async () => {
    const id = await jobTo("drawn", 1, dual);
    await expectErr(esc.submitVerdict(dual, id, { commit: h32("self") }), "SelfVerification");
  });

  it("UnderVerification → submit_verdict = fail or inconclusive → Disputed", async () => {
    for (const v of ["fail", "inconclusive"] as VerdictName[]) {
      const id = await jobTo("drawn", 1);
      await verdict1(id, v);
      const j = await esc.job(id);
      expect(stateName(j.state)).to.eq("disputed");
      expect(Object.keys(j.v1Verdict)[0]).to.eq(v);
    }
  });

  it("Disputed → escalate (provider, requester or orchestrator only)", async () => {
    const id = await jobTo("drawn", 1);
    await verdict1(id, "fail");
    await expectErr(esc.finalVerdict(v2, id, { commit: h32("early") }), "NotEscalated");
    await expectErr(esc.escalate(stranger, id), "Unauthorized");
    await esc.escalate(orch, id);
    expect((await esc.job(id)).escalated).to.eq(true);
    expect(await state(id)).to.eq("disputed");
    await expectErr(esc.escalate(prov, id), "AlreadyEscalated");
  });

  it("Disputed → final_verdict: second verifier agrees with the provider → Closed-paid (as for pass)", async () => {
    const id = await jobTo("drawn", 1);
    await verdict1(id, "fail");
    await esc.escalate(prov, id);
    await expectErr(esc.finalVerdict(v1, id, { commit: h32("again") }), "SameVerifier");
    await verdict2(id, "pass");
    expect(await state(id)).to.eq("closedPaid");
    const [p0, a0, b0] = [await bal(prov.publicKey), await bal(v1.publicKey), await bal(v2.publicKey)];
    await esc.settle("release", stranger, id);
    expect(await bal(prov.publicKey)).to.eq(p0 + BigInt(P));
    expect(await bal(v1.publicKey)).to.eq(a0 + BigInt(FEE - FEE / 2));
    expect(await bal(v2.publicKey)).to.eq(b0 + BigInt(FEE / 2));
  });

  it("Disputed → final_verdict: both verifiers against the provider → Closed-refunded, B slashed", async () => {
    const id = await jobTo("drawn", 1);
    await verdict1(id, "fail");
    await esc.escalate(requester, id);
    await verdict2(id, "fail");
    const j = await esc.job(id);
    expect(stateName(j.state)).to.eq("closedRefunded");
    expect(j.slashed).to.eq(true);
    await expectErr(esc.settle("refund", stranger, id), "BadState");
    await expectErr(esc.settle("release", stranger, id), "BadState");
    const [r0, t0, b0] = [await bal(requester.publicKey), await esc.tokenBalance(pdas.treasury()), await esc.bond(prov.publicKey)];
    await esc.settle("slash", stranger, id);
    expect(await bal(requester.publicKey)).to.eq(r0 + BigInt(P));
    expect(await esc.tokenBalance(pdas.treasury())).to.eq(t0 + BigInt(B));
    const b1 = await esc.bond(prov.publicKey);
    expect(b1.deposited.toNumber()).to.eq(b0.deposited.toNumber() - B);
    expect(b1.locked.toNumber()).to.eq(b0.locked.toNumber() - B);
    expect(b1.jobsSlashed).to.eq(b0.jobsSlashed + 1);
  });

  it("Disputed → final_verdict: all three disagree → Closed-unresolved; refund: P to requester, B returned", async () => {
    for (const [a, b] of [["fail", "inconclusive"], ["inconclusive", "fail"]] as VerdictName[][]) {
      const id = await jobTo("drawn", 1);
      await verdict1(id, a);
      await esc.escalate(prov, id);
      await verdict2(id, b);
      expect(await state(id)).to.eq("closedUnresolved");
      await expectErr(esc.settle("slash", stranger, id), "BadState");
      const [r0, b0, t0] = [await bal(requester.publicKey), await esc.bond(prov.publicKey), await esc.tokenBalance(pdas.treasury())];
      await esc.settle("refund", stranger, id);
      expect(await bal(requester.publicKey)).to.eq(r0 + BigInt(P));
      const b1 = await esc.bond(prov.publicKey);
      expect(b1.locked.toNumber()).to.eq(b0.locked.toNumber() - B);
      expect(b1.deposited.toNumber()).to.eq(b0.deposited.toNumber());
      expect(await esc.tokenBalance(pdas.treasury())).to.eq(t0);
    }
  });

  it("any open state → timeout_refund after the dispute deadline → Closed-refunded: P to requester, B returned", async () => {
    const ids: Record<string, BN> = {};
    // Funded, Committed, UnderVerification and Disputed jobs, all left to stall
    await cfg({ execTimeout: 20, disputeTimeout: 20 });
    ids.funded = newId();
    await esc.createJob(requester, ids.funded, P, FEE, B);
    ids.committed = newId();
    await esc.createJob(requester, ids.committed, P, FEE, B);
    await esc.acceptJob(prov, ids.committed);
    await esc.commitResult(prov, ids.committed, h32("r"), h32("o"));
    await cfg({ sampleProb: 1, execTimeout: 20, disputeTimeout: 20 });
    ids.underVerification = newId();
    await esc.createJob(requester, ids.underVerification, P, FEE, B);
    await esc.acceptJob(prov, ids.underVerification);
    await esc.commitResult(prov, ids.underVerification, h32("r"), h32("o"));
    await esc.drawSample(admin, ids.underVerification);
    ids.disputed = newId();
    await esc.createJob(requester, ids.disputed, P, FEE, B);
    await esc.acceptJob(prov, ids.disputed);
    await esc.commitResult(prov, ids.disputed, h32("r"), h32("o"));
    await esc.drawSample(admin, ids.disputed);
    await verdict1(ids.disputed, "fail");
    for (const [st, id] of Object.entries(ids)) {
      expect(await state(id)).to.eq(st);
      await expectErr(esc.settle("timeoutRefund", stranger, id), "TimeoutNotReached");
    }
    const deadlines = await Promise.all(Object.values(ids).map(async (id) => (await esc.job(id)).finalDeadline.toNumber()));
    await esc.waitSlotAfter(Math.max(...deadlines));
    for (const [st, id] of Object.entries(ids)) {
      const r0 = await bal(requester.publicKey);
      const lock0 = (await esc.bond(prov.publicKey)).locked.toNumber();
      await esc.settle("timeoutRefund", stranger, id);
      const j = await esc.job(id);
      expect(stateName(j.state), st).to.eq("closedRefunded");
      // fee: back to the requester unless a verifier revealed a verdict (the Disputed job)
      const fee = st === "disputed" ? 0 : FEE;
      expect(await bal(requester.publicKey), st).to.eq(r0 + BigInt(P + fee));
      const locked = (await esc.bond(prov.publicKey)).locked.toNumber();
      expect(locked, st).to.eq(st === "funded" ? lock0 : lock0 - B);
    }
    // a settled job cannot be timed out again: its vault is closed, so the accounts no longer validate
    await expectErr(esc.settle("timeoutRefund", stranger, ids.funded), "AccountNotInitialized");
    expect((await esc.job(ids.funded)).settled).to.eq(true);
  });

  it("withdraw_bond only from the free (unlocked) balance", async () => {
    const b = await esc.bond(prov.publicKey);
    const free = b.deposited.sub(b.locked).toNumber();
    await expectErr(esc.withdrawBond(prov, free + 1), "InsufficientBond");
    await esc.withdrawBond(prov, 1);
    expect((await esc.bond(prov.publicKey)).deposited.toNumber()).to.eq(b.deposited.toNumber() - 1);
  });
});
