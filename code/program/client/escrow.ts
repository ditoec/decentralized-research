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
  /** HTTP 429 answers the client got (and retried) between send and confirmation; only with throttledConnection */
  rpc_429?: number;
  /** dropped-connection retries between send and confirmation */
  net_retries?: number;
  cu: number | null;
  fee: number | null;
  slot: number | null;
  ms_confirmed: number;
}

/**
 * A Connection that stays under a public RPC's rate limits (Solana's public Devnet RPC: 100 requests
 * per 10 s per IP and 40 per 10 s per method). All requests are spaced at least `minGapMs` apart, and
 * requests of the same method at least `perMethodGapMs` apart. A 429 is retried here, with backoff,
 * up to 12 times. Used by the Devnet replay. Waiting in this queue counts in the measured time to confirmed.
 */
export function throttledConnection(url: string, minGapMs = 200, perMethodGapMs = 450): Connection {
  const counter = { n429: 0, nNet: 0, byMethod: {} as Record<string, number> };
  let last = 0;
  const lastByMethod = new Map<string, number>();
  let chain: Promise<void> = Promise.resolve();
  const slotFor = (method: string) => {
    const p = chain.then(async () => {
      const now = Date.now();
      const wait = Math.max(0, last + minGapMs - now, (lastByMethod.get(method) ?? 0) + perMethodGapMs - now);
      if (wait) await sleep(wait);
      last = Date.now();
      lastByMethod.set(method, last);
    });
    chain = p;
    return p;
  };
  const throttled = async (input: any, init?: any): Promise<any> => {
    let method = "?";
    try {
      const b = JSON.parse(String(init?.body ?? ""));
      method = Array.isArray(b) ? "batch" : b.method;
    } catch {}
    for (let i = 0; ; i++) {
      await slotFor(method);
      let res: Response;
      try {
        res = await fetch(input, init);
      } catch (e) {
        // dropped connection ("fetch failed"): retry; a re-sent signed transaction keeps its signature
        counter.nNet++;
        if (i >= 6) throw e;
        await sleep(Math.min(8_000, 500 * 2 ** i));
        continue;
      }
      if (res.status === 429) {
        counter.n429++;
        counter.byMethod[method] = (counter.byMethod[method] ?? 0) + 1;
      }
      if (res.status !== 429 || i >= 12) {
        if (res.status === 429) console.error(`rpc ${method}: still 429 after ${i} retries`);
        return res;
      }
      await sleep(Math.min(16_000, 500 * 2 ** i));
    }
  };
  const conn = new Connection(url, { commitment: "confirmed", fetch: throttled as any, disableRetryOnRateLimit: true });
  (conn as any).rpcCounter = counter;
  return conn;
}

export function stateName(s: any): StateName {
  return Object.keys(s)[0] as StateName;
}

export class Escrow {
  readonly program: Program<Trajescrow>;
  mint!: PublicKey;
  records: TxRecord[] = [];
  measure = true;
  /** Confirm by polling getSignatureStatuses instead of the websocket subscription (public RPCs rate-limit the websocket). */
  pollConfirm = false;

  readonly connection: Connection;

  constructor(connection: Connection, readonly payer: Keypair) {
    // all reads, simulations and confirmations at "confirmed" (a given "confirmed" connection, e.g. a throttled one, is kept)
    this.connection = connection.commitment === "confirmed" ? connection : new Connection(connection.rpcEndpoint, "confirmed");
    const wallet = new anchor.Wallet(payer);
    const provider = new anchor.AnchorProvider(this.connection, wallet, {
      commitment: "confirmed",
      preflightCommitment: "confirmed",
    });
    this.program = new Program<Trajescrow>(idl as any, provider);
  }

  // ---------- plumbing ----------
  async send(name: string, ix: TransactionInstruction, signer: Keypair): Promise<TxRecord> {
    const counter = (this.connection as any).rpcCounter as { n429: number; nNet: number } | undefined;
    const c0 = counter?.n429 ?? 0;
    const n0net = counter?.nNet ?? 0;
    const t0 = Date.now();
    const sig = this.pollConfirm
      ? await this.sendAndPoll(new Transaction().add(ix), signer)
      : await sendAndConfirmTransaction(this.connection, new Transaction().add(ix), [signer], {
          commitment: "confirmed",
          preflightCommitment: "confirmed",
        });
    const rec: TxRecord = { name, sig, nsig: 1, cu: null, fee: null, slot: null, ms_confirmed: Date.now() - t0 };
    if (counter) {
      rec.rpc_429 = counter.n429 - c0;
      rec.net_retries = counter.nNet - n0net;
    }
    if (this.measure) {
      // on a public RPC the transaction can take a few seconds to be served after confirmation
      for (let i = 0; i < 60; i++) {
        const tx = await this.connection.getTransaction(sig, { commitment: "confirmed", maxSupportedTransactionVersion: 0 });
        if (tx) {
          rec.nsig = tx.transaction.signatures.length;
          rec.cu = tx.meta?.computeUnitsConsumed ?? null;
          rec.fee = tx.meta?.fee ?? null;
          rec.slot = tx.slot;
          break;
        }
        await sleep(500);
      }
    }
    this.records.push(rec);
    return rec;
  }

  /** Sends with preflight, then polls the signature status (spaced by the throttle, about every 0.45 s) until "confirmed" or the blockhash expires. */
  private async sendAndPoll(tx: Transaction, signer: Keypair): Promise<string> {
    const bh = await this.connection.getLatestBlockhash("confirmed");
    tx.recentBlockhash = bh.blockhash;
    tx.feePayer = signer.publicKey;
    tx.sign(signer);
    const sig = await this.connection.sendRawTransaction(tx.serialize(), { preflightCommitment: "confirmed", maxRetries: 5 });
    for (let i = 0; ; i++) {
      await sleep(i === 0 ? 400 : 300);
      const st = (await this.connection.getSignatureStatuses([sig])).value[0];
      if (st?.err) throw new Error(`transaction ${sig} failed: ${JSON.stringify(st.err)}`);
      if (st && (st.confirmationStatus === "confirmed" || st.confirmationStatus === "finalized")) return sig;
      if (i % 20 === 19 && (await this.connection.getBlockHeight("confirmed")) > bh.lastValidBlockHeight)
        throw new Error(`transaction ${sig} expired before confirmation`);
    }
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
    while ((await this.slot()) <= s) await sleep(300);
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
