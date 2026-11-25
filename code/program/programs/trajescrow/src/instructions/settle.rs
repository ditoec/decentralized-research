use anchor_lang::prelude::*;
use anchor_spl::token::{self, CloseAccount, Token, TokenAccount, Transfer};

use crate::error::EscrowError;
use crate::state::*;

/// Accounts shared by `release`, `refund`, `slash` and `timeout_refund`. Settlement is
/// permissionless (any payer may crank it) except a requester's cancel of a Funded job.
/// Optional accounts are needed only on the paths that pay them.
#[derive(Accounts)]
pub struct Settle<'info> {
    pub caller: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(mut, seeds = [JOB_SEED, job.job_id.to_le_bytes().as_ref()], bump = job.bump)]
    pub job: Box<Account<'info, Job>>,
    #[account(mut, seeds = [VAULT_SEED, job.key().as_ref()], bump = job.vault_bump)]
    pub vault: Box<Account<'info, TokenAccount>>,
    /// CHECK: receives the vault's rent when it is closed; must be the job's requester.
    #[account(mut, address = job.requester @ EscrowError::Unauthorized)]
    pub requester: UncheckedAccount<'info>,
    #[account(mut, token::mint = config.mint, token::authority = job.requester)]
    pub requester_token: Box<Account<'info, TokenAccount>>,
    #[account(mut, token::mint = config.mint, token::authority = job.provider)]
    pub provider_token: Option<Box<Account<'info, TokenAccount>>>,
    #[account(mut, seeds = [BOND_SEED, job.provider.as_ref()], bump = provider_bond.bump)]
    pub provider_bond: Option<Box<Account<'info, ProviderBond>>>,
    #[account(mut, seeds = [BOND_VAULT_SEED, job.provider.as_ref()], bump)]
    pub bond_vault: Option<Box<Account<'info, TokenAccount>>>,
    #[account(mut, address = config.treasury)]
    pub treasury: Option<Box<Account<'info, TokenAccount>>>,
    #[account(mut, token::mint = config.mint, token::authority = job.verifier1)]
    pub verifier1_token: Option<Box<Account<'info, TokenAccount>>>,
    #[account(mut, token::mint = config.mint, token::authority = job.verifier2)]
    pub verifier2_token: Option<Box<Account<'info, TokenAccount>>>,
    pub token_program: Program<'info, Token>,
}

#[derive(PartialEq)]
enum Payee {
    Provider,
    Requester { slash: bool },
}

fn pay<'info>(
    a: &Settle<'info>,
    to: &Option<Box<Account<'info, TokenAccount>>>,
    amount: u64,
    seeds: &[&[u8]],
) -> Result<()> {
    if amount == 0 {
        return Ok(());
    }
    let to = to.as_ref().ok_or(EscrowError::MissingAccount)?;
    token::transfer(
        CpiContext::new_with_signer(
            a.token_program.key(),
            Transfer {
                from: a.vault.to_account_info(),
                to: to.to_account_info(),
                authority: a.job.to_account_info(),
            },
            &[seeds],
        ),
        amount,
    )
}

/// Moves P, the verifier fee and the bond, closes the vault and marks the job settled.
/// Verifier fee: to the verifier(s) who revealed a verdict (split evenly, remainder to the first);
/// to the requester when no verification took place.
fn payout(ctx: Context<Settle>, payee: Payee) -> Result<()> {
    let a = &ctx.accounts;
    let j = &a.job;
    require!(!j.settled, EscrowError::AlreadySettled);
    let id = j.job_id.to_le_bytes();
    let seeds: &[&[u8]] = &[JOB_SEED, id.as_ref(), &[j.bump]];
    let req = Some(a.requester_token.clone());

    // payment P
    let p_to = if payee == Payee::Provider { &a.provider_token } else { &req };
    pay(a, p_to, j.payment, seeds)?;

    // verifier fee
    let v1 = j.v1_verdict != Verdict::None;
    let v2 = j.v2_verdict != Verdict::None;
    let fee = j.verifier_fee;
    let (f1, f2, fr) = match (v1, v2) {
        (true, true) => (fee - fee / 2, fee / 2, 0),
        (true, false) => (fee, 0, 0),
        _ => (0, 0, fee),
    };
    pay(a, &a.verifier1_token, f1, seeds)?;
    pay(a, &a.verifier2_token, f2, seeds)?;
    pay(a, &req, fr, seeds)?;

    // bond B: unlocked, or moved to the treasury
    let mut slashed = 0;
    if j.provider != Pubkey::default() {
        let b = a.provider_bond.as_ref().ok_or(EscrowError::MissingAccount)?;
        if payee == (Payee::Requester { slash: true }) && j.bond > 0 {
            let vault = a.bond_vault.as_ref().ok_or(EscrowError::MissingAccount)?;
            let tre = a.treasury.as_ref().ok_or(EscrowError::MissingAccount)?;
            let bseeds: &[&[u8]] = &[BOND_SEED, j.provider.as_ref(), &[b.bump]];
            token::transfer(
                CpiContext::new_with_signer(
                    a.token_program.key(),
                    Transfer {
                        from: vault.to_account_info(),
                        to: tre.to_account_info(),
                        authority: b.to_account_info(),
                    },
                    &[bseeds],
                ),
                j.bond,
            )?;
            slashed = j.bond;
        }
    }

    // close the empty vault, rent back to the requester
    token::close_account(CpiContext::new_with_signer(
        a.token_program.key(),
        CloseAccount {
            account: a.vault.to_account_info(),
            destination: a.requester.to_account_info(),
            authority: a.job.to_account_info(),
        },
        &[seeds],
    ))?;

    let (job_id, bond, state, payment) = (j.job_id, j.bond, j.state, j.payment);
    if let Some(b) = ctx.accounts.provider_bond.as_mut() {
        if ctx.accounts.job.provider != Pubkey::default() {
            b.locked -= bond;
            b.deposited -= slashed;
            match payee {
                Payee::Provider => b.jobs_paid += 1,
                Payee::Requester { slash: true } => b.jobs_slashed += 1,
                _ => {}
            }
        }
    }
    ctx.accounts.job.settled = true;
    emit!(Settled {
        job_id,
        state,
        to_provider: if payee == Payee::Provider { payment } else { 0 },
        to_requester: if payee == Payee::Provider { fr } else { payment + fr },
        to_verifiers: f1 + f2,
        slashed,
    });
    Ok(())
}

/// ClosedPaid: P to the provider, B unlocked, fee to the verifier(s) if the job was verified.
pub fn handle_release(ctx: Context<Settle>) -> Result<()> {
    require!(ctx.accounts.job.state == JobState::ClosedPaid, EscrowError::BadState);
    payout(ctx, Payee::Provider)
}

/// Funded (requester cancels before assignment): -> ClosedRefunded, P and fee returned.
/// ClosedUnresolved: P to the requester, B unlocked (no penalty).
pub fn handle_refund(ctx: Context<Settle>) -> Result<()> {
    let slot = Clock::get()?.slot;
    match ctx.accounts.job.state {
        JobState::Funded => {
            require_keys_eq!(ctx.accounts.caller.key(), ctx.accounts.job.requester, EscrowError::Unauthorized);
            ctx.accounts.job.transition(JobState::ClosedRefunded, slot);
        }
        JobState::ClosedUnresolved => {}
        _ => return err!(EscrowError::BadState),
    }
    payout(ctx, Payee::Requester { slash: false })
}

/// ClosedRefunded after two fail verdicts: P to the requester, B to the treasury.
pub fn handle_slash(ctx: Context<Settle>) -> Result<()> {
    let j = &ctx.accounts.job;
    require!(j.state == JobState::ClosedRefunded && j.slashed, EscrowError::BadState);
    payout(ctx, Payee::Requester { slash: true })
}

/// Assigned past the execution deadline, or any open state past the dispute (final) deadline:
/// -> ClosedRefunded, P to the requester, B returned.
pub fn handle_timeout_refund(ctx: Context<Settle>) -> Result<()> {
    let slot = Clock::get()?.slot;
    let j = &mut ctx.accounts.job;
    require!(j.state.is_open(), EscrowError::BadState);
    let due = (j.state == JobState::Assigned && slot > j.exec_deadline) || slot > j.final_deadline;
    require!(due, EscrowError::TimeoutNotReached);
    j.transition(JobState::ClosedRefunded, slot);
    payout(ctx, Payee::Requester { slash: false })
}
