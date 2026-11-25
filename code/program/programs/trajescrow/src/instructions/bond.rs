use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::error::EscrowError;
use crate::state::*;

#[derive(Accounts)]
pub struct OpenBond<'info> {
    #[account(mut)]
    pub provider: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(address = config.mint)]
    pub mint: Box<Account<'info, Mint>>,
    #[account(init, payer = provider, space = 8 + ProviderBond::INIT_SPACE,
              seeds = [BOND_SEED, provider.key().as_ref()], bump)]
    pub provider_bond: Box<Account<'info, ProviderBond>>,
    #[account(init, payer = provider, seeds = [BOND_VAULT_SEED, provider.key().as_ref()], bump,
              token::mint = mint, token::authority = provider_bond)]
    pub bond_vault: Box<Account<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct MoveBond<'info> {
    pub provider: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(mut, seeds = [BOND_SEED, provider.key().as_ref()], bump = provider_bond.bump,
              has_one = provider @ EscrowError::Unauthorized)]
    pub provider_bond: Box<Account<'info, ProviderBond>>,
    #[account(mut, seeds = [BOND_VAULT_SEED, provider.key().as_ref()], bump = provider_bond.vault_bump)]
    pub bond_vault: Box<Account<'info, TokenAccount>>,
    #[account(mut, token::mint = config.mint, token::authority = provider)]
    pub provider_token: Box<Account<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
}

pub fn handle_open_bond(ctx: Context<OpenBond>) -> Result<()> {
    let b = &mut ctx.accounts.provider_bond;
    b.provider = ctx.accounts.provider.key();
    b.bump = ctx.bumps.provider_bond;
    b.vault_bump = ctx.bumps.bond_vault;
    Ok(())
}

pub fn handle_deposit_bond(ctx: Context<MoveBond>, amount: u64) -> Result<()> {
    let a = &ctx.accounts;
    token::transfer(
        CpiContext::new(
            a.token_program.key(),
            Transfer {
                from: a.provider_token.to_account_info(),
                to: a.bond_vault.to_account_info(),
                authority: a.provider.to_account_info(),
            },
        ),
        amount,
    )?;
    let b = &mut ctx.accounts.provider_bond;
    b.deposited = b.deposited.checked_add(amount).ok_or(EscrowError::Overflow)?;
    Ok(())
}

pub fn handle_withdraw_bond(ctx: Context<MoveBond>, amount: u64) -> Result<()> {
    let b = &ctx.accounts.provider_bond;
    let free = b.deposited - b.locked;
    require!(amount <= free, EscrowError::InsufficientBond);
    let provider = b.provider;
    let seeds: &[&[u8]] = &[BOND_SEED, provider.as_ref(), &[b.bump]];
    let a = &ctx.accounts;
    token::transfer(
        CpiContext::new_with_signer(
            a.token_program.key(),
            Transfer {
                from: a.bond_vault.to_account_info(),
                to: a.provider_token.to_account_info(),
                authority: a.provider_bond.to_account_info(),
            },
            &[seeds],
        ),
        amount,
    )?;
    ctx.accounts.provider_bond.deposited -= amount;
    Ok(())
}
