// Client for the trajescrow program: PDAs, one method per instruction, and per-transaction
// measurement (signature count, compute units, fee). Used by the tests, the path replay
// (scripts/replay.ts) and the orchestrator's relay (scripts/relay.ts).
import * as anchor from "@anchor-lang/core";
import { BN, Program } from "@anchor-lang/core";
import {
  Connection,
  Keypair,
  LAMPORTS_PER_SOL,
  PublicKey,
  SystemProgram,
  SYSVAR_SLOT_HASHES_PUBKEY,
  Transaction,
  TransactionInstruction,
  sendAndConfirmTransaction,
} from "@solana/web3.js";
import {
  TOKEN_PROGRAM_ID,
  createMint,
  getAssociatedTokenAddressSync,
  getOrCreateAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";
import idl from "../idl/trajescrow.json";
import type { Trajescrow } from "../idl/trajescrow";

const CONFIRMED = { commitment: "confirmed", preflightCommitment: "confirmed" } as const;
export const PROGRAM_ID = new PublicKey((idl as any).address);
const u64le = (n: BN | number | bigint) => new BN(n.toString()).toArrayLike(Buffer, "le", 8);
const pda = (seeds: (Buffer | Uint8Array)[]) => PublicKey.findProgramAddressSync(seeds, PROGRAM_ID)[0];

export const pdas = {
  config: () => pda([Buffer.from("config")]),
  treasury: () => pda([Buffer.from("treasury")]),
  job: (id: BN | number | bigint) => pda([Buffer.from("job"), u64le(id)]),
  vault: (job: PublicKey) => pda([Buffer.from("vault"), job.toBuffer()]),
  bond: (provider: PublicKey) => pda([Buffer.from("bond"), provider.toBuffer()]),
  bondVault: (provider: PublicKey) => pda([Buffer.from("bond_vault"), provider.toBuffer()]),
};

export type VerdictName = "pass" | "fail" | "inconclusive";
export type StateName =
  | "funded" | "assigned" | "committed" | "underVerification" | "disputed"
  | "closedPaid" | "closedRefunded" | "closedUnresolved";

export interface ConfigParams {
  orchestrator: PublicKey;
  sampleProb: number; // p in [0, 1]
  drawDelay: number;
  execTimeout: number;
  disputeTimeout: number;
  verifiers: PublicKey[];
}

export interface TxRecord {
  name: string;
  sig: string;
  nsig: number;
  cu: number | null;
  fee: number | null;
  slot: number | null;
  ms_confirmed: number;
}

export function stateName(s: any): StateName {
  return Object.keys(s)[0] as StateName;
}

export class Escrow {
  readonly program: Program<Trajescrow>;
  mint!: PublicKey;
  records: TxRecord[] = [];
  measure = true;

  readonly connection: Connection;

  constructor(connection: Connection, readonly payer: Keypair) {
    // all reads, simulations and confirmations at "confirmed"
    this.connection = new Connection(connection.rpcEndpoint, "confirmed");
    const wallet = new anchor.Wallet(payer);
    const provider = new anchor.AnchorProvider(this.connection, wallet, {
      commitment: "confirmed",
      preflightCommitment: "confirmed",
    });
    this.program = new Program<Trajescrow>(idl as any, provider);
  }

  // ---------- plumbing ----------
  async send(name: string, ix: TransactionInstruction, signer: Keypair): Promise<TxRecord> {
    const t0 = Date.now();
    const sig = await sendAndConfirmTransaction(this.connection, new Transaction().add(ix), [signer], {
      commitment: "confirmed",
      preflightCommitment: "confirmed",
    });
    const rec: TxRecord = { name, sig, nsig: 1, cu: null, fee: null, slot: null, ms_confirmed: Date.now() - t0 };
    if (this.measure) {
      for (let i = 0; i < 20; i++) {
        const tx = await this.connection.getTransaction(sig, { commitment: "confirmed", maxSupportedTransactionVersion: 0 });
        if (tx) {
          rec.nsig = tx.transaction.signatures.length;
          rec.cu = tx.meta?.computeUnitsConsumed ?? null;
          rec.fee = tx.meta?.fee ?? null;
          rec.slot = tx.slot;
          break;
        }
        await sleep(100);
      }
    }
    this.records.push(rec);
    return rec;
  }

  async airdrop(to: PublicKey, sol = 10) {
    const sig = await this.connection.requestAirdrop(to, sol * LAMPORTS_PER_SOL);
    const bh = await this.connection.getLatestBlockhash();
    await this.connection.confirmTransaction({ signature: sig, ...bh }, "confirmed");
  }

  async slot(): Promise<number> {
    return this.connection.getSlot("confirmed");
  }

  /** Wait until the confirmed slot is strictly greater than `s`. */
  async waitSlotAfter(s: number) {
    while ((await this.slot()) <= s) await sleep(150);
  }

  ata(owner: PublicKey) {
    return getAssociatedTokenAddressSync(this.mint, owner);
  }

  async fundTokens(owner: PublicKey, amount: number | bigint) {
    const acc = await getOrCreateAssociatedTokenAccount(this.connection, this.payer, this.mint, owner, false, "confirmed", CONFIRMED);
    if (BigInt(amount) > 0n) await mintTo(this.connection, this.payer, this.mint, acc.address, this.payer, amount, [], CONFIRMED);
    return acc.address;
  }

  async tokenBalance(acc: PublicKey): Promise<bigint> {
    try {
      const b = await this.connection.getTokenAccountBalance(acc, "confirmed");
      return BigInt(b.value.amount);
    } catch {
      return 0n;
    }
  }

  // ---------- config ----------
  private params(p: ConfigParams) {
    return {
      orchestrator: p.orchestrator,
      samplePpm: Math.round(p.sampleProb * 1_000_000),
      drawDelay: new BN(p.drawDelay),
      execTimeout: new BN(p.execTimeout),
      disputeTimeout: new BN(p.disputeTimeout),
      verifiers: p.verifiers,
    };
  }

  /** Creates a test mint (local validator only) and initializes Config, or loads an existing one. */
  async init(p: ConfigParams, mint?: PublicKey) {
    const existing = await this.program.account.config.fetchNullable(pdas.config());
    if (existing) {
      this.mint = existing.mint;
      await this.updateConfig(p);
      return;
    }
    this.mint = mint ?? (await createMint(this.connection, this.payer, this.payer.publicKey, null, 6, undefined, CONFIRMED));
    const ix = await this.program.methods
      .initializeConfig(this.params(p))
      .accountsPartial({
        admin: this.payer.publicKey, config: pdas.config(), mint: this.mint, treasury: pdas.treasury(),
        tokenProgram: TOKEN_PROGRAM_ID, systemProgram: SystemProgram.programId,
      })
      .instruction();
    await this.send("initialize_config", ix, this.payer);
  }

  async updateConfig(p: ConfigParams) {
    const ix = await this.program.methods
      .updateConfig(this.params(p))
      .accountsPartial({ admin: this.payer.publicKey, config: pdas.config() })
      .instruction();
    return this.send("update_config", ix, this.payer);
  }

  config() {
    return this.program.account.config.fetch(pdas.config());
  }

  // ---------- bond ----------
  async openBond(provider: Keypair) {
    const ix = await this.program.methods
      .openBond()
      .accountsPartial({
        provider: provider.publicKey, config: pdas.config(), mint: this.mint,
        providerBond: pdas.bond(provider.publicKey), bondVault: pdas.bondVault(provider.publicKey),
        tokenProgram: TOKEN_PROGRAM_ID, systemProgram: SystemProgram.programId,
      })
      .instruction();
    return this.send("open_bond", ix, provider);
  }

  private moveBondAccounts(provider: Keypair) {
    return {
      provider: provider.publicKey, config: pdas.config(), providerBond: pdas.bond(provider.publicKey),
      bondVault: pdas.bondVault(provider.publicKey), providerToken: this.ata(provider.publicKey),
      tokenProgram: TOKEN_PROGRAM_ID,
    };
  }

  async depositBond(provider: Keypair, amount: number) {
    const ix = await this.program.methods.depositBond(new BN(amount)).accountsPartial(this.moveBondAccounts(provider)).instruction();
    return this.send("deposit_bond", ix, provider);
  }

  async withdrawBond(provider: Keypair, amount: number) {
    const ix = await this.program.methods.withdrawBond(new BN(amount)).accountsPartial(this.moveBondAccounts(provider)).instruction();
    return this.send("withdraw_bond", ix, provider);
  }

  bond(provider: PublicKey) {
    return this.program.account.providerBond.fetch(pdas.bond(provider));
  }

  // ---------- job lifecycle ----------
  job(id: BN | number) {
    return this.program.account.job.fetch(pdas.job(new BN(id.toString())));
  }

  async createJob(requester: Keypair, id: BN | number, payment: number, fee: number, bond: number) {
    const job = pdas.job(new BN(id.toString()));
    const ix = await this.program.methods
      .createJob(new BN(id.toString()), new BN(payment), new BN(fee), new BN(bond))
      .accountsPartial({
        requester: requester.publicKey, config: pdas.config(), mint: this.mint, job, vault: pdas.vault(job),
        requesterToken: this.ata(requester.publicKey), tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .instruction();
    return this.send("create_job", ix, requester);
  }

  async acceptJob(provider: Keypair, id: BN | number) {
    const ix = await this.program.methods
      .acceptJob()
      .accountsPartial({
        provider: provider.publicKey, config: pdas.config(), job: pdas.job(new BN(id.toString())),
        providerBond: pdas.bond(provider.publicKey),
      })
      .instruction();
    return this.send("accept_job", ix, provider);
  }

  async commitResult(provider: Keypair, id: BN | number, merkleRoot: Buffer, outputDigest: Buffer) {
    const ix = await this.program.methods
      .commitResult([...merkleRoot], [...outputDigest])
      .accountsPartial({ provider: provider.publicKey, job: pdas.job(new BN(id.toString())) })
      .instruction();
    return this.send("commit_result", ix, provider);
  }

  /** Waits until the draw is allowed (slot > commit_slot + DELAY), then draws. */
  async drawSample(caller: Keypair, id: BN | number, wait = true) {
    if (wait) {
      const [j, c] = await Promise.all([this.job(id), this.config()]);
      await this.waitSlotAfter(j.commitSlot.toNumber() + c.drawDelay.toNumber());
    }
    const ix = await this.program.methods
      .drawSample()
      .accountsPartial({ config: pdas.config(), job: pdas.job(new BN(id.toString())), slotHashes: SYSVAR_SLOT_HASHES_PUBKEY })
      .instruction();
    return this.send("draw_sample", ix, caller);
  }

  private verdictMsg(m: { commit: Buffer } | { reveal: VerdictName }) {
    if ("commit" in m) return { commit: { commitment: [...m.commit] } };
    return { reveal: { verdict: { [m.reveal]: {} } } };
  }

  async submitVerdict(verifier: Keypair, id: BN | number, m: { commit: Buffer } | { reveal: VerdictName }) {
    const ix = await this.program.methods
      .submitVerdict(this.verdictMsg(m) as any)
      .accountsPartial({ verifier: verifier.publicKey, config: pdas.config(), job: pdas.job(new BN(id.toString())) })
      .instruction();
    return this.send("commit" in m ? "submit_verdict:commit" : "submit_verdict:reveal", ix, verifier);
  }

  async escalate(caller: Keypair, id: BN | number) {
    const ix = await this.program.methods
      .escalate()
      .accountsPartial({ caller: caller.publicKey, config: pdas.config(), job: pdas.job(new BN(id.toString())) })
      .instruction();
    return this.send("escalate", ix, caller);
  }

  async finalVerdict(verifier: Keypair, id: BN | number, m: { commit: Buffer } | { reveal: VerdictName }) {
    const ix = await this.program.methods
      .finalVerdict(this.verdictMsg(m) as any)
      .accountsPartial({ verifier: verifier.publicKey, config: pdas.config(), job: pdas.job(new BN(id.toString())) })
      .instruction();
    return this.send("commit" in m ? "final_verdict:commit" : "final_verdict:reveal", ix, verifier);
  }

  /** Accounts for release / refund / slash / timeout_refund, filled from the job's current record. */
  async settleAccounts(caller: PublicKey, id: BN | number) {
    const jobPk = pdas.job(new BN(id.toString()));
    const j = await this.program.account.job.fetch(jobPk);
    const has = (k: PublicKey) => !k.equals(PublicKey.default);
    return {
      caller, config: pdas.config(), job: jobPk, vault: pdas.vault(jobPk), requester: j.requester,
      requesterToken: this.ata(j.requester),
      providerToken: has(j.provider) ? this.ata(j.provider) : null,
      providerBond: has(j.provider) ? pdas.bond(j.provider) : null,
      bondVault: has(j.provider) ? pdas.bondVault(j.provider) : null,
      treasury: pdas.treasury(),
      verifier1Token: has(j.verifier1) ? this.ata(j.verifier1) : null,
      verifier2Token: has(j.verifier2) ? this.ata(j.verifier2) : null,
      tokenProgram: TOKEN_PROGRAM_ID,
    };
  }

  async settle(kind: "release" | "refund" | "slash" | "timeoutRefund", caller: Keypair, id: BN | number) {
    const accts = await this.settleAccounts(caller.publicKey, id);
    const ix = await (this.program.methods as any)[kind]().accountsPartial(accts).instruction();
    const name = kind === "timeoutRefund" ? "timeout_refund" : kind;
    return this.send(name, ix, caller);
  }
}

export function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Extracts the Anchor error name from a failed transaction, or "" if none. */
export function anchorError(e: any): string {
  const text = [String(e?.message ?? e), ...((e?.logs ?? e?.transactionLogs ?? []) as string[])].join("\n");
  const m = text.match(/Error Code: (\w+)/);
  if (m) return m[1];
  return text;
}
