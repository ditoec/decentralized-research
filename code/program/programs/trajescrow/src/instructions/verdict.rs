use anchor_lang::prelude::*;

use crate::error::EscrowError;
use crate::state::*;

#[derive(Accounts)]
pub struct VerifierAction<'info> {
    pub verifier: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(mut, seeds = [JOB_SEED, job.job_id.to_le_bytes().as_ref()], bump = job.bump)]
    pub job: Box<Account<'info, Job>>,
}

#[derive(Accounts)]
pub struct Escalate<'info> {
    pub caller: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(mut, seeds = [JOB_SEED, job.job_id.to_le_bytes().as_ref()], bump = job.bump)]
    pub job: Box<Account<'info, Job>>,
}

fn check_verifier(cfg: &Config, j: &Job, v: &Pubkey) -> Result<()> {
    require!(cfg.verifiers.contains(v), EscrowError::NotVerifier);
    require_keys_neq!(*v, j.provider, EscrowError::SelfVerification);
    require_keys_neq!(*v, j.requester, EscrowError::SelfVerification);
    Ok(())
}

/// First verifier. Commit records the verifier's own commitment; Reveal records the verdict:
/// UnderVerification -> ClosedPaid (pass) or Disputed (fail / inconclusive).
pub fn handle_submit_verdict(ctx: Context<VerifierAction>, msg: VerdictMsg) -> Result<()> {
    let slot = Clock::get()?.slot;
    let v = ctx.accounts.verifier.key();
    let j = &mut ctx.accounts.job;
    require!(j.state == JobState::UnderVerification, EscrowError::BadState);
    check_verifier(&ctx.accounts.config, j, &v)?;
    match msg {
        VerdictMsg::Commit { commitment } => {
            require!(j.verifier1 == Pubkey::default(), EscrowError::CommitOrder);
            j.verifier1 = v;
            j.v1_commitment = commitment;
        }
        VerdictMsg::Reveal { verdict } => {
            require_keys_eq!(v, j.verifier1, EscrowError::Unauthorized);
            require!(j.v1_verdict == Verdict::None, EscrowError::CommitOrder);
            require!(verdict != Verdict::None, EscrowError::BadVerdict);
            j.v1_verdict = verdict;
            let to = if verdict == Verdict::Pass { JobState::ClosedPaid } else { JobState::Disputed };
            j.transition(to, slot);
        }
    }
    Ok(())
}

/// Disputed: opens the adjudication by a second verifier. The provider, the requester or the
/// orchestrator may escalate. The state stays Disputed until `final_verdict` or `timeout_refund`.
pub fn handle_escalate(ctx: Context<Escalate>) -> Result<()> {
    let c = ctx.accounts.caller.key();
    let cfg = &ctx.accounts.config;
    let j = &mut ctx.accounts.job;
    require!(j.state == JobState::Disputed, EscrowError::BadState);
    require!(!j.escalated, EscrowError::AlreadyEscalated);
    require!(c == j.provider || c == j.requester || c == cfg.orchestrator, EscrowError::Unauthorized);
    j.escalated = true;
    Ok(())
}

/// Second verifier, two-of-three over (provider's claim = pass, verifier 1, verifier 2):
///   v2 = pass                -> ClosedPaid (second verifier agrees with the provider)
///   v2 = fail and v1 = fail  -> ClosedRefunded with the bond slashed (both against the provider)
///   otherwise                -> ClosedUnresolved (no two-of-three majority; no penalty)
/// No ground-truth label enters this decision: only the two recorded verdicts do.
pub fn handle_final_verdict(ctx: Context<VerifierAction>, msg: VerdictMsg) -> Result<()> {
    let slot = Clock::get()?.slot;
    let v = ctx.accounts.verifier.key();
    let j = &mut ctx.accounts.job;
    require!(j.state == JobState::Disputed, EscrowError::BadState);
    require!(j.escalated, EscrowError::NotEscalated);
    check_verifier(&ctx.accounts.config, j, &v)?;
    require_keys_neq!(v, j.verifier1, EscrowError::SameVerifier);
    match msg {
        VerdictMsg::Commit { commitment } => {
            require!(j.verifier2 == Pubkey::default(), EscrowError::CommitOrder);
            j.verifier2 = v;
            j.v2_commitment = commitment;
        }
        VerdictMsg::Reveal { verdict } => {
            require_keys_eq!(v, j.verifier2, EscrowError::Unauthorized);
            require!(j.v2_verdict == Verdict::None, EscrowError::CommitOrder);
            require!(verdict != Verdict::None, EscrowError::BadVerdict);
            j.v2_verdict = verdict;
            let to = match (j.v1_verdict, verdict) {
                (_, Verdict::Pass) => JobState::ClosedPaid,
                (Verdict::Fail, Verdict::Fail) => {
                    j.slashed = true;
                    JobState::ClosedRefunded
                }
                _ => JobState::ClosedUnresolved,
            };
            j.transition(to, slot);
        }
    }
    Ok(())
}
