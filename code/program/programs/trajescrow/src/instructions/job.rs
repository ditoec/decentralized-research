use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::error::EscrowError;
use crate::state::*;

#[derive(Accounts)]
#[instruction(job_id: u64)]
pub struct CreateJob<'info> {
    #[account(mut)]
    pub requester: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(address = config.mint)]
    pub mint: Box<Account<'info, Mint>>,
    #[account(init, payer = requester, space = 8 + Job::INIT_SPACE,
              seeds = [JOB_SEED, job_id.to_le_bytes().as_ref()], bump)]
    pub job: Box<Account<'info, Job>>,
    #[account(init, payer = requester, seeds = [VAULT_SEED, job.key().as_ref()], bump,
              token::mint = mint, token::authority = job)]
    pub vault: Box<Account<'info, TokenAccount>>,
    #[account(mut, token::mint = config.mint, token::authority = requester)]
    pub requester_token: Box<Account<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

/// Funded -> Assigned. The provider locks B from its bond's free balance.
#[derive(Accounts)]
pub struct AcceptJob<'info> {
    pub provider: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(mut, seeds = [JOB_SEED, job.job_id.to_le_bytes().as_ref()], bump = job.bump)]
    pub job: Box<Account<'info, Job>>,
    #[account(mut, seeds = [BOND_SEED, provider.key().as_ref()], bump = provider_bond.bump)]
    pub provider_bond: Box<Account<'info, ProviderBond>>,
}

/// Assigned -> Committed. Merkle root of the trajectory and the output digest; records the slot.
#[derive(Accounts)]
pub struct CommitResult<'info> {
    pub provider: Signer<'info>,
    #[account(mut, seeds = [JOB_SEED, job.job_id.to_le_bytes().as_ref()], bump = job.bump)]
    pub job: Box<Account<'info, Job>>,
}

pub fn handle_create_job(
    ctx: Context<CreateJob>,
    job_id: u64,
    payment: u64,
    verifier_fee: u64,
    bond: u64,
) -> Result<()> {
    require!(payment > 0, EscrowError::ZeroPayment);
    let total = payment.checked_add(verifier_fee).ok_or(EscrowError::Overflow)?;
    let a = &ctx.accounts;
    token::transfer(
        CpiContext::new(
            a.token_program.key(),
            Transfer {
                from: a.requester_token.to_account_info(),
                to: a.vault.to_account_info(),
                authority: a.requester.to_account_info(),
            },
        ),
        total,
    )?;
    let slot = Clock::get()?.slot;
    let cfg = &ctx.accounts.config;
    let final_deadline = slot
        .checked_add(cfg.exec_timeout)
        .and_then(|s| s.checked_add(cfg.dispute_timeout))
        .ok_or(EscrowError::Overflow)?;
    let sample_ppm = cfg.sample_ppm;
    let requester = ctx.accounts.requester.key();
    let j = &mut ctx.accounts.job;
    j.job_id = job_id;
    j.requester = requester;
    j.payment = payment;
    j.verifier_fee = verifier_fee;
    j.bond = bond;
    j.sample_ppm = sample_ppm;
    j.state = JobState::Funded;
    j.created_slot = slot;
    j.final_deadline = final_deadline;
    j.v1_verdict = Verdict::None;
    j.v2_verdict = Verdict::None;
    j.bump = ctx.bumps.job;
    j.vault_bump = ctx.bumps.vault;
    emit!(Transition { job_id, from: JobState::Funded, to: JobState::Funded, slot });
    Ok(())
}

pub fn handle_accept_job(ctx: Context<AcceptJob>) -> Result<()> {
    let slot = Clock::get()?.slot;
    let cfg = &ctx.accounts.config;
    let provider = ctx.accounts.provider.key();
    let j = &mut ctx.accounts.job;
    require!(j.state == JobState::Funded, EscrowError::BadState);
    require_keys_neq!(provider, j.requester, EscrowError::SelfDealing);
    let b = &mut ctx.accounts.provider_bond;
    require!(b.deposited - b.locked >= j.bond, EscrowError::InsufficientBond);
    b.locked += j.bond;
    b.jobs_accepted += 1;
    j.provider = provider;
    j.accept_slot = slot;
    j.exec_deadline = slot.checked_add(cfg.exec_timeout).ok_or(EscrowError::Overflow)?;
    j.final_deadline = j.exec_deadline.checked_add(cfg.dispute_timeout).ok_or(EscrowError::Overflow)?;
    j.transition(JobState::Assigned, slot);
    Ok(())
}

pub fn handle_commit_result(ctx: Context<CommitResult>, merkle_root: [u8; 32], output_digest: [u8; 32]) -> Result<()> {
    let slot = Clock::get()?.slot;
    let j = &mut ctx.accounts.job;
    require!(j.state == JobState::Assigned, EscrowError::BadState);
    require_keys_eq!(ctx.accounts.provider.key(), j.provider, EscrowError::Unauthorized);
    require!(slot <= j.exec_deadline, EscrowError::DeadlinePassed);
    j.merkle_root = merkle_root;
    j.output_digest = output_digest;
    j.commit_slot = slot;
    j.transition(JobState::Committed, slot);
    Ok(())
}
