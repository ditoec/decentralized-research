use anchor_lang::prelude::*;

pub const CONFIG_SEED: &[u8] = b"config";
pub const TREASURY_SEED: &[u8] = b"treasury";
pub const JOB_SEED: &[u8] = b"job";
pub const VAULT_SEED: &[u8] = b"vault";
pub const BOND_SEED: &[u8] = b"bond";
pub const BOND_VAULT_SEED: &[u8] = b"bond_vault";

/// Sampling probability p is stored in parts per million: p = sample_ppm / 1e6.
pub const PPM: u32 = 1_000_000;
/// Upper bound on the verifier pool kept in `Config`.
pub const MAX_VERIFIERS: usize = 8;

/// Lifecycle states of a job (runbook section 7 item 1, manuscript Figure 2).
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug, InitSpace)]
pub enum JobState {
    Funded,
    Assigned,
    Committed,
    UnderVerification,
    Disputed,
    ClosedPaid,
    ClosedRefunded,
    ClosedUnresolved,
}

impl JobState {
    pub fn is_open(&self) -> bool {
        !matches!(self, JobState::ClosedPaid | JobState::ClosedRefunded | JobState::ClosedUnresolved)
    }
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug, InitSpace)]
pub enum Verdict {
    None,
    Pass,
    Fail,
    Inconclusive,
}

/// A verifier first records a commitment to its own recomputed values (before the provider's
/// commitment is opened to it), then, in a later transaction, its verdict.
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, Debug)]
pub enum VerdictMsg {
    Commit { commitment: [u8; 32] },
    Reveal { verdict: Verdict },
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, PartialEq, Eq, Debug)]
pub struct ConfigParams {
    /// Off-chain orchestrator key; may escalate disputes on behalf of either party.
    pub orchestrator: Pubkey,
    /// p in parts per million, copied into each job at `create_job`.
    pub sample_ppm: u32,
    /// DELAY: `draw_sample` uses the slot hash of `commit_slot + draw_delay` (or the first produced slot after it).
    pub draw_delay: u64,
    /// Slots the provider has after `accept_job` to `commit_result`.
    pub exec_timeout: u64,
    /// Slots after the execution deadline until any open job can be refunded by `timeout_refund`.
    pub dispute_timeout: u64,
    /// Registered verifier pool (a verifier never verifies its own job; enforced per job).
    pub verifiers: Vec<Pubkey>,
}

#[account]
#[derive(InitSpace)]
pub struct Config {
    pub admin: Pubkey,
    pub orchestrator: Pubkey,
    pub mint: Pubkey,
    pub treasury: Pubkey,
    pub sample_ppm: u32,
    pub draw_delay: u64,
    pub exec_timeout: u64,
    pub dispute_timeout: u64,
    #[max_len(MAX_VERIFIERS)]
    pub verifiers: Vec<Pubkey>,
    pub bump: u8,
    pub treasury_bump: u8,
}

/// Per-provider bond account. Tokens sit in the provider's bond vault; `accept_job` locks B of the
/// free balance for the job, settlement unlocks it or (on a confirmed fail) moves it to the treasury.
#[account]
#[derive(InitSpace)]
pub struct ProviderBond {
    pub provider: Pubkey,
    pub deposited: u64,
    pub locked: u64,
    pub jobs_accepted: u32,
    pub jobs_paid: u32,
    pub jobs_slashed: u32,
    pub bump: u8,
    pub vault_bump: u8,
}

#[account]
#[derive(InitSpace)]
pub struct Job {
    pub job_id: u64,
    pub requester: Pubkey,
    pub provider: Pubkey,
    /// P
    pub payment: u64,
    pub verifier_fee: u64,
    /// B
    pub bond: u64,
    pub sample_ppm: u32,
    pub state: JobState,
    pub created_slot: u64,
    pub accept_slot: u64,
    pub exec_deadline: u64,
    pub final_deadline: u64,
    pub commit_slot: u64,
    pub merkle_root: [u8; 32],
    pub output_digest: [u8; 32],
    /// Slot whose hash seeded the draw, and the draw seed H(slot_hash || job_id_le).
    pub draw_slot: u64,
    pub draw_seed: [u8; 32],
    pub sampled: bool,
    pub verifier1: Pubkey,
    pub v1_commitment: [u8; 32],
    pub v1_verdict: Verdict,
    pub escalated: bool,
    pub verifier2: Pubkey,
    pub v2_commitment: [u8; 32],
    pub v2_verdict: Verdict,
    /// Closed-refunded with the bond forfeited (both verifiers against the provider).
    pub slashed: bool,
    pub settled: bool,
    pub bump: u8,
    pub vault_bump: u8,
}

#[event]
pub struct Transition {
    pub job_id: u64,
    pub from: JobState,
    pub to: JobState,
    pub slot: u64,
}

#[event]
pub struct Drawn {
    pub job_id: u64,
    pub draw_slot: u64,
    pub draw_seed: [u8; 32],
    pub sampled: bool,
}

#[event]
pub struct Settled {
    pub job_id: u64,
    pub state: JobState,
    pub to_provider: u64,
    pub to_requester: u64,
    pub to_verifiers: u64,
    pub slashed: u64,
}

impl Job {
    pub fn transition(&mut self, to: JobState, slot: u64) {
        emit!(Transition { job_id: self.job_id, from: self.state, to, slot });
        self.state = to;
    }
}
